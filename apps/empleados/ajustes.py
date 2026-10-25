"""Cálculo de próximos ajustes salariales según el esquema pactado con cada empleado."""

import datetime
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction

from apps.core.dates import worked_month_text

from .models import Employee, SalaryAdjustment, SalaryAdjustmentPlan

REASON_BY_METHOD = {
    SalaryAdjustmentPlan.Method.IPC: SalaryAdjustment.Reason.INFLACION,
    SalaryAdjustmentPlan.Method.PORCENTAJE: SalaryAdjustment.Reason.ACUERDO,
    SalaryAdjustmentPlan.Method.MONTO: SalaryAdjustment.Reason.ACUERDO,
}


@dataclass
class UpcomingAdjustment:
    employee: Employee
    plan: SalaryAdjustmentPlan | None
    last: SalaryAdjustment | None = None
    next_date: datetime.date | None = None
    base_salary: Decimal | None = None
    new_salary: Decimal | None = None
    pct: Decimal | None = None
    missing_ipc: list = field(default_factory=list)
    extras: Decimal = Decimal(0)

    @property
    def gross_now(self):
        return self.base_salary + self.extras if self.base_salary is not None else None

    @property
    def gross_new(self):
        return self.new_salary + self.extras if self.new_salary is not None else None

    @property
    def days_left(self):
        return (self.next_date - datetime.date.today()).days if self.next_date else None

    @property
    def status(self):
        """Clave usada para colores y filtros."""
        if not self.plan:
            return "sin_esquema"
        if self.base_salary is None:
            return "sin_salario"
        if self.days_left < 0:
            return "vencido"
        if self.days_left <= 15:
            return "proximo"
        return "programado"

    @property
    def can_apply(self):
        return bool(self.plan and self.new_salary and not self.missing_ipc)

    @property
    def ipc_missing_text(self):
        return ", ".join(f"{m:%m/%Y}" for m in self.missing_ipc)


def compute(employee):
    plan = getattr(employee, "salary_plan", None)
    if plan and not plan.active:
        plan = None
    row = UpcomingAdjustment(employee=employee, plan=plan)
    row.last = employee.salary_adjustments.order_by("-effective_date", "-id").first()
    row.base_salary = row.last.new_salary if row.last else None
    row.extras = row.last.extras_total if row.last else Decimal(0)
    if plan:
        row.next_date = plan.next_date(row.last)
        if row.base_salary:
            row.new_salary, row.pct, row.missing_ipc = plan.estimate(row.base_salary, row.next_date)
    return row


def upcoming(employees=None):
    employees = employees if employees is not None else Employee.objects.all()
    employees = employees.exclude(status=Employee.Status.DESVINCULADO).select_related(
        "department", "salary_plan"
    )
    rows = [compute(e) for e in employees]
    far = datetime.date.max
    return sorted(rows, key=lambda r: (r.next_date or far, r.employee.last_name))


@transaction.atomic
def apply(row, user):
    """Registra el ajuste programado. Devuelve el SalaryAdjustment creado."""
    if not row.can_apply:
        raise ValueError("El ajuste no se puede aplicar (falta salario, esquema o IPC).")
    plan = row.plan
    if plan.method == SalaryAdjustmentPlan.Method.IPC:
        months = plan.ipc_months(row.next_date)
        detail = f"IPC {months[0]:%m/%Y}–{months[-1]:%m/%Y}" if len(months) > 1 else f"IPC {months[0]:%m/%Y}"
        if plan.ipc_extra_percent:
            detail += f" + {plan.ipc_extra_percent:g} %"
    else:
        detail = plan.get_method_display()
    adjustment = SalaryAdjustment.objects.create(
        employee=row.employee,
        effective_date=row.next_date,
        previous_salary=row.base_salary,
        new_salary=row.new_salary,
        reason=REASON_BY_METHOD[plan.method],
        notes=f"Ajuste programado ({plan.get_frequency_months_display().lower()}): {detail}. Variación {row.pct:.2f} %. "
              f"Rige desde el {worked_month_text(row.next_date)}.",
        created_by=user,
    )
    adjustment.copy_extra_costs_from(row.last)
    return adjustment
