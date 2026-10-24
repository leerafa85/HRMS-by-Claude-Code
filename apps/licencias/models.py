import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.uploads import UploadTo
from apps.core.validators import validate_document
from apps.empleados.models import Employee

from . import lct

upload_leave = UploadTo("licencias")


class Holiday(models.Model):
    class Kind(models.TextChoices):
        INAMOVIBLE = "inamovible", "Feriado inamovible"
        TRASLADABLE = "trasladable", "Feriado trasladable"
        NO_LABORABLE = "no_laborable", "Día no laborable"
        PUENTE = "puente", "Día no laborable con fines turísticos"
        EMPRESA = "empresa", "Día no laborable de la empresa"
        LOCAL = "local", "Feriado provincial / local"

    date = models.DateField("fecha", unique=True)
    name = models.CharField("motivo", max_length=150)
    kind = models.CharField("tipo", max_length=15, choices=Kind.choices, default=Kind.INAMOVIBLE)
    is_working_day_optional = models.BooleanField(
        "optativo para el empleador",
        default=False,
        help_text="Días no laborables: el empleador decide si se trabaja (se paga simple).",
    )

    class Meta:
        verbose_name = "feriado"
        verbose_name_plural = "feriados"
        ordering = ["date"]

    def __str__(self):
        return f"{self.date:%d/%m/%Y} {self.name}"

    @property
    def is_paid_holiday(self):
        """Feriado nacional: si se trabaja, las horas se pagan al 100 %."""
        return self.kind in (self.Kind.INAMOVIBLE, self.Kind.TRASLADABLE, self.Kind.LOCAL)


class LeaveType(models.Model):
    class DayCount(models.TextChoices):
        CORRIDOS = "corridos", "Días corridos"
        HABILES = "habiles", "Días hábiles"

    class Kind(models.TextChoices):
        VACACIONES = "vacaciones", "Vacaciones"
        ENFERMEDAD = "enfermedad", "Enfermedad"
        ESPECIAL = "especial", "Licencia especial"
        OTRA = "otra", "Otra"

    name = models.CharField("nombre", max_length=100, unique=True)
    code = models.SlugField("código", max_length=30, unique=True)
    kind = models.CharField("clase", max_length=15, choices=Kind.choices, default=Kind.ESPECIAL)
    color = models.CharField("color", max_length=7, default="#0d6efd")
    paid = models.BooleanField("con goce de haberes", default=True)
    day_count = models.CharField("cómputo", max_length=10, choices=DayCount.choices, default=DayCount.CORRIDOS)
    days_per_year = models.DecimalField(
        "días por año", max_digits=6, decimal_places=1, null=True, blank=True,
        help_text="Tope anual. Vacío = sin tope. Para vacaciones se calcula por antigüedad (art. 150 LCT).",
    )
    days_per_event = models.DecimalField(
        "días por evento", max_digits=6, decimal_places=1, null=True, blank=True,
        help_text="Máximo por solicitud (ej. matrimonio 10, fallecimiento 3).",
    )
    tracks_balance = models.BooleanField("controla saldo", default=False)
    requires_attachment = models.BooleanField("requiere comprobante", default=False)
    requires_approval = models.BooleanField("requiere aprobación", default=True)
    self_service = models.BooleanField("el empleado puede solicitarla", default=True)
    legal_reference = models.CharField("referencia legal", max_length=200, blank=True)
    active = models.BooleanField("activa", default=True)

    class Meta:
        verbose_name = "tipo de licencia"
        verbose_name_plural = "tipos de licencia"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def is_vacation(self):
        return self.kind == self.Kind.VACACIONES


class LeaveBalance(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="leave_balances", verbose_name="empleado")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE, related_name="balances", verbose_name="tipo")
    year = models.PositiveIntegerField("período (año)")
    entitled = models.DecimalField("días que corresponden", max_digits=6, decimal_places=1, default=0)
    carried_over = models.DecimalField("arrastre de períodos anteriores", max_digits=6, decimal_places=1, default=0)
    adjustment = models.DecimalField("ajuste manual (+/-)", max_digits=6, decimal_places=1, default=0)
    notes = models.CharField("observaciones", max_length=200, blank=True)

    class Meta:
        verbose_name = "saldo de licencia"
        verbose_name_plural = "saldos de licencias"
        unique_together = ("employee", "leave_type", "year")
        ordering = ["-year", "employee"]

    def __str__(self):
        return f"{self.employee} - {self.leave_type} {self.year}"

    @property
    def total(self):
        return self.entitled + self.carried_over + self.adjustment

    @property
    def used(self):
        return LeaveRequest.days_used(self.employee, self.leave_type, self.year)

    @property
    def pending(self):
        return LeaveRequest.days_used(self.employee, self.leave_type, self.year, statuses=[LeaveRequest.Status.PENDIENTE])

    @property
    def available(self):
        return self.total - self.used


class LeaveRequest(models.Model):
    class Status(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        APROBADA = "aprobada", "Aprobada"
        RECHAZADA = "rechazada", "Rechazada"
        CANCELADA = "cancelada", "Cancelada"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="leave_requests", verbose_name="empleado")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, related_name="requests", verbose_name="tipo")
    start_date = models.DateField("desde")
    end_date = models.DateField("hasta")
    days = models.DecimalField("días", max_digits=6, decimal_places=1, default=0)
    half_day = models.BooleanField("medio día", default=False, help_text="Solo para solicitudes de un único día.")
    period_year = models.PositiveIntegerField(
        "período", null=True, blank=True, help_text="Año del saldo que consume (vacaciones). Vacío = año de inicio."
    )
    reason = models.TextField("motivo / comentario", blank=True)
    attachment = models.FileField(
        "comprobante", upload_to=upload_leave, blank=True, validators=[validate_document],
        help_text="Certificado médico, acta de matrimonio, etc.",
    )
    status = models.CharField("estado", max_length=12, choices=Status.choices, default=Status.PENDIENTE)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="solicitado por",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="revisado por",
    )
    reviewed_at = models.DateTimeField("fecha de revisión", null=True, blank=True)
    review_comment = models.TextField("comentario del revisor", blank=True)
    created_at = models.DateTimeField("fecha de solicitud", auto_now_add=True)

    class Meta:
        verbose_name = "solicitud de licencia"
        verbose_name_plural = "solicitudes de licencia"
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.employee} - {self.leave_type} ({self.start_date:%d/%m/%Y} al {self.end_date:%d/%m/%Y})"

    @property
    def period(self):
        return self.period_year or self.start_date.year

    def compute_days(self):
        if self.half_day and self.start_date == self.end_date:
            return 0.5
        holidays = set(
            Holiday.objects.filter(date__range=(self.start_date, self.end_date)).values_list("date", flat=True)
        )
        return lct.count_days(
            self.start_date,
            self.end_date,
            business_days=self.leave_type.day_count == LeaveType.DayCount.HABILES,
            holidays=holidays,
            include_saturday=self.employee.works_saturday,
        )

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "La fecha hasta no puede ser anterior a la fecha desde."})
        if self.half_day and self.start_date != self.end_date:
            raise ValidationError({"half_day": "El medio día solo aplica a solicitudes de un día."})
        if not (self.start_date and self.end_date and self.employee_id and self.leave_type_id):
            return
        overlap = LeaveRequest.objects.filter(
            employee_id=self.employee_id,
            status__in=[self.Status.PENDIENTE, self.Status.APROBADA],
            start_date__lte=self.end_date,
            end_date__gte=self.start_date,
        ).exclude(pk=self.pk)
        if overlap.exists():
            raise ValidationError("Ya existe una solicitud pendiente o aprobada que se superpone con estas fechas.")
        days = self.compute_days()
        lt = self.leave_type
        if lt.days_per_event and days > lt.days_per_event:
            raise ValidationError(f"«{lt}» admite como máximo {lt.days_per_event} días por solicitud.")
        if lt.requires_attachment and not self.attachment and self.status == self.Status.APROBADA:
            raise ValidationError({"attachment": "Este tipo de licencia requiere comprobante para aprobarse."})
        if lt.days_per_year and not lt.tracks_balance:
            used = LeaveRequest.days_used(self.employee, lt, self.period, exclude_pk=self.pk)
            if used + days > lt.days_per_year:
                raise ValidationError(
                    f"Supera el tope anual de {lt.days_per_year} días para «{lt}» (ya utilizados: {used})."
                )
        if lt.tracks_balance:
            balance = LeaveBalance.objects.filter(employee_id=self.employee_id, leave_type=lt, year=self.period).first()
            available = balance.available if balance else 0
            if self.pk:
                stored = LeaveRequest.objects.filter(pk=self.pk, status=self.Status.APROBADA).first()
                if stored and stored.period == self.period:
                    available += stored.days
            if days > available:
                raise ValidationError(
                    f"Saldo insuficiente: solicita {days} días y tiene {available} disponibles del período {self.period}."
                )

    def save(self, *args, **kwargs):
        if self.start_date and self.end_date and self.leave_type_id and self.employee_id:
            self.days = self.compute_days()
        super().save(*args, **kwargs)

    @classmethod
    def days_used(cls, employee, leave_type, year, statuses=None, exclude_pk=None):
        statuses = statuses or [cls.Status.APROBADA]
        qs = cls.objects.filter(employee=employee, leave_type=leave_type, status__in=statuses).filter(
            models.Q(period_year=year) | models.Q(period_year__isnull=True, start_date__year=year)
        )
        if exclude_pk:
            qs = qs.exclude(pk=exclude_pk)
        return qs.aggregate(t=models.Sum("days"))["t"] or 0

    def warnings(self):
        """Advertencias no bloqueantes (para mostrar al aprobar)."""
        from apps.core.models import CompanySettings

        out = []
        cfg = CompanySettings.get()
        if self.leave_type.is_vacation:
            if self.days < cfg.vacation_min_block_days:
                out.append(
                    f"Tramo de {self.days} días: el art. 154 LCT (Ley 27.802) exige tramos de al menos "
                    f"{cfg.vacation_min_block_days} días corridos cuando se fraccionan."
                )
            notice = (self.start_date - self.created_at.date()).days if self.created_at else None
            if notice is not None and notice < cfg.vacation_notice_days:
                out.append(f"Se solicitó con {notice} días de anticipación (preaviso legal: {cfg.vacation_notice_days}).")
        if self.leave_type.requires_attachment and not self.attachment:
            out.append("Falta el comprobante requerido.")
        return out

    def can_be_reviewed_by(self, user):
        from apps.core.modules import Level, Module

        if user.can(Module.LICENCIAS, Level.ADMINISTRAR):
            return True
        own = getattr(user, "employee", None)
        return bool(own and self.employee.manager_id == own.pk and own.pk != self.employee_id)

    @property
    def is_current(self):
        today = datetime.date.today()
        return self.status == self.Status.APROBADA and self.start_date <= today <= self.end_date
