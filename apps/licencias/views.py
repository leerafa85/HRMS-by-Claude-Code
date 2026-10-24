import calendar
import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.core.crud import Column, HRCreateView, HRDeleteView, HRListView, HRUpdateView
from apps.core.dates import DIAS
from apps.core.models import AuditLog
from apps.core.modules import Level, Module
from apps.empleados.models import Department, Employee
from apps.reportes.excel import excel_response

from . import services
from .forms import (
    GenerateBalancesForm,
    HolidayForm,
    LeaveBalanceForm,
    LeaveRequestForm,
    LeaveTypeForm,
    ReviewForm,
)
from .models import Holiday, LeaveBalance, LeaveRequest, LeaveType

STATUS_BADGES = {"pendiente": "warning", "aprobada": "success", "rechazada": "danger", "cancelada": "secondary"}

# ---------------------------------------------------------------- Solicitudes


class RequestList(HRListView):
    model = LeaveRequest
    module = Module.LICENCIAS
    url_prefix = "licencias:solicitud"
    title = "Solicitudes de vacaciones y licencias"
    create_label = "Cargar licencia"
    search_fields = ["employee__first_name", "employee__last_name", "employee__file_number"]
    columns = [
        Column("Empleado", "employee", link=True),
        Column("Tipo", "leave_type"),
        Column("Desde", "start_date"),
        Column("Hasta", "end_date"),
        Column("Días", "days"),
        Column("Estado", "status", badge=STATUS_BADGES),
        Column("Solicitada", "created_at"),
    ]
    filters = [
        ("estado", "status", "Estado", LeaveRequest.Status.choices),
        ("tipo", "leave_type_id", "Tipo", lambda: [(t.pk, t.name) for t in LeaveType.objects.all()]),
        ("area", "employee__department_id", "Área", lambda: [(d.pk, d.name) for d in Department.objects.all()]),
        ("anio", "start_date__year", "Año", lambda: [(y, y) for y in range(datetime.date.today().year + 1, 2019, -1)]),
    ]

    def get_queryset(self):
        return super().get_queryset().select_related("employee", "leave_type")


@login_required
def request_export(request):
    if not request.user.can(Module.LICENCIAS):
        raise PermissionDenied
    view = RequestList()
    view.request = request
    view.kwargs = {}
    qs = view.get_queryset()
    rows = [
        [r.employee.file_number, str(r.employee), r.leave_type.name, r.start_date, r.end_date, r.days,
         "Sí" if r.leave_type.paid else "No", r.get_status_display(), str(r.reviewed_by or ""), r.reason]
        for r in qs
    ]
    headers = ["Legajo", "Empleado", "Tipo", "Desde", "Hasta", "Días", "Con goce", "Estado", "Revisó", "Motivo"]
    return excel_response("licencias", "Licencias", headers, rows)


class RequestCreate(HRCreateView):
    """Carga directa por RRHH (puede quedar aprobada en el acto)."""

    model = LeaveRequest
    form_class = LeaveRequestForm
    module = Module.LICENCIAS
    url_prefix = "licencias:solicitud"
    template_name = "licencias/request_form.html"
    title = "Cargar licencia"

    def get_initial(self):
        return {"employee": self.request.GET.get("empleado")}

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_auto_approve"] = self.request.user.can(Module.LICENCIAS, Level.ADMINISTRAR)
        return ctx

    def form_valid(self, form):
        form.instance.requested_by = self.request.user
        if self.request.POST.get("aprobar") and self.request.user.can(Module.LICENCIAS, Level.ADMINISTRAR):
            form.instance.status = LeaveRequest.Status.APROBADA
            form.instance.reviewed_by = self.request.user
            from django.utils import timezone

            form.instance.reviewed_at = timezone.now()
            try:
                form.instance.full_clean()
            except ValidationError as e:
                form.add_error(None, e)
                return self.form_invalid(form)
        return super().form_valid(form)


class RequestUpdate(HRUpdateView):
    model = LeaveRequest
    form_class = LeaveRequestForm
    module = Module.LICENCIAS
    url_prefix = "licencias:solicitud"
    template_name = "licencias/request_form.html"


class RequestDelete(HRDeleteView):
    model = LeaveRequest
    module = Module.LICENCIAS
    url_prefix = "licencias:solicitud"


def _visible_request(user, pk):
    req = get_object_or_404(LeaveRequest.objects.select_related("employee", "leave_type"), pk=pk)
    own = getattr(user, "employee", None)
    if user.can(Module.LICENCIAS):
        return req
    if own and (req.employee_id == own.pk or req.employee.manager_id == own.pk):
        return req
    raise PermissionDenied


@login_required
def request_detail(request, pk):
    req = _visible_request(request.user, pk)
    own = getattr(request.user, "employee", None)
    balance = None
    if req.leave_type.tracks_balance:
        balance = LeaveBalance.objects.filter(employee=req.employee, leave_type=req.leave_type, year=req.period).first()
    overlapping_team = LeaveRequest.objects.none()
    if req.employee.department_id:
        overlapping_team = LeaveRequest.objects.filter(
            employee__department_id=req.employee.department_id,
            status=LeaveRequest.Status.APROBADA,
            start_date__lte=req.end_date,
            end_date__gte=req.start_date,
        ).exclude(employee=req.employee).select_related("employee", "leave_type")
    return render(request, "licencias/request_detail.html", {
        "req": req,
        "balance": balance,
        "remaining": balance.available - req.days if balance else None,
        "warnings": req.warnings() if req.status == LeaveRequest.Status.PENDIENTE else [],
        "can_review": req.status == LeaveRequest.Status.PENDIENTE and req.can_be_reviewed_by(request.user),
        "can_cancel": (
            req.status in (LeaveRequest.Status.PENDIENTE, LeaveRequest.Status.APROBADA)
            and ((own and own.pk == req.employee_id and req.start_date > datetime.date.today())
                 or request.user.can(Module.LICENCIAS, Level.ADMINISTRAR))
        ),
        "can_edit": request.user.can(Module.LICENCIAS, Level.EDITAR),
        "review_form": ReviewForm(),
        "overlapping_team": overlapping_team,
    })


@login_required
def request_review(request, pk):
    req = _visible_request(request.user, pk)
    if request.method != "POST" or not req.can_be_reviewed_by(request.user):
        raise PermissionDenied
    if req.status != LeaveRequest.Status.PENDIENTE:
        messages.warning(request, "La solicitud ya fue revisada.")
        return redirect("licencias:solicitud_detail", pk=pk)
    form = ReviewForm(request.POST)
    form.is_valid()
    approve = request.POST.get("accion") == "aprobar"
    try:
        services.review_request(req, request.user, approve, form.cleaned_data.get("comment", ""))
    except ValidationError as e:
        req.status = LeaveRequest.Status.PENDIENTE
        for msg in e.messages:
            messages.error(request, msg)
        return redirect("licencias:solicitud_detail", pk=pk)
    AuditLog.log(request.user, AuditLog.Action.APPROVE if approve else AuditLog.Action.REJECT, req)
    messages.success(request, f"Solicitud {'aprobada' if approve else 'rechazada'}.")
    nxt = request.POST.get("next")
    return redirect(nxt if nxt and nxt.startswith("/") and not nxt.startswith("//") else reverse("licencias:aprobaciones"))


@login_required
def request_cancel(request, pk):
    req = _visible_request(request.user, pk)
    own = getattr(request.user, "employee", None)
    allowed = request.user.can(Module.LICENCIAS, Level.ADMINISTRAR) or (
        own and own.pk == req.employee_id and req.start_date > datetime.date.today()
    )
    if request.method != "POST" or not allowed:
        raise PermissionDenied
    req.status = LeaveRequest.Status.CANCELADA
    req.save(update_fields=["status"])
    AuditLog.log(request.user, AuditLog.Action.UPDATE, req, f"Cancelación: {req}")
    messages.success(request, "Solicitud cancelada.")
    return redirect("licencias:solicitud_detail", pk=pk)


@login_required
def approvals(request):
    user = request.user
    own = getattr(user, "employee", None)
    qs = LeaveRequest.objects.filter(status=LeaveRequest.Status.PENDIENTE).select_related("employee", "leave_type")
    if not user.can(Module.LICENCIAS, Level.ADMINISTRAR):
        if not own:
            raise PermissionDenied
        qs = qs.filter(employee__manager=own)
    return render(request, "licencias/approvals.html", {"requests": qs.order_by("start_date"), "review_form": ReviewForm()})


# ---------------------------------------------------------------- Autogestión


@login_required
def my_leaves(request):
    employee = getattr(request.user, "employee", None)
    if not employee:
        messages.info(request, "Tu usuario no está vinculado a un legajo.")
        return redirect("dashboard")
    form = LeaveRequestForm(request.POST or None, request.FILES or None, employee=employee, self_service=True)
    if request.method == "POST" and form.is_valid():
        req = form.save(commit=False)
        req.employee = employee
        req.requested_by = request.user
        if not req.leave_type.requires_approval:
            req.status = LeaveRequest.Status.APROBADA
        req.save()
        AuditLog.log(request.user, AuditLog.Action.CREATE, req)
        if req.status == LeaveRequest.Status.PENDIENTE:
            services.notify_approvers(req)
        messages.success(request, "Solicitud enviada." if req.status == LeaveRequest.Status.PENDIENTE else "Licencia registrada.")
        return redirect("licencias:mis_licencias")
    balances = LeaveBalance.objects.filter(employee=employee).select_related("leave_type").order_by("-year")
    return render(request, "licencias/my_leaves.html", {
        "form": form,
        "balances": balances,
        "requests": employee.leave_requests.select_related("leave_type"),
        "holidays": Holiday.objects.filter(date__gte=datetime.date.today())[:6],
        "types": LeaveType.objects.filter(active=True, self_service=True),
    })


# ---------------------------------------------------------------- Calendario


@login_required
def leave_calendar(request):
    user = request.user
    own = getattr(user, "employee", None)
    if not (user.can(Module.LICENCIAS) or (own and own.reports.exists())):
        raise PermissionDenied
    today = datetime.date.today()
    try:
        year = int(request.GET.get("anio", today.year))
        month = int(request.GET.get("mes", today.month))
        datetime.date(year, month, 1)
    except ValueError:
        year, month = today.year, today.month
    first = datetime.date(year, month, 1)
    last = datetime.date(year, month, calendar.monthrange(year, month)[1])

    employees = Employee.objects.exclude(status=Employee.Status.DESVINCULADO)
    if not user.can(Module.LICENCIAS):
        employees = employees.filter(Q(manager=own) | Q(pk=own.pk))
    dept = request.GET.get("area")
    if dept:
        employees = employees.filter(department_id=dept)
    reqs = LeaveRequest.objects.filter(
        employee__in=employees,
        status__in=[LeaveRequest.Status.APROBADA, LeaveRequest.Status.PENDIENTE],
        start_date__lte=last,
        end_date__gte=first,
    ).select_related("leave_type", "employee")
    holidays = {h.date: h for h in Holiday.objects.filter(date__range=(first, last))}
    days = [first + datetime.timedelta(days=i) for i in range((last - first).days + 1)]
    by_emp = {}
    for r in reqs:
        by_emp.setdefault(r.employee_id, []).append(r)
    rows = []
    for e in employees.order_by("last_name"):
        cells = []
        for d in days:
            match = next((r for r in by_emp.get(e.pk, []) if r.start_date <= d <= r.end_date), None)
            cells.append({"date": d, "req": match, "holiday": d in holidays})
        if by_emp.get(e.pk) or not request.GET.get("solo_ausentes"):
            rows.append({"employee": e, "cells": cells})
    prev_m = (first - datetime.timedelta(days=1)).replace(day=1)
    next_m = last + datetime.timedelta(days=1)
    return render(request, "licencias/calendar.html", {
        "days": [{"date": d, "holiday": holidays.get(d), "weekend": d.weekday() >= 5} for d in days],
        "rows": rows,
        "first": first,
        "prev_m": prev_m,
        "next_m": next_m,
        "types": LeaveType.objects.filter(active=True),
        "departments": Department.objects.all(),
        "area": dept,
    })


# ---------------------------------------------------------------- Saldos


class BalanceList(HRListView):
    model = LeaveBalance
    module = Module.LICENCIAS
    url_prefix = "licencias:saldo"
    title = "Saldos de vacaciones y licencias"
    create_label = "Nuevo saldo"
    template_name = "licencias/balance_list.html"
    search_fields = ["employee__first_name", "employee__last_name", "employee__file_number"]
    columns = [
        Column("Empleado", "employee"),
        Column("Tipo", "leave_type"),
        Column("Período", "year"),
        Column("Corresponden", "entitled"),
        Column("Arrastre", "carried_over"),
        Column("Ajuste", "adjustment"),
        Column("Gozados", "used"),
        Column("Pendientes de aprobación", "pending"),
        Column("Disponibles", "available"),
    ]
    filters = [
        ("anio", "year", "Período", lambda: [(y, y) for y in LeaveBalance.objects.values_list("year", flat=True).distinct().order_by("-year")]),
        ("tipo", "leave_type_id", "Tipo", lambda: [(t.pk, t.name) for t in LeaveType.objects.filter(tracks_balance=True)]),
    ]

    def get_queryset(self):
        return super().get_queryset().select_related("employee", "leave_type")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["generate_form"] = GenerateBalancesForm()
        return ctx


class BalanceCreate(HRCreateView):
    model = LeaveBalance
    form_class = LeaveBalanceForm
    module = Module.LICENCIAS
    url_prefix = "licencias:saldo"
    required_level = Level.ADMINISTRAR

    def get_success_url(self):
        return self.url_for("list")


class BalanceUpdate(HRUpdateView):
    model = LeaveBalance
    form_class = LeaveBalanceForm
    module = Module.LICENCIAS
    url_prefix = "licencias:saldo"
    required_level = Level.ADMINISTRAR

    def get_success_url(self):
        return self.url_for("list")


class BalanceDelete(HRDeleteView):
    model = LeaveBalance
    module = Module.LICENCIAS
    url_prefix = "licencias:saldo"


@login_required
def generate_balances(request):
    if not request.user.can(Module.LICENCIAS, Level.ADMINISTRAR) or request.method != "POST":
        raise PermissionDenied
    form = GenerateBalancesForm(request.POST)
    if form.is_valid():
        try:
            created, updated = services.generate_vacation_balances(
                form.cleaned_data["year"], form.cleaned_data["carry_over"],
                form.cleaned_data["carry_over_cap"], form.cleaned_data["overwrite"],
            )
        except ValueError as e:
            messages.error(request, str(e))
        else:
            messages.success(request, f"Saldos de vacaciones {form.cleaned_data['year']}: {created} creados, {updated} recalculados.")
    return redirect(reverse("licencias:saldo_list") + f"?anio={form.cleaned_data.get('year', '')}")


@login_required
def balance_export(request):
    if not request.user.can(Module.LICENCIAS):
        raise PermissionDenied
    qs = LeaveBalance.objects.select_related("employee", "leave_type")
    if request.GET.get("anio"):
        qs = qs.filter(year=request.GET["anio"])
    rows = [[b.employee.file_number, str(b.employee), b.leave_type.name, b.year, b.entitled, b.carried_over,
             b.adjustment, b.used, b.pending, b.available] for b in qs]
    headers = ["Legajo", "Empleado", "Tipo", "Período", "Corresponden", "Arrastre", "Ajuste", "Gozados", "Pendientes",
               "Disponibles"]
    return excel_response("saldos", "Saldos", headers, rows)


# ---------------------------------------------------------------- Tipos de licencia


class TypeList(HRListView):
    model = LeaveType
    module = Module.CONFIGURACION
    url_prefix = "licencias:tipo"
    title = "Tipos de licencia"
    create_label = "Nuevo tipo"
    columns = [
        Column("Nombre", "name"),
        Column("Clase", "kind"),
        Column("Cómputo", "day_count"),
        Column("Con goce", "paid"),
        Column("Días por evento", "days_per_event"),
        Column("Tope anual", "days_per_year"),
        Column("Controla saldo", "tracks_balance"),
        Column("Autogestión", "self_service"),
        Column("Referencia legal", "legal_reference"),
        Column("Activa", "active"),
    ]


class TypeCreate(HRCreateView):
    model = LeaveType
    form_class = LeaveTypeForm
    module = Module.CONFIGURACION
    url_prefix = "licencias:tipo"

    def get_success_url(self):
        return self.url_for("list")


class TypeUpdate(HRUpdateView):
    model = LeaveType
    form_class = LeaveTypeForm
    module = Module.CONFIGURACION
    url_prefix = "licencias:tipo"

    def get_success_url(self):
        return self.url_for("list")


class TypeDelete(HRDeleteView):
    model = LeaveType
    module = Module.CONFIGURACION
    url_prefix = "licencias:tipo"


# ---------------------------------------------------------------- Feriados


class HolidayList(HRListView):
    model = Holiday
    module = Module.FERIADOS
    url_prefix = "licencias:feriado"
    title = "Feriados y días no laborables"
    create_label = "Nuevo feriado"
    template_name = "licencias/holiday_list.html"
    paginate_by = 60
    columns = [
        Column("Fecha", "date"),
        Column("Día", lambda h: DIAS[h.date.weekday()]),
        Column("Motivo", "name"),
        Column("Tipo", "kind", badge={"inamovible": "danger", "trasladable": "warning", "no_laborable": "info",
                                      "puente": "info", "empresa": "primary", "local": "secondary"}),
    ]

    def get_queryset(self):
        year = self.request.GET.get("anio") or datetime.date.today().year
        return super().get_queryset().filter(date__year=year)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["year"] = int(self.request.GET.get("anio") or datetime.date.today().year)
        return ctx


class HolidayCreate(HRCreateView):
    model = Holiday
    form_class = HolidayForm
    module = Module.FERIADOS
    url_prefix = "licencias:feriado"

    def get_success_url(self):
        return self.url_for("list") + f"?anio={self.object.date.year}"


class HolidayUpdate(HRUpdateView):
    model = Holiday
    form_class = HolidayForm
    module = Module.FERIADOS
    url_prefix = "licencias:feriado"

    def get_success_url(self):
        return self.url_for("list") + f"?anio={self.object.date.year}"


class HolidayDelete(HRDeleteView):
    model = Holiday
    module = Module.FERIADOS
    url_prefix = "licencias:feriado"


@login_required
def holiday_import(request):
    """Importa feriados nacionales desde la API pública de ArgentinaDatos."""
    if not request.user.can(Module.FERIADOS, Level.EDITAR) or request.method != "POST":
        raise PermissionDenied
    from .holidays_data import import_from_api

    year = int(request.POST.get("anio", datetime.date.today().year))
    try:
        created, updated = import_from_api(year)
        messages.success(request, f"Feriados {year} importados: {created} nuevos, {updated} actualizados.")
    except Exception as e:  # red caída, API cambiada, etc.
        messages.error(request, f"No se pudo consultar la API de feriados ({e}). Podés cargarlos manualmente.")
    return redirect(reverse("licencias:feriado_list") + f"?anio={year}")
