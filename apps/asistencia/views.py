import calendar
import datetime
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.crud import Column, HRCreateView, HRDeleteView, HRListView, HRUpdateView
from apps.core.dates import MONTH_CHOICES
from apps.core.models import AuditLog
from apps.core.modules import Level, Module
from apps.empleados.models import Department, Employee
from apps.licencias.models import LeaveRequest
from apps.reportes.excel import excel_response

from .forms import AbsenceForm, OvertimeForm, TardinessForm
from .models import Absence, Overtime, Tardiness

EMP_FILTER = ("empleado", "employee_id", "Empleado", lambda: [(e.pk, str(e)) for e in Employee.objects.exclude(status="baja")])
AREA_FILTER = ("area", "employee__department_id", "Área", lambda: [(d.pk, d.name) for d in Department.objects.all()])
MONTH_FILTER = ("mes", "date__month", "Mes", MONTH_CHOICES)
YEAR_FILTER = ("anio", "date__year", "Año", lambda: [(y, y) for y in range(datetime.date.today().year, 2019, -1)])
SEARCH = ["employee__first_name", "employee__last_name", "employee__file_number"]


class _Base:
    module = Module.ASISTENCIA

    def get_queryset(self):
        return super().get_queryset().select_related("employee")


class _FormBase:
    module = Module.ASISTENCIA

    def get_initial(self):
        return {"employee": self.request.GET.get("empleado"), "date": datetime.date.today()}

    def get_success_url(self):
        return self.url_for("list")


# ---------------------------------------------------------------- Inasistencias


class AbsenceList(_Base, HRListView):
    model = Absence
    url_prefix = "asistencia:inasistencia"
    title = "Inasistencias"
    create_label = "Registrar inasistencia"
    search_fields = SEARCH
    columns = [
        Column("Empleado", "employee"), Column("Fecha", "date"), Column("Motivo", "reason"),
        Column("Justificada", "justified"), Column("Con goce", "paid"), Column("Dio aviso", "notified"),
        Column("Comprobante", lambda a: "Sí" if a.attachment else "No"),
    ]
    filters = [EMP_FILTER, AREA_FILTER, ("justificada", "justified", "Justificada", [("True", "Sí"), ("False", "No")]),
               MONTH_FILTER, YEAR_FILTER]


class AbsenceCreate(_FormBase, HRCreateView):
    model = Absence
    form_class = AbsenceForm
    url_prefix = "asistencia:inasistencia"


class AbsenceUpdate(_FormBase, HRUpdateView):
    model = Absence
    form_class = AbsenceForm
    url_prefix = "asistencia:inasistencia"


class AbsenceDelete(HRDeleteView):
    model = Absence
    module = Module.ASISTENCIA
    url_prefix = "asistencia:inasistencia"


# ---------------------------------------------------------------- Llegadas tarde


class TardinessList(_Base, HRListView):
    model = Tardiness
    url_prefix = "asistencia:tardanza"
    title = "Llegadas tarde"
    create_label = "Registrar llegada tarde"
    search_fields = SEARCH
    columns = [
        Column("Empleado", "employee"), Column("Fecha", "date"), Column("Entrada pactada", lambda t: t.scheduled_time.strftime("%H:%M") if t.scheduled_time else "—"),
        Column("Llegada", lambda t: t.arrival_time.strftime("%H:%M")), Column("Minutos", "minutes_late"),
        Column("Justificada", "justified"), Column("Observaciones", "notes"),
    ]
    filters = [EMP_FILTER, AREA_FILTER, MONTH_FILTER, YEAR_FILTER]


class TardinessCreate(_FormBase, HRCreateView):
    model = Tardiness
    form_class = TardinessForm
    url_prefix = "asistencia:tardanza"


class TardinessUpdate(_FormBase, HRUpdateView):
    model = Tardiness
    form_class = TardinessForm
    url_prefix = "asistencia:tardanza"


class TardinessDelete(HRDeleteView):
    model = Tardiness
    module = Module.ASISTENCIA
    url_prefix = "asistencia:tardanza"


# ---------------------------------------------------------------- Horas extras

OT_BADGES = {"pendiente": "warning", "aprobada": "success", "rechazada": "danger"}


class OvertimeList(_Base, HRListView):
    model = Overtime
    url_prefix = "asistencia:horaextra"
    title = "Horas extras"
    create_label = "Registrar horas extras"
    template_name = "asistencia/overtime_list.html"
    search_fields = SEARCH
    columns = [
        Column("Empleado", "employee"), Column("Fecha", "date"), Column("Horas", "hours"),
        Column("Recargo", "rate"), Column("Compensación", "compensation"), Column("Motivo", "reason"),
        Column("Estado", "status", badge=OT_BADGES), Column("Aprobó", "approved_by"),
    ]
    filters = [EMP_FILTER, AREA_FILTER, ("estado", "status", "Estado", Overtime.Status.choices), MONTH_FILTER, YEAR_FILTER]


class OvertimeCreate(_FormBase, HRCreateView):
    model = Overtime
    form_class = OvertimeForm
    url_prefix = "asistencia:horaextra"


class OvertimeUpdate(_FormBase, HRUpdateView):
    model = Overtime
    form_class = OvertimeForm
    url_prefix = "asistencia:horaextra"


class OvertimeDelete(HRDeleteView):
    model = Overtime
    module = Module.ASISTENCIA
    url_prefix = "asistencia:horaextra"


@login_required
def overtime_review(request, pk):
    ot = get_object_or_404(Overtime.objects.select_related("employee"), pk=pk)
    own = getattr(request.user, "employee", None)
    allowed = request.user.can(Module.ASISTENCIA, Level.ADMINISTRAR) or (
        own and ot.employee.manager_id == own.pk
    )
    if request.method != "POST" or not allowed:
        raise PermissionDenied
    approve = request.POST.get("accion") == "aprobar"
    ot.status = Overtime.Status.APROBADA if approve else Overtime.Status.RECHAZADA
    ot.approved_by = request.user
    ot.save(update_fields=["status", "approved_by"])
    AuditLog.log(request.user, AuditLog.Action.APPROVE if approve else AuditLog.Action.REJECT, ot)
    messages.success(request, f"Horas extras {'aprobadas' if approve else 'rechazadas'}.")
    nxt = request.POST.get("next", "")
    return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else "asistencia:horaextra_list")


# ---------------------------------------------------------------- Resumen mensual (para liquidación)


def monthly_summary(year, month, employees):
    first = datetime.date(year, month, 1)
    last = datetime.date(year, month, calendar.monthrange(year, month)[1])
    absences = {
        r["employee_id"]: r
        for r in Absence.objects.filter(date__range=(first, last), employee__in=employees)
        .values("employee_id")
        .annotate(total=Count("id"), injust=Count("id", filter=Q(justified=False)))
    }
    tardies = {
        r["employee_id"]: r
        for r in Tardiness.objects.filter(date__range=(first, last), employee__in=employees)
        .values("employee_id")
        .annotate(n=Count("id"), mins=Sum("minutes_late"))
    }
    ot = {}
    for r in (
        Overtime.objects.filter(date__range=(first, last), employee__in=employees, status=Overtime.Status.APROBADA)
        .values("employee_id", "rate", "compensation")
        .annotate(h=Sum("hours"))
    ):
        d = ot.setdefault(r["employee_id"], {"h50": Decimal(0), "h100": Decimal(0), "banco": Decimal(0)})
        if r["compensation"] == Overtime.Compensation.BANCO:
            d["banco"] += r["h"]
        elif r["rate"] == 100:
            d["h100"] += r["h"]
        else:
            d["h50"] += r["h"]
    leaves = {}
    for lr in LeaveRequest.objects.filter(
        status=LeaveRequest.Status.APROBADA, start_date__lte=last, end_date__gte=first, employee__in=employees
    ).select_related("leave_type"):
        start, end = max(lr.start_date, first), min(lr.end_date, last)
        days = (end - start).days + 1 if not (lr.half_day and lr.start_date == lr.end_date) else 0.5
        d = leaves.setdefault(lr.employee_id, {})
        key = lr.leave_type.name
        d[key] = d.get(key, 0) + days
    rows = []
    for e in employees:
        a = absences.get(e.pk, {})
        t = tardies.get(e.pk, {})
        o = ot.get(e.pk, {"h50": 0, "h100": 0, "banco": 0})
        rows.append({
            "employee": e,
            "absences": a.get("total", 0),
            "absences_unjustified": a.get("injust", 0),
            "tardies": t.get("n", 0),
            "tardy_minutes": t.get("mins", 0) or 0,
            "h50": o["h50"], "h100": o["h100"], "banco": o["banco"],
            "leaves": leaves.get(e.pk, {}),
        })
    return rows


@login_required
def summary(request):
    if not request.user.can(Module.ASISTENCIA):
        raise PermissionDenied
    today = datetime.date.today()
    try:
        year = int(request.GET.get("anio", today.year))
        month = int(request.GET.get("mes", today.month))
        datetime.date(year, month, 1)
    except ValueError:
        year, month = today.year, today.month
    employees = Employee.objects.exclude(status=Employee.Status.DESVINCULADO).select_related("department")
    if request.GET.get("area"):
        employees = employees.filter(department_id=request.GET["area"])
    rows = monthly_summary(year, month, employees)
    if request.GET.get("exportar"):
        headers = ["Legajo", "Empleado", "Área", "Inasistencias", "Injustificadas", "Llegadas tarde", "Minutos tarde",
                   "HE 50 %", "HE 100 %", "HE a banco", "Licencias (días)"]
        data = [[r["employee"].file_number, str(r["employee"]), str(r["employee"].department or ""), r["absences"],
                 r["absences_unjustified"], r["tardies"], r["tardy_minutes"], r["h50"], r["h100"], r["banco"],
                 "; ".join(f"{k}: {v}" for k, v in r["leaves"].items())] for r in rows]
        return excel_response(f"novedades_{year}_{month:02d}", "Novedades", headers, data)
    return render(request, "asistencia/summary.html", {
        "rows": rows, "year": year, "month": month, "months": MONTH_CHOICES,
        "departments": Department.objects.all(), "area": request.GET.get("area", ""),
        "years": range(today.year + 1, today.year - 6, -1),
    })


@login_required
def my_attendance(request):
    employee = getattr(request.user, "employee", None)
    if not employee:
        messages.info(request, "Tu usuario no está vinculado a un legajo.")
        return redirect("dashboard")
    year = datetime.date.today().year
    return render(request, "asistencia/my_attendance.html", {
        "absences": employee.absences.filter(date__year=year),
        "tardies": employee.tardies.filter(date__year=year),
        "overtimes": employee.overtimes.filter(date__year=year),
        "year": year,
    })
