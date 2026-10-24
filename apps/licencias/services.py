from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.empleados.models import Employee

from . import lct
from .models import LeaveBalance, LeaveRequest, LeaveType


def vacation_type():
    return LeaveType.objects.filter(kind=LeaveType.Kind.VACACIONES, active=True).first()


@transaction.atomic
def generate_vacation_balances(year, carry_over=True, cap_third=True, overwrite=False):
    """Crea/actualiza los saldos de vacaciones del período según art. 150/153 LCT.

    Devuelve (creados, actualizados).
    """
    vt = vacation_type()
    if not vt:
        raise ValueError("No hay un tipo de licencia de clase «Vacaciones» activo.")
    created = updated = 0
    employees = Employee.objects.exclude(status=Employee.Status.DESVINCULADO).filter(hire_date__year__lte=year)
    for emp in employees:
        entitled = lct.vacation_entitlement(emp, year)
        carried = Decimal(0)
        if carry_over:
            prev = LeaveBalance.objects.filter(employee=emp, leave_type=vt, year=year - 1).first()
            if prev and prev.available > 0:
                carried = Decimal(prev.available)
                if cap_third:
                    carried = min(carried, (Decimal(prev.entitled) / 3).quantize(Decimal("0.1")))
        balance, was_created = LeaveBalance.objects.get_or_create(
            employee=emp, leave_type=vt, year=year, defaults={"entitled": entitled, "carried_over": carried}
        )
        if was_created:
            created += 1
        elif overwrite:
            balance.entitled = entitled
            balance.carried_over = carried
            balance.save()
            updated += 1
    return created, updated


def review_request(leave_request, user, approve, comment=""):
    leave_request.status = LeaveRequest.Status.APROBADA if approve else LeaveRequest.Status.RECHAZADA
    if approve:
        leave_request.full_clean()
    leave_request.reviewed_by = user
    leave_request.reviewed_at = timezone.now()
    leave_request.review_comment = comment
    leave_request.save()
    notify_employee(leave_request)
    return leave_request


def notify_employee(leave_request):
    """Envía un email al empleado con el resultado (si tiene email cargado)."""
    from django.core.mail import send_mail

    emp = leave_request.employee
    to = emp.work_email or emp.personal_email
    if not to:
        return
    send_mail(
        f"Tu solicitud de {leave_request.leave_type} fue {leave_request.get_status_display().lower()}",
        f"Hola {emp.first_name}:\n\nTu solicitud de {leave_request.leave_type} del "
        f"{leave_request.start_date:%d/%m/%Y} al {leave_request.end_date:%d/%m/%Y} "
        f"({leave_request.days} días) fue {leave_request.get_status_display().lower()}.\n"
        + (f"\nComentario: {leave_request.review_comment}\n" if leave_request.review_comment else ""),
        None,
        [to],
        fail_silently=True,
    )


def notify_approvers(leave_request):
    from django.core.mail import send_mail

    manager = leave_request.employee.manager
    to = [m for m in [getattr(manager, "work_email", None)] if m]
    if to:
        send_mail(
            f"Nueva solicitud de {leave_request.leave_type}: {leave_request.employee.full_name}",
            f"{leave_request.employee.full_name} solicitó {leave_request.leave_type} del "
            f"{leave_request.start_date:%d/%m/%Y} al {leave_request.end_date:%d/%m/%Y} ({leave_request.days} días).\n"
            "Ingresá al HRMS para aprobarla o rechazarla.",
            None,
            to,
            fail_silently=True,
        )
