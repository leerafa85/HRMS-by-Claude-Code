import datetime
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum

from apps.core.uploads import UploadTo
from apps.core.validators import validate_document
from apps.empleados.models import Employee, PaymentMethod

upload_payment = UploadTo("pagos")


class SalaryAdvance(models.Model):
    """Adelanto de sueldo entregado antes de la liquidación; se descuenta del sueldo del período indicado."""

    class Status(models.TextChoices):
        PENDIENTE_PAGO = "pendiente_pago", "Pendiente de pago"
        A_DESCONTAR = "a_descontar", "Pagado · pendiente de descuento"
        DESCONTADO = "descontado", "Descontado del sueldo"
        ANULADO = "anulado", "Anulado"

    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="advances", verbose_name="empleado")
    date = models.DateField("fecha del adelanto")
    amount = models.DecimalField("importe ($)", max_digits=14, decimal_places=2)
    reason = models.CharField("motivo", max_length=250)
    payment_method = models.CharField("forma de pago", max_length=15, choices=PaymentMethod.choices,
                                      default=PaymentMethod.TRANSFERENCIA)
    paid_date = models.DateField("fecha de pago realizado", null=True, blank=True,
                                 help_text="Vacío mientras el adelanto no se haya entregado.")
    discount_period = models.DateField(
        "se descuenta del sueldo de", help_text="Mes de liquidación en el que se descuenta.",
    )
    discounted = models.BooleanField("ya descontado", default=False)
    discounted_on = models.DateField("fecha de descuento", null=True, blank=True)
    cancelled = models.BooleanField("anulado", default=False)
    attachment = models.FileField("comprobante / recibo firmado", upload_to=upload_payment, blank=True,
                                  validators=[validate_document])
    notes = models.TextField("observaciones", blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+", verbose_name="registrado por")
    created_at = models.DateTimeField("registrado", auto_now_add=True)

    class Meta:
        verbose_name = "adelanto de sueldo"
        verbose_name_plural = "adelantos de sueldo"
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"Adelanto {self.employee} {self.date:%d/%m/%Y}"

    def clean(self):
        errors = {}
        if self.amount is not None and self.amount <= 0:
            errors["amount"] = "El importe debe ser mayor a cero."
        if self.paid_date and self.date and self.paid_date < self.date:
            errors["paid_date"] = "La fecha de pago no puede ser anterior a la fecha del adelanto."
        if self.discounted and not self.paid_date and not self.cancelled:
            errors["discounted"] = "No se puede marcar como descontado un adelanto que todavía no se pagó."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.discount_period:
            self.discount_period = self.discount_period.replace(day=1)
        if self.discounted and not self.discounted_on:
            self.discounted_on = datetime.date.today()
        if not self.discounted:
            self.discounted_on = None
        super().save(*args, **kwargs)

    @property
    def status(self):
        if self.cancelled:
            return self.Status.ANULADO
        if self.discounted:
            return self.Status.DESCONTADO
        if self.paid_date:
            return self.Status.A_DESCONTAR
        return self.Status.PENDIENTE_PAGO

    @property
    def status_label(self):
        return self.Status(self.status).label

    @classmethod
    def pending_discount(cls, employee=None, period=None):
        """Adelantos pagados que todavía no se descontaron (opcionalmente de un período)."""
        qs = cls.objects.filter(cancelled=False, discounted=False, paid_date__isnull=False)
        if employee is not None:
            qs = qs.filter(employee=employee)
        if period is not None:
            qs = qs.filter(discount_period=period.replace(day=1))
        return qs

    @classmethod
    def total(cls, qs):
        return qs.aggregate(t=Sum("amount"))["t"] or Decimal(0)


class FinalSettlement(models.Model):
    """Liquidación final por desvinculación, renuncia, retiro voluntario, etc."""

    class Status(models.TextChoices):
        BORRADOR = "borrador", "En preparación"
        CONFIRMADA = "confirmada", "Confirmada · pendiente de pago"
        PAGO_PARCIAL = "parcial", "Pagada parcialmente"
        PAGADA = "pagada", "Pagada"
        RECLAMO = "reclamo", "En reclamo / conciliación"
        ANULADA = "anulada", "Anulada"

    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="settlements", verbose_name="empleado")
    reason = models.CharField("motivo del egreso", max_length=20, choices=Employee.TerminationReason.choices)
    termination_date = models.DateField("fecha de egreso")
    notice_date = models.DateField("fecha de notificación", null=True, blank=True,
                                   help_text="Telegrama, carta documento o acuerdo.")
    due_date = models.DateField(
        "fecha límite de pago", null=True, blank=True,
        help_text="Vacío = 4 días hábiles desde el egreso (arts. 128 y 255 bis LCT). Verificalo con tu asesor.",
    )
    status = models.CharField("estado", max_length=12, choices=Status.choices, default=Status.BORRADOR)
    payment_method = models.CharField("forma de pago", max_length=15, choices=PaymentMethod.choices, blank=True)
    prepared_by = models.CharField("preparada por", max_length=120, blank=True,
                                   help_text="Estudio contable o responsable de liquidación.")
    attachment = models.FileField("documentación (recibo, acuerdo, telegrama)", upload_to=upload_payment, blank=True,
                                  validators=[validate_document])
    notes = models.TextField("observaciones / seguimiento", blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+", verbose_name="registrada por")
    created_at = models.DateTimeField("registrada", auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "liquidación final"
        verbose_name_plural = "liquidaciones finales"
        ordering = ["-termination_date", "-id"]

    def __str__(self):
        return f"Liquidación final {self.employee} ({self.get_reason_display()})"

    def save(self, *args, **kwargs):
        if not self.due_date and self.termination_date:
            self.due_date = business_days_after(self.termination_date, 4)
        super().save(*args, **kwargs)

    @property
    def total_earnings(self):
        return sum((i.amount for i in self.items.all() if i.kind == SettlementItem.Kind.HABER), Decimal(0))

    @property
    def total_deductions(self):
        return sum((i.amount for i in self.items.all() if i.kind == SettlementItem.Kind.DESCUENTO), Decimal(0))

    @property
    def total_to_pay(self):
        return self.total_earnings - self.total_deductions

    @property
    def total_paid(self):
        return sum((p.amount for p in self.payments.all()), Decimal(0))

    @property
    def balance(self):
        return self.total_to_pay - self.total_paid

    @property
    def is_overdue(self):
        return (self.due_date and self.due_date < datetime.date.today()
                and self.status in (self.Status.BORRADOR, self.Status.CONFIRMADA, self.Status.PAGO_PARCIAL))

    def refresh_status_from_payments(self):
        """Ajusta el estado según los pagos registrados (sin tocar estados de reclamo o anulación)."""
        if self.status in (self.Status.RECLAMO, self.Status.ANULADA):
            return
        paid, total = self.total_paid, self.total_to_pay
        if paid and total and paid >= total:
            self.status = self.Status.PAGADA
        elif paid:
            self.status = self.Status.PAGO_PARCIAL
        elif self.status in (self.Status.PAGO_PARCIAL, self.Status.PAGADA):
            self.status = self.Status.CONFIRMADA
        self.save(update_fields=["status", "updated_at"])


SETTLEMENT_CONCEPTS = [
    "Días trabajados del mes", "SAC proporcional", "Vacaciones no gozadas", "SAC sobre vacaciones no gozadas",
    "Indemnización por antigüedad (art. 245 LCT)", "Indemnización sustitutiva de preaviso (arts. 231/232 LCT)",
    "SAC sobre preaviso", "Integración mes de despido (art. 233 LCT)", "SAC sobre integración",
    "Gratificación por retiro voluntario", "Horas extras pendientes", "Aportes jubilatorios", "Obra social",
    "Ley 19.032 (PAMI)", "Cuota sindical", "Adelantos de sueldo pendientes", "Otros",
]


class SettlementItem(models.Model):
    class Kind(models.TextChoices):
        HABER = "haber", "Haber (a favor del empleado)"
        DESCUENTO = "descuento", "Descuento / retención"

    settlement = models.ForeignKey(FinalSettlement, on_delete=models.CASCADE, related_name="items")
    concept = models.CharField("concepto", max_length=150)
    kind = models.CharField("tipo", max_length=10, choices=Kind.choices, default=Kind.HABER)
    amount = models.DecimalField("importe ($)", max_digits=14, decimal_places=2)
    detail = models.CharField("detalle / cálculo", max_length=250, blank=True)

    class Meta:
        verbose_name = "concepto de liquidación"
        verbose_name_plural = "conceptos de liquidación"
        ordering = ["kind", "id"]

    def __str__(self):
        return f"{self.concept}: {self.amount}"


class SettlementPayment(models.Model):
    settlement = models.ForeignKey(FinalSettlement, on_delete=models.CASCADE, related_name="payments")
    date = models.DateField("fecha de pago")
    amount = models.DecimalField("importe ($)", max_digits=14, decimal_places=2)
    method = models.CharField("forma de pago", max_length=15, choices=PaymentMethod.choices,
                              default=PaymentMethod.TRANSFERENCIA)
    reference = models.CharField("referencia / comprobante", max_length=150, blank=True)

    class Meta:
        verbose_name = "pago de liquidación"
        verbose_name_plural = "pagos de liquidación"
        ordering = ["date", "id"]

    def __str__(self):
        return f"Pago {self.date:%d/%m/%Y} {self.amount}"


def business_days_after(date, days):
    """Fecha luego de `days` días hábiles (sin sábados, domingos ni feriados cargados)."""
    from apps.licencias.models import Holiday

    holidays = set(Holiday.objects.filter(date__gt=date, date__lte=date + datetime.timedelta(days=days * 3 + 10))
                   .values_list("date", flat=True))
    d, counted = date, 0
    while counted < days:
        d += datetime.timedelta(days=1)
        if d.weekday() < 5 and d not in holidays:
            counted += 1
    return d
