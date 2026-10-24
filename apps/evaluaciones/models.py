import calendar
import datetime
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.dates import MESES
from apps.empleados.models import Department, Employee

SCORE_MAX = 10


class PeriodType(models.TextChoices):
    MENSUAL = "mensual", "Mensual"
    TRIMESTRAL = "trimestral", "Trimestral"
    SEMESTRAL = "semestral", "Semestral"
    ANUAL = "anual", "Anual"


PERIODS_PER_YEAR = {PeriodType.MENSUAL: 12, PeriodType.TRIMESTRAL: 4, PeriodType.SEMESTRAL: 2, PeriodType.ANUAL: 1}
MONTHS_PER_PERIOD = {PeriodType.MENSUAL: 1, PeriodType.TRIMESTRAL: 3, PeriodType.SEMESTRAL: 6, PeriodType.ANUAL: 12}
ORDINAL = {1: "1.er", 2: "2.º", 3: "3.er", 4: "4.º"}


def period_label(period_type, year, number):
    if period_type == PeriodType.MENSUAL:
        return f"{MESES[number - 1]} {year}"
    if period_type == PeriodType.TRIMESTRAL:
        return f"{ORDINAL[number]} trimestre {year}"
    if period_type == PeriodType.SEMESTRAL:
        return f"{ORDINAL[number]} semestre {year}"
    return f"Año {year}"


def period_choices(period_type):
    n = PERIODS_PER_YEAR[PeriodType(period_type)]
    if period_type == PeriodType.MENSUAL:
        return [(i, MESES[i - 1]) for i in range(1, 13)]
    if n == 1:
        return [(1, "Todo el año")]
    word = "trimestre" if period_type == PeriodType.TRIMESTRAL else "semestre"
    return [(i, f"{ORDINAL[i]} {word}") for i in range(1, n + 1)]


def current_period_number(period_type, today=None):
    today = today or datetime.date.today()
    return (today.month - 1) // MONTHS_PER_PERIOD[PeriodType(period_type)] + 1


class GoalPlan(models.Model):
    """Conjunto de metas de un equipo (área) o de una persona para un período."""

    class Scope(models.TextChoices):
        EQUIPO = "equipo", "Equipo (área)"
        PERSONAL = "personal", "Personal"

    class Status(models.TextChoices):
        ABIERTO = "abierto", "En curso"
        CERRADO = "cerrado", "Evaluado / cerrado"

    period_type = models.CharField("tipo de meta", max_length=12, choices=PeriodType.choices)
    year = models.PositiveIntegerField("año")
    period_number = models.PositiveSmallIntegerField("período", default=1)
    scope = models.CharField("metas de", max_length=10, choices=Scope.choices, default=Scope.PERSONAL)
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.PROTECT,
                                   related_name="goal_plans", verbose_name="equipo / área")
    employee = models.ForeignKey(Employee, null=True, blank=True, on_delete=models.PROTECT,
                                 related_name="goal_plans", verbose_name="persona")
    status = models.CharField("estado", max_length=10, choices=Status.choices, default=Status.ABIERTO)
    evaluator = models.CharField("evaluador", max_length=120, blank=True)
    notes = models.TextField("comentario general", blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "plan de metas"
        verbose_name_plural = "planes de metas"
        ordering = ["-year", "-period_number", "scope", "id"]

    def __str__(self):
        return f"Metas {self.get_period_type_display().lower()} · {self.target_name} · {self.period_label}"

    def clean(self):
        errors = {}
        if self.period_type and self.period_number:
            if not 1 <= self.period_number <= PERIODS_PER_YEAR[PeriodType(self.period_type)]:
                errors["period_number"] = "Período inválido para el tipo de meta."
        if self.scope == self.Scope.EQUIPO:
            if not self.department_id:
                errors["department"] = "Elegí el equipo (área)."
            self.employee = None
        elif self.scope == self.Scope.PERSONAL:
            if not self.employee_id:
                errors["employee"] = "Elegí la persona."
            self.department = None
        if errors:
            raise ValidationError(errors)
        dup = GoalPlan.objects.filter(period_type=self.period_type, year=self.year, period_number=self.period_number,
                                      scope=self.scope, department=self.department, employee=self.employee)
        if dup.exclude(pk=self.pk).exists():
            raise ValidationError("Ya existe un plan de metas para ese destinatario y período.")

    @property
    def target_name(self):
        return str(self.department) if self.scope == self.Scope.EQUIPO else (
            self.employee.full_name if self.employee else "—")

    @property
    def period_label(self):
        return period_label(self.period_type, self.year, self.period_number)

    @property
    def start_date(self):
        months = MONTHS_PER_PERIOD[PeriodType(self.period_type)]
        return datetime.date(self.year, (self.period_number - 1) * months + 1, 1)

    @property
    def end_date(self):
        months = MONTHS_PER_PERIOD[PeriodType(self.period_type)]
        last_month = self.period_number * months
        return datetime.date(self.year, last_month, calendar.monthrange(self.year, last_month)[1])

    def _goals(self):
        return list(self.goals.all())

    @property
    def total_goals(self):
        return len(self._goals())

    @property
    def done_goals(self):
        return sum(g.done for g in self._goals())

    @property
    def progress(self):
        total = self.total_goals
        return round(self.done_goals * 100 / total) if total else 0

    @property
    def average_score(self):
        scores = [g.score for g in self._goals() if g.score is not None]
        return (sum(scores, Decimal(0)) / len(scores)).quantize(Decimal("0.01")) if scores else None

    def next_period(self):
        n = PERIODS_PER_YEAR[PeriodType(self.period_type)]
        return (self.year, self.period_number + 1) if self.period_number < n else (self.year + 1, 1)


class Goal(models.Model):
    plan = models.ForeignKey(GoalPlan, on_delete=models.CASCADE, related_name="goals")
    order = models.PositiveIntegerField("orden", default=0)
    objective = models.CharField("objetivo / meta", max_length=300)
    responsible = models.ForeignKey(Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                    verbose_name="responsable")
    done = models.BooleanField("cumplido", default=False)
    score = models.DecimalField(
        "evaluación (1 a 10)", max_digits=4, decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(Decimal(1)), MaxValueValidator(Decimal(SCORE_MAX))],
    )
    how_achieved = models.TextField("cómo lo cumplió", blank=True)
    observations = models.TextField("observaciones", blank=True)

    class Meta:
        verbose_name = "meta"
        verbose_name_plural = "metas"
        ordering = ["order", "id"]

    def __str__(self):
        return self.objective
