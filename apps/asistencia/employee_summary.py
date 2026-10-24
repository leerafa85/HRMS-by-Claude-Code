"""Resumen de asistencia de un empleado: inasistencias, llegadas tarde, horas extras y licencias,
con motivo, documentación y aprobación, subtotales por tipo y total general."""

from decimal import Decimal

from django.db.models import Q

from apps.core.formatting import format_number
from apps.licencias.models import LeaveRequest
from apps.reportes.documents import Document, Link, Note, Section, Table


def _doc(obj, field="attachment"):
    f = getattr(obj, field)
    return Link("Sí", f.url) if f else "No"


def _yes(value):
    return "Sí" if value else "No"


def _plural(n, singular, plural):
    return f"{n} {singular if n == 1 else plural}"


def build(employee, start, end):
    absences = list(employee.absences.filter(date__range=(start, end)).order_by("date"))
    tardies = list(employee.tardies.filter(date__range=(start, end)).order_by("date"))
    overtimes = list(employee.overtimes.filter(date__range=(start, end)).select_related("approved_by").order_by("date"))
    leaves = list(
        employee.leave_requests.filter(start_date__lte=end, end_date__gte=start)
        .exclude(status=LeaveRequest.Status.CANCELADA)
        .select_related("leave_type", "reviewed_by")
        .order_by("start_date")
    )

    doc = Document(
        title=f"Resumen de asistencia · {employee.full_name}",
        subtitle=[
            f"Legajo {employee.file_number} · CUIL {employee.cuil} · {employee.department or 'Sin área'}"
            f"{' · ' + str(employee.position) if employee.position else ''}",
            f"Período: {start:%d/%m/%Y} al {end:%d/%m/%Y}",
        ],
    )
    totals = []

    # Inasistencias
    justified = sum(a.justified for a in absences)
    with_doc = sum(bool(a.attachment) for a in absences)
    doc.add(Section(f"Inasistencias ({len(absences)})"), Table(
        ["Fecha", "Motivo", "Justificada", "Con goce", "Dio aviso", "Documentación", "Observaciones"],
        [[a.date, a.get_reason_display(), _yes(a.justified), _yes(a.paid), _yes(a.notified), _doc(a), a.notes]
         for a in absences],
        footer=["Subtotal", _plural(len(absences), "inasistencia", "inasistencias"),
                f"{justified} justificadas", f"{sum(a.paid for a in absences)} con goce", "",
                f"{with_doc} con documentación", f"{len(absences) - justified} injustificadas"] if absences else None,
        empty_text="Sin inasistencias en el período.",
    ))
    totals.append(["Inasistencias", len(absences), _plural(len(absences), "día", "días"), with_doc,
                   f"{justified} justificadas", f"{len(absences) - justified} injustificadas"])

    # Llegadas tarde
    minutes = sum(t.minutes_late for t in tardies)
    justified = sum(t.justified for t in tardies)
    with_doc = sum(bool(t.attachment) for t in tardies)
    doc.add(Section(f"Llegadas tarde ({len(tardies)})"), Table(
        ["Fecha", "Entrada pactada", "Llegada", "Minutos", "Justificada", "Documentación", "Observaciones"],
        [[t.date, t.scheduled_time.strftime("%H:%M") if t.scheduled_time else "", t.arrival_time.strftime("%H:%M"),
          t.minutes_late, _yes(t.justified), _doc(t), t.notes] for t in tardies],
        footer=["Subtotal", _plural(len(tardies), "llegada tarde", "llegadas tarde"), "", f"{minutes} min",
                f"{justified} justificadas", f"{with_doc} con documentación", ""] if tardies else None,
        empty_text="Sin llegadas tarde en el período.",
    ))
    totals.append(["Llegadas tarde", len(tardies), f"{minutes} min", with_doc,
                   f"{justified} justificadas", f"{len(tardies) - justified} sin justificar"])

    # Horas extras
    hours = sum((o.hours or Decimal(0)) for o in overtimes)
    approved = [o for o in overtimes if o.status == o.Status.APROBADA]
    h_approved = sum((o.hours or Decimal(0)) for o in approved)
    h50 = sum((o.hours for o in approved if o.rate == 50 and o.compensation == o.Compensation.PAGO), Decimal(0))
    h100 = sum((o.hours for o in approved if o.rate == 100 and o.compensation == o.Compensation.PAGO), Decimal(0))
    bank = sum((o.hours for o in approved if o.compensation == o.Compensation.BANCO), Decimal(0))
    pending = sum(o.status == o.Status.PENDIENTE for o in overtimes)
    with_doc = sum(bool(o.attachment) for o in overtimes)

    def schedule(o):
        if o.start_time and o.end_time:
            return f"{o.start_time:%H:%M} a {o.end_time:%H:%M}"
        return ""

    def approval(o):
        return f"{o.get_status_display()}{' por ' + str(o.approved_by) if o.approved_by else ''}"

    doc.add(Section(f"Horas extras ({len(overtimes)})"), Table(
        ["Fecha", "Horario", "Horas", "Recargo", "Compensación", "Motivo / tarea", "Documentación", "Aprobación"],
        [[o.date, schedule(o), format_number(o.hours), f"{o.rate} %", o.get_compensation_display(), o.reason,
          _doc(o), approval(o)] for o in overtimes],
        footer=["Subtotal", _plural(len(overtimes), "registro", "registros"), f"{format_number(hours)} h",
                f"Aprobadas: 50 % {format_number(h50)} h · 100 % {format_number(h100)} h",
                f"Banco: {format_number(bank)} h", "", f"{with_doc} con documentación",
                f"{len(approved)} aprobadas · {pending} pendientes"] if overtimes else None,
        empty_text="Sin horas extras en el período.",
    ))
    totals.append(["Horas extras", len(overtimes), f"{format_number(hours)} h ({format_number(h_approved)} h aprobadas)",
                   with_doc, f"{len(approved)} aprobadas", f"{pending} pendientes"])

    # Licencias y vacaciones
    def days_in_range(lr):
        if lr.half_day and lr.start_date == lr.end_date:
            return Decimal("0.5")
        if lr.start_date >= start and lr.end_date <= end:
            return lr.days
        s, e = max(lr.start_date, start), min(lr.end_date, end)
        return Decimal((e - s).days + 1)  # días corridos dentro del período

    approved_leaves = [lr for lr in leaves if lr.status == LeaveRequest.Status.APROBADA]
    days_approved = sum((days_in_range(lr) for lr in approved_leaves), Decimal(0))
    pending = sum(lr.status == LeaveRequest.Status.PENDIENTE for lr in leaves)
    with_doc = sum(bool(lr.attachment) for lr in leaves)

    def leave_approval(lr):
        return f"{lr.get_status_display()}{' por ' + str(lr.reviewed_by) if lr.reviewed_by else ''}"

    doc.add(Section(f"Vacaciones y licencias ({len(leaves)})"), Table(
        ["Tipo", "Desde", "Hasta", "Días", "Con goce", "Motivo", "Documentación", "Aprobación"],
        [[lr.leave_type.name, lr.start_date, lr.end_date, format_number(days_in_range(lr), 1),
          _yes(lr.leave_type.paid), lr.reason, _doc(lr), leave_approval(lr)] for lr in leaves],
        footer=["Subtotal", _plural(len(leaves), "solicitud", "solicitudes"), "",
                f"{format_number(days_approved, 1)} días aprobados", "", "", f"{with_doc} con documentación",
                f"{len(approved_leaves)} aprobadas · {pending} pendientes"] if leaves else None,
        empty_text="Sin vacaciones ni licencias en el período.",
    ))
    by_type = {}
    for lr in approved_leaves:
        by_type[lr.leave_type.name] = by_type.get(lr.leave_type.name, Decimal(0)) + days_in_range(lr)
    if by_type:
        doc.add(Note("Días aprobados por tipo: " + " · ".join(f"{k}: {format_number(v, 1)}" for k, v in by_type.items())))
    totals.append(["Vacaciones y licencias", len(leaves), f"{format_number(days_approved, 1)} días aprobados", with_doc,
                   f"{len(approved_leaves)} aprobadas", f"{pending} pendientes"])

    # Total general
    doc.add(Section("Total general"), Table(
        ["Tipo", "Registros", "Cantidad", "Con documentación", "Justificados / aprobados", "Pendientes / sin justificar"],
        totals,
        footer=["Total", sum(t[1] for t in totals), "", sum(t[3] for t in totals), "", ""],
    ))
    return doc


def employees_for(user):
    """Empleados cuyo resumen puede ver el usuario."""
    from apps.core.modules import Module
    from apps.empleados.models import Employee

    if user.can(Module.ASISTENCIA):
        return Employee.objects.all()
    own = getattr(user, "employee", None)
    if not own:
        return Employee.objects.none()
    return Employee.objects.filter(Q(pk=own.pk) | Q(manager=own))
