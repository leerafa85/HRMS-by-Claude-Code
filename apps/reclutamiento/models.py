
from django.conf import settings
from django.db import models

from apps.core.uploads import UploadTo
from apps.core.validators import validate_document
from apps.empleados.models import Department, Employee, Location, Position

upload_cv = UploadTo("reclutamiento/cv")


class JobOpening(models.Model):
    class Status(models.TextChoices):
        BORRADOR = "borrador", "Borrador"
        ABIERTA = "abierta", "Abierta"
        PAUSA = "pausa", "En pausa"
        CERRADA = "cerrada", "Cerrada (cubierta)"
        CANCELADA = "cancelada", "Cancelada"

    class Modality(models.TextChoices):
        PRESENCIAL = "presencial", "Presencial"
        HIBRIDO = "hibrido", "Híbrido"
        REMOTO = "remoto", "Remoto"

    title = models.CharField("puesto buscado", max_length=150)
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="área")
    position = models.ForeignKey(Position, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="puesto")
    location = models.ForeignKey(Location, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="sede")
    modality = models.CharField("modalidad", max_length=12, choices=Modality.choices, default=Modality.PRESENCIAL)
    contract_type = models.CharField(
        "contratación", max_length=20, choices=Employee.ContractType.choices, default=Employee.ContractType.INDETERMINADO
    )
    vacancies = models.PositiveIntegerField("vacantes", default=1)
    description = models.TextField("descripción")
    requirements = models.TextField("requisitos", blank=True)
    benefits = models.TextField("beneficios", blank=True)
    salary_min = models.DecimalField("salario desde ($)", max_digits=14, decimal_places=2, null=True, blank=True)
    salary_max = models.DecimalField("salario hasta ($)", max_digits=14, decimal_places=2, null=True, blank=True)
    show_salary = models.BooleanField("mostrar salario en la publicación", default=False)
    hiring_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="responsable de la búsqueda",
    )
    status = models.CharField("estado", max_length=12, choices=Status.choices, default=Status.BORRADOR)
    published = models.BooleanField("publicar en portal de empleos", default=False)
    closing_date = models.DateField("fecha de cierre", null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField("creada", auto_now_add=True)

    class Meta:
        verbose_name = "búsqueda"
        verbose_name_plural = "búsquedas"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    @property
    def is_public(self):
        return self.published and self.status == self.Status.ABIERTA


class Candidate(models.Model):
    class Source(models.TextChoices):
        PORTAL = "portal", "Portal de empleos propio"
        LINKEDIN = "linkedin", "LinkedIn"
        BUMERAN = "bumeran", "Bumeran"
        ZONAJOBS = "zonajobs", "ZonaJobs"
        COMPUTRABAJO = "computrabajo", "Computrabajo"
        REFERIDO = "referido", "Referido"
        CONSULTORA = "consultora", "Consultora"
        UNIVERSIDAD = "universidad", "Universidad"
        OTRO = "otro", "Otro"

    first_name = models.CharField("nombre", max_length=100)
    last_name = models.CharField("apellido", max_length=100)
    email = models.EmailField("email")
    phone = models.CharField("teléfono", max_length=30, blank=True)
    dni = models.CharField("DNI", max_length=12, blank=True)
    city = models.CharField("localidad", max_length=100, blank=True)
    linkedin = models.URLField("LinkedIn", blank=True)
    resume = models.FileField("CV", upload_to=upload_cv, blank=True, validators=[validate_document])
    source = models.CharField("fuente", max_length=15, choices=Source.choices, default=Source.OTRO)
    referred_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="referrals", verbose_name="referido por"
    )
    expected_salary = models.DecimalField("pretensión salarial ($)", max_digits=14, decimal_places=2, null=True, blank=True)
    tags = models.CharField("etiquetas", max_length=200, blank=True, help_text="Separadas por coma.")
    notes = models.TextField("notas", blank=True)
    consent = models.BooleanField("consiente tratamiento de datos (Ley 25.326)", default=False)
    created_at = models.DateTimeField("alta", auto_now_add=True)

    class Meta:
        verbose_name = "candidato"
        verbose_name_plural = "candidatos"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.last_name}, {self.first_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class Application(models.Model):
    class Stage(models.TextChoices):
        NUEVO = "nuevo", "Nuevo"
        PRESELECCION = "preseleccion", "Preselección"
        ENTREVISTA_RRHH = "entrevista_rrhh", "Entrevista RRHH"
        ENTREVISTA_TECNICA = "entrevista_tec", "Entrevista técnica / líder"
        EVALUACION = "evaluacion", "Evaluación / psicotécnico"
        OFERTA = "oferta", "Oferta"
        CONTRATADO = "contratado", "Contratado"
        DESCARTADO = "descartado", "Descartado"

    PIPELINE = [
        Stage.NUEVO, Stage.PRESELECCION, Stage.ENTREVISTA_RRHH, Stage.ENTREVISTA_TECNICA,
        Stage.EVALUACION, Stage.OFERTA, Stage.CONTRATADO, Stage.DESCARTADO,
    ]

    job = models.ForeignKey(JobOpening, on_delete=models.CASCADE, related_name="applications", verbose_name="búsqueda")
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="applications", verbose_name="candidato")
    stage = models.CharField("etapa", max_length=20, choices=Stage.choices, default=Stage.NUEVO)
    rating = models.PositiveSmallIntegerField("valoración (1-5)", null=True, blank=True)
    discard_reason = models.CharField("motivo de descarte", max_length=200, blank=True)
    offer_salary = models.DecimalField("salario ofrecido ($)", max_digits=14, decimal_places=2, null=True, blank=True)
    offer_start_date = models.DateField("fecha de ingreso propuesta", null=True, blank=True)
    notes = models.TextField("notas", blank=True)
    hired_employee = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="empleado creado"
    )
    created_at = models.DateTimeField("postulación", auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "postulación"
        verbose_name_plural = "postulaciones"
        unique_together = ("job", "candidate")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.candidate} → {self.job}"


class Interview(models.Model):
    class Mode(models.TextChoices):
        PRESENCIAL = "presencial", "Presencial"
        VIDEO = "video", "Videollamada"
        TELEFONO = "telefono", "Telefónica"

    class Result(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        AVANZA = "avanza", "Avanza"
        NO_AVANZA = "no_avanza", "No avanza"
        AUSENTE = "ausente", "No se presentó"

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="interviews", verbose_name="postulación")
    scheduled_at = models.DateTimeField("fecha y hora")
    mode = models.CharField("modalidad", max_length=12, choices=Mode.choices, default=Mode.VIDEO)
    location_or_link = models.CharField("lugar / link", max_length=250, blank=True)
    interviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="entrevistador"
    )
    score = models.PositiveSmallIntegerField("puntaje (1-5)", null=True, blank=True)
    feedback = models.TextField("devolución", blank=True)
    result = models.CharField("resultado", max_length=12, choices=Result.choices, default=Result.PENDIENTE)

    class Meta:
        verbose_name = "entrevista"
        verbose_name_plural = "entrevistas"
        ordering = ["scheduled_at"]

    def __str__(self):
        return f"Entrevista {self.application.candidate} {self.scheduled_at:%d/%m/%Y %H:%M}"
