import datetime
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.uploads import UploadTo
from apps.core.validators import validate_document
from apps.empleados.models import Employee

upload_attendance = UploadTo("asistencia")


class Absence(models.Model):
    class Reason(models.TextChoices):
        ENFERMEDAD = "enfermedad", "Enfermedad (sin licencia cargada)"
        PERSONAL = "personal", "Razones personales"
        TRAMITE = "tramite", "Trámite"
        FAMILIAR = "familiar", "Atención de familiar"
        TRANSPORTE = "transporte", "Problemas de transporte / paro"
        CLIMA = "clima", "Fenómeno climático"
        SIN_AVISO = "sin_aviso", "Sin aviso"
        OTRO = "otro", "Otro"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="absences", verbose_name="empleado")
    date = models.DateField("fecha")
    reason = models.CharField("motivo", max_length=15, choices=Reason.choices, default=Reason.PERSONAL)
    justified = models.BooleanField("justificada", default=False)
    paid = models.BooleanField("con goce", default=False, help_text="Si se abona el día (justificadas con goce).")
    notified = models.BooleanField("dio aviso", default=True)
    attachment = models.FileField("comprobante", upload_to=upload_attendance, blank=True, validators=[validate_document])
    notes = models.TextField("observaciones", blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="registrado por"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "inasistencia"
        verbose_name_plural = "inasistencias"
        ordering = ["-date"]
        unique_together = ("employee", "date")

    def __str__(self):
        return f"{self.employee} - {self.date:%d/%m/%Y}"


class Tardiness(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="tardies", verbose_name="empleado")
    date = models.DateField("fecha")
    scheduled_time = models.TimeField("hora de entrada pactada", null=True, blank=True)
    arrival_time = models.TimeField("hora de llegada")
    minutes_late = models.PositiveIntegerField("minutos de demora", default=0, editable=False)
    justified = models.BooleanField("justificada", default=False)
    notes = models.CharField("observaciones", max_length=250, blank=True)
    attachment = models.FileField("comprobante", upload_to=upload_attendance, blank=True, validators=[validate_document])
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="registrado por"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "llegada tarde"
        verbose_name_plural = "llegadas tarde"
        ordering = ["-date"]
        unique_together = ("employee", "date")

    def __str__(self):
        return f"{self.employee} - {self.date:%d/%m/%Y} ({self.minutes_late} min)"

    def clean(self):
        sched = self.scheduled_time or (self.employee.effective_start_time() if self.employee_id else None)
        if sched and self.arrival_time and self.arrival_time <= sched:
            raise ValidationError({"arrival_time": "La hora de llegada no es posterior a la hora de entrada."})

    def save(self, *args, **kwargs):
        if not self.scheduled_time:
            self.scheduled_time = self.employee.effective_start_time()
        base = datetime.datetime.combine(self.date, self.scheduled_time)
        arrival = datetime.datetime.combine(self.date, self.arrival_time)
        self.minutes_late = max(0, int((arrival - base).total_seconds() // 60))
        super().save(*args, **kwargs)


class Overtime(models.Model):
    class Status(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        APROBADA = "aprobada", "Aprobada"
        RECHAZADA = "rechazada", "Rechazada"

    class Rate(models.IntegerChoices):
        R50 = 50, "50 %"
        R100 = 100, "100 %"

    class Compensation(models.TextChoices):
        PAGO = "pago", "Pago con recargo"
        BANCO = "banco", "Banco de horas (compensación)"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="overtimes", verbose_name="empleado")
    date = models.DateField("fecha")
    start_time = models.TimeField("desde", null=True, blank=True)
    end_time = models.TimeField("hasta", null=True, blank=True)
    hours = models.DecimalField(
        "horas", max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Si se completan desde/hasta y se deja vacío, se calcula automáticamente.",
    )
    rate = models.PositiveSmallIntegerField(
        "recargo", choices=Rate.choices, null=True, blank=True,
        help_text="Vacío = se calcula: 50 % días comunes; 100 % sábados desde las 13 h, domingos y feriados.",
    )
    compensation = models.CharField("compensación", max_length=10, choices=Compensation.choices, default=Compensation.PAGO)
    reason = models.CharField("motivo / tarea", max_length=250, blank=True)
    attachment = models.FileField("comprobante", upload_to=upload_attendance, blank=True, validators=[validate_document])
    status = models.CharField("estado", max_length=10, choices=Status.choices, default=Status.PENDIENTE)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="aprobado por",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="registrado por",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "horas extras"
        verbose_name_plural = "horas extras"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.employee} - {self.date:%d/%m/%Y} {self.hours} h al {self.rate}%"

    def clean(self):
        if self.hours is None and self.start_time and self.end_time:
            start = datetime.datetime.combine(self.date or datetime.date.today(), self.start_time)
            end = datetime.datetime.combine(self.date or datetime.date.today(), self.end_time)
            if end <= start:
                end += datetime.timedelta(days=1)
            self.hours = round(Decimal((end - start).total_seconds()) / Decimal(3600), 2)
        if self.hours is None:
            raise ValidationError({"hours": "Indicá la cantidad de horas o el horario desde/hasta."})
        if self.hours <= 0:
            raise ValidationError({"hours": "Las horas deben ser mayores a cero."})

    def save(self, *args, **kwargs):
        from apps.licencias.lct import overtime_rate
        from apps.licencias.models import Holiday

        if not self.rate:
            holiday = Holiday.objects.filter(date=self.date).first()
            self.rate = overtime_rate(self.date, self.start_time, bool(holiday and holiday.is_paid_holiday))
        super().save(*args, **kwargs)
