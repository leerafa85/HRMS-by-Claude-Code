import datetime
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.forms import inlineformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.core.crud import Column, HRCreateView, HRDeleteView, HRListView, HRUpdateView
from apps.core.dates import MESES
from apps.core.formatting import format_ars
from apps.core.models import AuditLog
from apps.core.modules import Level, Module
from apps.empleados.models import Department, Employee
from apps.reportes.documents import Document, Link, Note, Section, Table, document_response, wants_document

from .forms import (
    CONCEPTS,
    FinalSettlementForm,
    MarkDiscountedForm,
    SalaryAdvanceForm,
    SettlementItemForm,
    SettlementItemFormSet,
    SettlementPaymentForm,
)
from .models import FinalSettlement, SalaryAdvance, SettlementItem

ADV_BADGES = {"pendiente_pago": "warning", "a_descontar": "info", "descontado": "success", "anulado": "secondary"}
STATUS_FILTER = {
    "pendiente_pago": Q(cancelled=False, paid_date__isnull=True),
    "a_descontar": Q(cancelled=False, discounted=False, paid_date__isnull=False),
    "descontado": Q(cancelled=False, discounted=True),
    "anulado": Q(cancelled=True),
}


def _period_label(d):
    return f"{MESES[d.month - 1]} {d.year}" if d else ""


def _periods():
    today = datetime.date.today().replace(day=1)
    from apps.empleados.models import add_months

    return [(add_months(today, i).strftime("%Y-%m-01"), _period_label(add_months(today, i))) for i in range(2, -13, -1)]


# ---------------------------------------------------------------- Adelantos


class AdvanceList(HRListView):
    model = SalaryAdvance
    module = Module.PAGOS
    url_prefix = "pagos:adelanto"
    title = "Adelantos de sueldo"
    create_label = "Registrar adelanto"
    template_name = "pagos/advance_list.html"
    printable = True
    search_fields = ["employee__first_name", "employee__last_name", "employee__file_number", "reason"]
    extra_actions = [("Informe de adelantos", "pagos:adelanto_informe", "file-earmark-bar-graph")]
    columns = [
        Column("Empleado", "employee"),
        Column("Fecha", "date"),
        Column("Importe", "amount", kind="money"),
        Column("Motivo", "reason"),
        Column("Forma de pago", "payment_method"),
        Column("Pagado el", "paid_date"),
        Column("Se descuenta de", lambda a: _period_label(a.discount_period)),
        Column("Estado", "status_label", badge=ADV_BADGES, badge_key="status"),
    ]
    filters = [
        ("empleado", "employee_id", "Empleado", lambda: [(e.pk, str(e)) for e in Employee.objects.all()]),
        ("area", "employee__department_id", "Área", lambda: [(d.pk, d.name) for d in Department.objects.all()]),
        ("estado", None, "Estado", SalaryAdvance.Status.choices),
        ("periodo", "discount_period", "Se descuenta de", _periods),
    ]

    def get_queryset(self):
        qs = super().get_queryset().select_related("employee")
        status = self.request.GET.get("estado")
        if status in STATUS_FILTER:
            qs = qs.filter(STATUS_FILTER[status])
        return qs

    def print_footer(self, qs):
        active = qs.filter(cancelled=False)
        return ["Total", f"{qs.count()} adelantos", format_ars(SalaryAdvance.total(active)), "", "",
                f"Pendiente de pago: {format_ars(SalaryAdvance.total(active.filter(paid_date__isnull=True)))}",
                f"A descontar: {format_ars(SalaryAdvance.total(active.filter(discounted=False, paid_date__isnull=False)))}",
                f"Descontado: {format_ars(SalaryAdvance.total(active.filter(discounted=True)))}"]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["mark_form"] = MarkDiscountedForm()
        ctx["totals"] = self.print_footer(self.get_queryset())
        return ctx


class _AdvanceForm:
    model = SalaryAdvance
    form_class = SalaryAdvanceForm
    module = Module.PAGOS
    url_prefix = "pagos:adelanto"

    def get_success_url(self):
        nxt = self.request.GET.get("next", "")
        return nxt if nxt.startswith("/") and not nxt.startswith("//") else self.url_for("list")


class AdvanceCreate(_AdvanceForm, HRCreateView):
    title = "Registrar adelanto de sueldo"

    def get_initial(self):
        today = datetime.date.today()
        initial = {"date": today, "discount_period": today.replace(day=1)}
        emp = Employee.objects.filter(pk=self.request.GET.get("empleado") or 0).first()
        if emp:
            initial["employee"] = emp.pk
            if emp.payment_method:
                initial["payment_method"] = emp.payment_method
        return initial


class AdvanceUpdate(_AdvanceForm, HRUpdateView):
    title = "Editar adelanto de sueldo"


class AdvanceDelete(HRDeleteView):
    model = SalaryAdvance
    module = Module.PAGOS
    url_prefix = "pagos:adelanto"


def _require(user, level):
    if not user.can(Module.PAGOS, level):
        raise PermissionDenied


def _next(request, default):
    nxt = request.POST.get("next", "")
    return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else default)


@login_required
def advance_mark_paid(request, pk):
    _require(request.user, Level.EDITAR)
    if request.method != "POST":
        raise PermissionDenied
    adv = get_object_or_404(SalaryAdvance, pk=pk, cancelled=False)
    adv.paid_date = adv.paid_date or timezone.localdate()
    adv.save(update_fields=["paid_date"])
    AuditLog.log(request.user, AuditLog.Action.UPDATE, adv, f"Adelanto pagado: {adv}")
    messages.success(request, f"Adelanto de {adv.employee.full_name} marcado como pagado.")
    return _next(request, "pagos:adelanto_list")


@login_required
def advance_mark_discounted(request):
    """Marca como descontados todos los adelantos pagados de un período (al liquidar los sueldos)."""
    _require(request.user, Level.ADMINISTRAR)
    form = MarkDiscountedForm(request.POST)
    if request.method != "POST" or not form.is_valid():
        messages.error(request, "Indicá el período liquidado.")
        return redirect("pagos:adelanto_list")
    period = form.cleaned_data["period"].replace(day=1)
    qs = SalaryAdvance.pending_discount(period=period)
    if request.POST.get("empleado"):
        qs = qs.filter(employee_id=request.POST["empleado"])
    total, count = SalaryAdvance.total(qs), qs.count()
    qs.update(discounted=True, discounted_on=timezone.localdate())
    AuditLog.objects.create(user=request.user, action=AuditLog.Action.UPDATE, model="adelanto de sueldo",
                            description=f"{count} adelantos descontados del período {_period_label(period)}")
    messages.success(request, f"{count} adelanto(s) por {format_ars(total)} marcados como descontados de {_period_label(period)}.")
    return redirect(reverse("pagos:adelanto_list") + f"?periodo={period:%Y-%m-%d}")


def _date_param(request, name, default):
    try:
        return datetime.date.fromisoformat(request.GET.get(name, ""))
    except ValueError:
        return default


@login_required
def advance_report(request):
    """Informe general (por empleado) o detallado de un empleado, con PDF e impresión."""
    _require(request.user, Level.VER)
    today = datetime.date.today()
    start = _date_param(request, "desde", datetime.date(today.year, 1, 1))
    end = _date_param(request, "hasta", datetime.date(today.year, 12, 31))
    area = request.GET.get("area", "")
    emp_id = request.GET.get("empleado", "")
    qs = SalaryAdvance.objects.filter(date__range=(start, end)).select_related("employee", "employee__department")
    if area:
        qs = qs.filter(employee__department_id=area)
    employee = Employee.objects.filter(pk=emp_id).first() if emp_id.isdigit() else None
    if employee:
        qs = qs.filter(employee=employee)

    statuses = [SalaryAdvance.Status.PENDIENTE_PAGO, SalaryAdvance.Status.A_DESCONTAR, SalaryAdvance.Status.DESCONTADO]
    subtitle = [f"Período: {start:%d/%m/%Y} al {end:%d/%m/%Y}"]
    if area:
        subtitle.append(f"Área: {Department.objects.filter(pk=area).first()}")

    def by_status(items):
        sums = {s: Decimal(0) for s in statuses}
        for a in items:
            if a.status in sums:
                sums[a.status] += a.amount
        return sums

    advances = list(qs.order_by("date"))
    active = [a for a in advances if not a.cancelled]
    if employee:
        doc = Document(title=f"Adelantos de sueldo · {employee.full_name}",
                       subtitle=[f"Legajo {employee.file_number} · {employee.department or 'Sin área'}"
                                 f" · Forma de pago habitual: {employee.get_payment_method_display() or 'sin definir'}"] + subtitle)
        for status in statuses + [SalaryAdvance.Status.ANULADO]:
            items = [a for a in advances if a.status == status]
            if not items and status == SalaryAdvance.Status.ANULADO:
                continue
            doc.add(Section(f"{SalaryAdvance.Status(status).label} ({len(items)})"), Table(
                ["Fecha", "Importe", "Motivo", "Forma de pago", "Pagado el", "Se descuenta de", "Descontado el", "Comprobante"],
                [[a.date, format_ars(a.amount), a.reason, a.get_payment_method_display(), a.paid_date,
                  _period_label(a.discount_period), a.discounted_on,
                  Link("Sí", a.attachment.url) if a.attachment else "No"] for a in items],
                footer=["Subtotal", format_ars(sum((a.amount for a in items), Decimal(0))), "", "", "", "", "", ""]
                if items else None,
                empty_text="Sin adelantos en este estado.",
            ))
        sums = by_status(active)
        doc.add(Section("Total general"), Table(
            ["Estado", "Importe"],
            [[SalaryAdvance.Status(s).label, format_ars(sums[s])] for s in statuses],
            footer=["Total adelantado (sin anulados)", format_ars(sum(sums.values(), Decimal(0)))],
        ))
    else:
        rows, totals = [], {s: Decimal(0) for s in statuses}
        per_emp = {}
        for a in active:
            per_emp.setdefault(a.employee, []).append(a)
        for emp, items in sorted(per_emp.items(), key=lambda kv: kv[0].last_name):
            sums = by_status(items)
            for s in statuses:
                totals[s] += sums[s]
            url = reverse("pagos:adelanto_informe") + f"?empleado={emp.pk}&desde={start}&hasta={end}"
            rows.append([Link(str(emp), url), emp.file_number, str(emp.department or ""), len(items),
                         format_ars(sum(sums.values(), Decimal(0))),
                         format_ars(sums[statuses[0]]), format_ars(sums[statuses[1]]), format_ars(sums[statuses[2]])])
        doc = Document(title="Informe general de adelantos de sueldo", subtitle=subtitle).add(
            Table(["Empleado", "Legajo", "Área", "Adelantos", "Total", "Pendiente de pago", "Pendiente de descuento",
                   "Descontado"], rows,
                  footer=["Total", "", "", sum(r[3] for r in rows), format_ars(sum(totals.values(), Decimal(0))),
                          format_ars(totals[statuses[0]]), format_ars(totals[statuses[1]]), format_ars(totals[statuses[2]])],
                  empty_text="No hay adelantos en el período."),
            Note("Los adelantos anulados no se suman. Tocá un empleado para ver su detalle."),
        )
    if wants_document(request):
        return document_response(request, doc, "informe_adelantos" + (f"_{employee.file_number}" if employee else ""))
    return render(request, "pagos/report.html", {
        "doc": doc, "start": start, "end": end, "area": area, "employee": employee,
        "employees": Employee.objects.order_by("last_name"), "departments": Department.objects.all(),
    })


# ---------------------------------------------------------------- Liquidaciones finales

SET_BADGES = {"borrador": "secondary", "confirmada": "warning", "parcial": "info", "pagada": "success",
              "reclamo": "danger", "anulada": "dark"}


class SettlementList(HRListView):
    model = FinalSettlement
    module = Module.PAGOS
    url_prefix = "pagos:liquidacion"
    title = "Liquidaciones finales"
    create_label = "Nueva liquidación final"
    printable = True
    search_fields = ["employee__first_name", "employee__last_name", "employee__file_number"]
    columns = [
        Column("Empleado", "employee", link=True),
        Column("Motivo", "reason"),
        Column("Egreso", "termination_date"),
        Column("Fecha límite de pago", lambda s: f"{s.due_date:%d/%m/%Y}{' (vencida)' if s.is_overdue else ''}" if s.due_date else "—"),
        Column("Total a pagar", "total_to_pay", kind="money"),
        Column("Pagado", "total_paid", kind="money"),
        Column("Saldo", "balance", kind="money"),
        Column("Estado", "get_status_display", badge=SET_BADGES, badge_key="status"),
    ]
    filters = [("estado", "status", "Estado", FinalSettlement.Status.choices),
               ("motivo", "reason", "Motivo", Employee.TerminationReason.choices)]

    def get_queryset(self):
        return super().get_queryset().select_related("employee").prefetch_related("items", "payments")

    def print_footer(self, qs):
        items = list(qs)
        return ["Total", f"{len(items)} liquidaciones", "", "",
                format_ars(sum((s.total_to_pay for s in items), Decimal(0))),
                format_ars(sum((s.total_paid for s in items), Decimal(0))),
                format_ars(sum((s.balance for s in items), Decimal(0))), ""]


class _SettlementForm:
    model = FinalSettlement
    form_class = FinalSettlementForm
    module = Module.PAGOS
    url_prefix = "pagos:liquidacion"
    template_name = "pagos/settlement_form.html"

    def initial_items(self):
        return []

    def get_formset(self):
        instance = self.object or FinalSettlement()
        if self.request.method == "POST":
            return SettlementItemFormSet(self.request.POST, instance=instance, prefix="items")
        initial = self.initial_items()
        factory = inlineformset_factory(FinalSettlement, SettlementItem, form=SettlementItemForm,
                                        formset=SettlementItemFormSet, extra=len(initial), can_delete=True)
        return factory(instance=instance, prefix="items", initial=initial)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault("formset", self.get_formset())
        ctx["concepts"] = CONCEPTS
        ctx["pending_advances"] = self.pending_advances()
        return ctx

    def pending_advances(self):
        return SalaryAdvance.objects.none()

    def form_valid(self, form):
        formset = SettlementItemFormSet(self.request.POST, instance=form.instance, prefix="items")
        if not formset.is_valid():
            return self.render_to_response(self.get_context_data(form=form, formset=formset))
        response = super().form_valid(form)
        formset.instance = self.object
        formset.save()
        if self.request.POST.get("descontar_adelantos"):
            pending = SalaryAdvance.pending_discount(employee=self.object.employee)
            count = pending.count()
            pending.update(discounted=True, discounted_on=timezone.localdate(),
                           notes="Descontado en la liquidación final")
            if count:
                messages.info(self.request, f"{count} adelanto(s) marcados como descontados en esta liquidación.")
        return response


class SettlementCreate(_SettlementForm, HRCreateView):
    title = "Nueva liquidación final"

    def employee(self):
        return Employee.objects.filter(pk=self.request.GET.get("empleado") or 0).first()

    def get_initial(self):
        emp = self.employee()
        if not emp:
            return {}
        return {"employee": emp.pk, "reason": emp.termination_reason, "termination_date": emp.termination_date,
                "payment_method": emp.payment_method}

    def pending_advances(self):
        emp = self.employee()
        return SalaryAdvance.pending_discount(employee=emp) if emp else SalaryAdvance.objects.none()

    def initial_items(self):
        pending = self.pending_advances()
        if not pending.exists():
            return []
        detail = ", ".join(f"{a.date:%d/%m/%Y} {format_ars(a.amount)}" for a in pending)
        return [{"concept": "Adelantos de sueldo pendientes", "kind": SettlementItem.Kind.DESCUENTO,
                 "amount": SalaryAdvance.total(pending), "detail": detail[:250]}]


class SettlementUpdate(_SettlementForm, HRUpdateView):
    title = "Editar liquidación final"


class SettlementDelete(HRDeleteView):
    model = FinalSettlement
    module = Module.PAGOS
    url_prefix = "pagos:liquidacion"


def settlement_document(s):
    earnings = [i for i in s.items.all() if i.kind == SettlementItem.Kind.HABER]
    deductions = [i for i in s.items.all() if i.kind == SettlementItem.Kind.DESCUENTO]
    doc = Document(
        title=f"Liquidación final · {s.employee.full_name}",
        subtitle=[f"Legajo {s.employee.file_number} · CUIL {s.employee.cuil} · Ingreso {s.employee.hire_date:%d/%m/%Y}",
                  f"Motivo: {s.get_reason_display()} · Egreso: {s.termination_date:%d/%m/%Y}"
                  + (f" · Fecha límite de pago: {s.due_date:%d/%m/%Y}" if s.due_date else ""),
                  f"Estado: {s.get_status_display()}"],
    )
    doc.add(Section("Haberes"), Table(["Concepto", "Detalle / cálculo", "Importe"],
                                      [[i.concept, i.detail, format_ars(i.amount)] for i in earnings],
                                      footer=["Subtotal haberes", "", format_ars(s.total_earnings)],
                                      empty_text="Sin haberes cargados."))
    doc.add(Section("Descuentos y retenciones"), Table(["Concepto", "Detalle / cálculo", "Importe"],
                                                        [[i.concept, i.detail, format_ars(i.amount)] for i in deductions],
                                                        footer=["Subtotal descuentos", "", format_ars(s.total_deductions)],
                                                        empty_text="Sin descuentos cargados."))
    doc.add(Section("Pagos realizados"), Table(["Fecha", "Forma de pago", "Referencia", "Importe"],
                                               [[p.date, p.get_method_display(), p.reference, format_ars(p.amount)]
                                                for p in s.payments.all()],
                                               footer=["Total pagado", "", "", format_ars(s.total_paid)],
                                               empty_text="Todavía no se registraron pagos."))
    doc.add(Section("Resumen"), Table(["", "Importe"], [
        ["Total haberes", format_ars(s.total_earnings)], ["Total descuentos", format_ars(s.total_deductions)],
        ["Total a pagar", format_ars(s.total_to_pay)], ["Pagado", format_ars(s.total_paid)]],
        footer=["Saldo pendiente", format_ars(s.balance)]))
    if s.notes:
        doc.add(Note(f"Observaciones: {s.notes}"))
    return doc


@login_required
def settlement_detail(request, pk):
    _require(request.user, Level.VER)
    s = get_object_or_404(FinalSettlement.objects.select_related("employee").prefetch_related("items", "payments"), pk=pk)
    if wants_document(request):
        return document_response(request, settlement_document(s), f"liquidacion_final_{s.employee.file_number}")
    can_edit = request.user.can(Module.PAGOS, Level.EDITAR)
    payment_form = SettlementPaymentForm(initial={"date": timezone.localdate(), "amount": s.balance if s.balance > 0 else None,
                                                  "method": s.payment_method or "transferencia"})
    return render(request, "pagos/settlement_detail.html", {
        "s": s, "doc": settlement_document(s), "can_edit": can_edit,
        "can_admin": request.user.can(Module.PAGOS, Level.ADMINISTRAR), "payment_form": payment_form,
        "statuses": FinalSettlement.Status.choices,
    })


@login_required
def settlement_add_payment(request, pk):
    _require(request.user, Level.EDITAR)
    s = get_object_or_404(FinalSettlement, pk=pk)
    form = SettlementPaymentForm(request.POST)
    if request.method == "POST" and form.is_valid():
        payment = form.save(commit=False)
        payment.settlement = s
        payment.save()
        s.refresh_status_from_payments()
        AuditLog.log(request.user, AuditLog.Action.UPDATE, s, f"Pago de liquidación final {format_ars(payment.amount)}")
        messages.success(request, f"Pago registrado. Saldo pendiente: {format_ars(s.balance)}.")
    else:
        for errs in form.errors.values():
            for e in errs:
                messages.error(request, e)
    return redirect("pagos:liquidacion_detail", pk=pk)


@login_required
def settlement_delete_payment(request, pk, payment_pk):
    _require(request.user, Level.ADMINISTRAR)
    s = get_object_or_404(FinalSettlement, pk=pk)
    if request.method == "POST":
        s.payments.filter(pk=payment_pk).delete()
        s.refresh_status_from_payments()
        messages.success(request, "Pago eliminado.")
    return redirect("pagos:liquidacion_detail", pk=pk)


@login_required
def settlement_set_status(request, pk):
    _require(request.user, Level.EDITAR)
    s = get_object_or_404(FinalSettlement, pk=pk)
    status = request.POST.get("status")
    if request.method == "POST" and status in FinalSettlement.Status.values:
        s.status = status
        note = request.POST.get("note", "").strip()
        if note:
            stamp = timezone.localtime().strftime("%d/%m/%Y %H:%M")
            s.notes = (s.notes + "\n" if s.notes else "") + f"[{stamp} · {request.user}] {note}"
        s.save()
        AuditLog.log(request.user, AuditLog.Action.UPDATE, s, f"Liquidación final: estado {s.get_status_display()}")
        messages.success(request, "Seguimiento actualizado.")
    return redirect("pagos:liquidacion_detail", pk=pk)
