"""Bloques de la pantalla de inicio: agenda de fechas, novedades de la semana y solicitudes."""

import datetime
from dataclasses import dataclass

from django.db.models import Q
from django.urls import reverse

from apps.core.dates import MESES
from apps.core.formatting import format_ars, format_number

from .modules import Level, Module


@dataclass
class AgendaItem:
    date: datetime.date
    title: str
    detail: str = ""
    url: str = ""
    icon: str = "calendar-event"
    end: datetime.date | None = None
    done_today: bool = False

    @property
    def days(self):
        return (self.date - datetime.date.today()).days

    @property
    def overdue(self):
        return (self.end or self.date) < datetime.date.today()

    @property
    def ongoing(self):
        today = datetime.date.today()
        return bool(self.end and self.date <= today <= self.end)


def agenda(user, today=None, horizon=30):
    """Fechas a tener en cuenta en los próximos `horizon` días (y lo vencido sin resolver)."""
    from apps.empleados.models import Employee

    today = today or datetime.date.today()
    limit = today + datetime.timedelta(days=horizon)
    active = Employee.objects.exclude(status=Employee.Status.DESVINCULADO)
    items = []

    if user.can(Module.SALARIOS) or user.can(Module.PAGOS):
        windows = {}
        for e in active.exclude(pay_day_from__isnull=True):
            w = e.next_pay_window(today)
            if w:
                windows.setdefault(w, []).append(e)
        for (start, end), emps in sorted(windows.items()):
            if start <= limit:
                items.append(AgendaItem(
                    start, f"Acreditación de sueldos · {len(emps)} empleado{'s' if len(emps) != 1 else ''}",
                    f"Del {start:%d/%m} al {end:%d/%m}: " + ", ".join(e.full_name for e in emps[:4])
                    + ("…" if len(emps) > 4 else ""),
                    reverse("empleados:empleado_list"), "cash-stack", end=end))

    if user.can(Module.PAGOS):
        from apps.pagos.models import FinalSettlement, SalaryAdvance

        for a in SalaryAdvance.objects.filter(cancelled=False, paid_date__isnull=True).select_related("employee"):
            items.append(AgendaItem(a.date, f"Pagar adelanto a {a.employee.full_name}", format_ars(a.amount),
                                    reverse("pagos:adelanto_list") + "?estado=pendiente_pago", "wallet2"))
        period = today.replace(day=1)
        pending = SalaryAdvance.pending_discount(period=period)
        if pending.exists():
            from apps.empleados.models import add_months

            month_end = add_months(period, 1) - datetime.timedelta(days=1)
            items.append(AgendaItem(
                month_end, f"Descontar adelantos en la liquidación de {MESES[period.month - 1].lower()}",
                f"{pending.count()} adelanto(s) por {format_ars(SalaryAdvance.total(pending))}",
                reverse("pagos:adelanto_list") + f"?estado=a_descontar&periodo={period:%Y-%m-%d}", "dash-circle"))
        open_states = [FinalSettlement.Status.BORRADOR, FinalSettlement.Status.CONFIRMADA, FinalSettlement.Status.PAGO_PARCIAL]
        for s in FinalSettlement.objects.filter(status__in=open_states, due_date__lte=limit).select_related("employee"):
            items.append(AgendaItem(s.due_date, f"Pago de liquidación final · {s.employee.full_name}",
                                    f"Saldo {format_ars(s.balance)} · {s.get_status_display()}",
                                    reverse("pagos:liquidacion_detail", args=[s.pk]), "file-earmark-ruled"))

    if user.can(Module.SALARIOS):
        from apps.empleados import ajustes

        # Agrupados: los vencidos en un solo aviso y los próximos por fecha, para no saturar la agenda.
        overdue, by_date = [], {}
        for r in ajustes.upcoming():
            if not r.next_date or r.next_date > limit:
                continue
            if r.next_date < today:
                overdue.append(r)
            else:
                by_date.setdefault(r.next_date, []).append(r)
        if overdue:
            items.append(AgendaItem(
                min(r.next_date for r in overdue), f"{len(overdue)} ajuste{'s' if len(overdue) != 1 else ''} salarial"
                f"{'es' if len(overdue) != 1 else ''} vencido{'s' if len(overdue) != 1 else ''} sin aplicar",
                ", ".join(r.employee.full_name for r in overdue[:4]) + ("…" if len(overdue) > 4 else ""),
                reverse("empleados:proximos_ajustes") + "?estado=vencido", "graph-up-arrow"))
        for date, rows in sorted(by_date.items()):
            items.append(AgendaItem(
                date, f"Ajuste salarial · {rows[0].employee.full_name}" if len(rows) == 1
                else f"{len(rows)} ajustes salariales", ", ".join(r.employee.full_name for r in rows[1:5]) if len(rows) > 1
                else (rows[0].plan.summary if rows[0].plan else ""),
                reverse("empleados:proximos_ajustes"), "graph-up-arrow"))

    if user.can(Module.EMPLEADOS):
        for e in active.filter(trial_end_date__range=(today, limit)):
            items.append(AgendaItem(e.trial_end_date, f"Fin del período de prueba · {e.full_name}", "",
                                    reverse("empleados:empleado_detail", args=[e.pk]), "hourglass-bottom"))
        for e in active.filter(contract_end_date__range=(today, limit)):
            items.append(AgendaItem(e.contract_end_date, f"Fin de contrato · {e.full_name}", "",
                                    reverse("empleados:empleado_detail", args=[e.pk]), "file-earmark-x"))

    return sorted(items, key=lambda i: (not i.overdue, i.date))


def week_bounds(today=None):
    today = today or datetime.date.today()
    start = today - datetime.timedelta(days=today.weekday())
    return start, start + datetime.timedelta(days=6)


def weekly_news(user, today=None):
    """Novedades del personal en la semana actual (lunes a domingo), agrupadas por tipo."""
    from apps.empleados.models import Employee

    start, end = week_bounds(today)
    groups = []

    def add(title, icon, entries, url=""):
        if entries:
            groups.append({"title": title, "icon": icon, "entries": entries, "url": url})

    if user.can(Module.EMPLEADOS):
        add("Ingresos", "person-plus", [f"{e.full_name} · {e.hire_date:%d/%m}" for e in
                                        Employee.objects.filter(hire_date__range=(start, end))])
        add("Egresos", "person-dash", [f"{e.full_name} · {e.termination_date:%d/%m}" for e in
                                       Employee.objects.filter(termination_date__range=(start, end))])
    if user.can(Module.LICENCIAS):
        from apps.licencias.models import LeaveRequest

        add("Licencias y vacaciones", "airplane", [
            f"{r.employee.full_name} · {r.leave_type} ({r.start_date:%d/%m} al {r.end_date:%d/%m})"
            for r in LeaveRequest.objects.filter(status=LeaveRequest.Status.APROBADA, start_date__lte=end,
                                                 end_date__gte=start).select_related("employee", "leave_type")],
            reverse("licencias:calendario"))
    if user.can(Module.ASISTENCIA):
        from apps.asistencia.models import Absence, Overtime, Tardiness

        add("Inasistencias", "person-x", [
            f"{a.employee.full_name} · {a.date:%d/%m} · {a.get_reason_display()}{'' if a.justified else ' (injustificada)'}"
            for a in Absence.objects.filter(date__range=(start, end)).select_related("employee")],
            reverse("asistencia:inasistencia_list"))
        add("Llegadas tarde", "alarm", [
            f"{t.employee.full_name} · {t.date:%d/%m} · {t.minutes_late} min"
            for t in Tardiness.objects.filter(date__range=(start, end)).select_related("employee")],
            reverse("asistencia:tardanza_list"))
        add("Horas extras", "clock-history", [
            f"{o.employee.full_name} · {o.date:%d/%m} · {format_number(o.hours)} h al {o.rate} % ({o.get_status_display().lower()})"
            for o in Overtime.objects.filter(date__range=(start, end)).select_related("employee")],
            reverse("asistencia:horaextra_list"))
    if user.can(Module.PAGOS):
        from apps.pagos.models import SalaryAdvance

        add("Adelantos de sueldo", "wallet2", [
            f"{a.employee.full_name} · {a.date:%d/%m} · {format_ars(a.amount)}"
            for a in SalaryAdvance.objects.filter(date__range=(start, end), cancelled=False).select_related("employee")],
            reverse("pagos:adelanto_list"))
    if user.can(Module.SALARIOS):
        from apps.empleados.models import SalaryAdjustment

        add("Ajustes salariales con vigencia en la semana", "graph-up-arrow", [
            f"{a.employee.full_name} · {a.effective_date:%d/%m} · {a.get_reason_display()}"
            for a in SalaryAdjustment.objects.filter(effective_date__range=(start, end)).select_related("employee")],
            reverse("empleados:salario_list"))
    birthdays = []
    for e in Employee.objects.exclude(status=Employee.Status.DESVINCULADO).exclude(birth_date__isnull=True):
        for year in {start.year, end.year}:
            try:
                d = e.birth_date.replace(year=year)
            except ValueError:
                d = datetime.date(year, 3, 1)
            if start <= d <= end:
                birthdays.append(f"{e.full_name} · {d:%d/%m}")
    add("Cumpleaños", "balloon", birthdays)
    return {"start": start, "end": end, "groups": groups}


def staff_requests(user, employee, days=15):
    """Solicitudes del personal: pendientes de confirmar y confirmadas (aprobadas o rechazadas) recientes."""
    from django.utils import timezone

    from apps.asistencia.models import Overtime
    from apps.licencias.models import LeaveRequest

    since = timezone.now() - datetime.timedelta(days=days)
    leaves = LeaveRequest.objects.select_related("employee", "leave_type")
    overtime = Overtime.objects.select_related("employee")
    if not user.can(Module.LICENCIAS, Level.VER):
        leaves = leaves.filter(employee__manager=employee) if employee else leaves.none()
    if not user.can(Module.ASISTENCIA, Level.VER):
        overtime = overtime.filter(employee__manager=employee) if employee else overtime.none()

    pending = [
        {"kind": str(r.leave_type), "employee": r.employee, "when": f"{r.start_date:%d/%m} al {r.end_date:%d/%m}",
         "extra": f"{format_number(r.days, 1)} días", "status": "Pendiente", "badge": "warning", "sort": r.created_at,
         "url": reverse("licencias:solicitud_detail", args=[r.pk])}
        for r in leaves.filter(status=LeaveRequest.Status.PENDIENTE)
    ] + [
        {"kind": "Horas extras", "employee": o.employee, "when": f"{o.date:%d/%m}", "extra": f"{format_number(o.hours)} h al {o.rate} %",
         "status": "Pendiente", "badge": "warning", "sort": o.created_at,
         "url": reverse("asistencia:horaextra_list") + "?estado=pendiente"}
        for o in overtime.filter(status=Overtime.Status.PENDIENTE)
    ]
    confirmed = [
        {"kind": str(r.leave_type), "employee": r.employee, "when": f"{r.start_date:%d/%m} al {r.end_date:%d/%m}",
         "extra": f"{format_number(r.days, 1)} días", "status": r.get_status_display(),
         "badge": "success" if r.status == LeaveRequest.Status.APROBADA else "danger", "sort": r.reviewed_at,
         "url": reverse("licencias:solicitud_detail", args=[r.pk])}
        for r in leaves.filter(status__in=[LeaveRequest.Status.APROBADA, LeaveRequest.Status.RECHAZADA],
                               reviewed_at__gte=since)
    ] + [
        {"kind": "Horas extras", "employee": o.employee, "when": f"{o.date:%d/%m}", "extra": f"{format_number(o.hours)} h al {o.rate} %",
         "status": o.get_status_display(), "badge": "success" if o.status == Overtime.Status.APROBADA else "danger",
         "sort": o.created_at, "url": reverse("asistencia:horaextra_list")}
        for o in overtime.filter(~Q(status=Overtime.Status.PENDIENTE), created_at__gte=since)
    ]
    pending.sort(key=lambda r: r["sort"])
    confirmed.sort(key=lambda r: r["sort"], reverse=True)
    return {"pending": pending, "confirmed": confirmed[:15], "days": days}
