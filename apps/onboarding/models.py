import datetime

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.empleados.models import Employee


class Kind(models.TextChoices):
    ONBOARDING = "onboarding", "Onboarding (ingreso)"
    OFFBOARDING = "offboarding", "Offboarding (egreso)"


class ChecklistTemplate(models.Model):
    name = models.CharField("nombre", max_length=120)
    kind = models.CharField("tipo", max_length=12, choices=Kind.choices, default=Kind.ONBOARDING)
    description = models.TextField("descripción", blank=True)
    active = models.BooleanField("activa", default=True)

    class Meta:
        verbose_name = "plantilla de checklist"
        verbose_name_plural = "plantillas de checklist"
        ordering = ["kind", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()})"


class TemplateTask(models.Model):
    template = models.ForeignKey(ChecklistTemplate, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField("tarea", max_length=200)
    description = models.TextField("detalle", blank=True)
    responsible = models.CharField("responsable sugerido", max_length=100, blank=True, help_text="Ej.: RRHH, IT, Jefe directo")
    default_assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="asignar a"
    )
    due_offset_days = models.IntegerField(
        "plazo (días)", default=0, help_text="Días respecto de la fecha de inicio. Negativo = antes del ingreso/egreso."
    )
    order = models.PositiveIntegerField("orden", default=0)

    class Meta:
        verbose_name = "tarea de plantilla"
        verbose_name_plural = "tareas de plantilla"
        ordering = ["order", "id"]

    def __str__(self):
        return self.title


class EmployeeChecklist(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="checklists", verbose_name="empleado")
    name = models.CharField("nombre", max_length=120)
    kind = models.CharField("tipo", max_length=12, choices=Kind.choices)
    start_date = models.DateField("fecha de referencia", help_text="Fecha de ingreso o de egreso.")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "checklist de empleado"
        verbose_name_plural = "checklists de empleados"
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.name} - {self.employee}"

    @property
    def progress(self):
        total = self.tasks.count()
        if not total:
            return 100
        return round(self.tasks.filter(done=True).count() * 100 / total)

    @property
    def is_complete(self):
        return not self.tasks.filter(done=False).exists()

    @classmethod
    def from_template(cls, template, employee, start_date, user=None):
        checklist = cls.objects.create(
            employee=employee, name=template.name, kind=template.kind, start_date=start_date, created_by=user
        )
        for t in template.tasks.all():
            ChecklistTask.objects.create(
                checklist=checklist,
                title=t.title,
                description=t.description,
                responsible=t.responsible,
                assignee=t.default_assignee,
                due_date=start_date + datetime.timedelta(days=t.due_offset_days),
                order=t.order,
            )
        return checklist


class ChecklistTask(models.Model):
    checklist = models.ForeignKey(EmployeeChecklist, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField("tarea", max_length=200)
    description = models.TextField("detalle", blank=True)
    responsible = models.CharField("responsable", max_length=100, blank=True)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="asignada a"
    )
    due_date = models.DateField("vence", null=True, blank=True)
    done = models.BooleanField("realizada", default=False)
    done_at = models.DateTimeField(null=True, blank=True)
    done_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "tarea"
        verbose_name_plural = "tareas"
        ordering = ["order", "due_date", "id"]

    def __str__(self):
        return self.title

    def toggle(self, user):
        self.done = not self.done
        self.done_at = timezone.now() if self.done else None
        self.done_by = user if self.done else None
        self.save()

    @property
    def is_overdue(self):
        return not self.done and self.due_date and self.due_date < datetime.date.today()
