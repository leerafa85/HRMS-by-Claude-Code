import datetime
import os

from django.conf import settings
from django.db import models

from apps.core.uploads import UploadTo
from apps.core.validators import (
    validate_cbu,
    validate_cuil,
    validate_document,
    validate_image,
)

PROVINCIAS = [
    ("CABA", "Ciudad Autónoma de Buenos Aires"),
    ("BA", "Buenos Aires"),
    ("CA", "Catamarca"),
    ("CH", "Chaco"),
    ("CT", "Chubut"),
    ("CB", "Córdoba"),
    ("CR", "Corrientes"),
    ("ER", "Entre Ríos"),
    ("FO", "Formosa"),
    ("JY", "Jujuy"),
    ("LP", "La Pampa"),
    ("LR", "La Rioja"),
    ("MZ", "Mendoza"),
    ("MI", "Misiones"),
    ("NQ", "Neuquén"),
    ("RN", "Río Negro"),
    ("SA", "Salta"),
    ("SJ", "San Juan"),
    ("SL", "San Luis"),
    ("SC", "Santa Cruz"),
    ("SF", "Santa Fe"),
    ("SE", "Santiago del Estero"),
    ("TF", "Tierra del Fuego"),
    ("TU", "Tucumán"),
]


upload_photo = UploadTo("empleados/fotos")
upload_document = UploadTo("empleados/documentos")
upload_salary = UploadTo("empleados/salarios")


class Department(models.Model):
    name = models.CharField("nombre", max_length=100, unique=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children", verbose_name="área superior"
    )
    head = models.ForeignKey(
        "Employee", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="responsable"
    )
    cost_center = models.CharField("centro de costo", max_length=30, blank=True)

    class Meta:
        verbose_name = "área / departamento"
        verbose_name_plural = "áreas / departamentos"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Location(models.Model):
    name = models.CharField("nombre", max_length=100, unique=True)
    address = models.CharField("domicilio", max_length=200, blank=True)
    city = models.CharField("localidad", max_length=100, blank=True)
    province = models.CharField("provincia", max_length=4, choices=PROVINCIAS, default="CABA")

    class Meta:
        verbose_name = "sucursal / sede"
        verbose_name_plural = "sucursales / sedes"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Position(models.Model):
    name = models.CharField("nombre", max_length=100)
    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.SET_NULL, related_name="positions", verbose_name="área"
    )
    description = models.TextField("descripción / responsabilidades", blank=True)

    class Meta:
        verbose_name = "puesto"
        verbose_name_plural = "puestos"
        ordering = ["name"]
        unique_together = ("name", "department")

    def __str__(self):
        return self.name


class Employee(models.Model):
    class Status(models.TextChoices):
        ACTIVO = "activo", "Activo"
        PRUEBA = "prueba", "En período de prueba"
        LICENCIA = "licencia", "En licencia prolongada"
        DESVINCULADO = "baja", "Desvinculado"

    class ContractType(models.TextChoices):
        INDETERMINADO = "indeterminado", "Tiempo indeterminado"
        PLAZO_FIJO = "plazo_fijo", "Plazo fijo"
        EVENTUAL = "eventual", "Eventual"
        TEMPORADA = "temporada", "De temporada"
        PARCIAL = "parcial", "Tiempo parcial"
        PASANTIA = "pasantia", "Pasantía"
        MONOTRIBUTO = "monotributo", "Contratado / monotributista"

    class PayType(models.TextChoices):
        MENSUAL = "mensual", "Mensualizado"
        JORNAL = "jornal", "Jornalizado"
        HORA = "hora", "Por hora"

    class Gender(models.TextChoices):
        F = "F", "Femenino"
        M = "M", "Masculino"
        X = "X", "No binario / X"

    class MaritalStatus(models.TextChoices):
        SOLTERO = "soltero", "Soltero/a"
        CASADO = "casado", "Casado/a"
        CONVIVIENTE = "conviviente", "Unión convivencial"
        DIVORCIADO = "divorciado", "Divorciado/a"
        VIUDO = "viudo", "Viudo/a"

    class TerminationReason(models.TextChoices):
        RENUNCIA = "renuncia", "Renuncia"
        DESPIDO_SIN_CAUSA = "despido_sc", "Despido sin causa"
        DESPIDO_CON_CAUSA = "despido_cc", "Despido con causa"
        MUTUO_ACUERDO = "mutuo", "Mutuo acuerdo (art. 241 LCT)"
        FIN_CONTRATO = "fin_contrato", "Fin de contrato"
        PERIODO_PRUEBA = "prueba", "Extinción en período de prueba"
        JUBILACION = "jubilacion", "Jubilación"
        FALLECIMIENTO = "fallecimiento", "Fallecimiento"
        OTRO = "otro", "Otro"

    # Identificación
    file_number = models.CharField("legajo", max_length=20, unique=True)
    first_name = models.CharField("nombre/s", max_length=100)
    last_name = models.CharField("apellido/s", max_length=100)
    photo = models.ImageField("foto", upload_to=upload_photo, blank=True, validators=[validate_image])
    dni = models.CharField("DNI", max_length=12, unique=True)
    cuil = models.CharField("CUIL", max_length=13, unique=True, validators=[validate_cuil])
    birth_date = models.DateField("fecha de nacimiento", null=True, blank=True)
    gender = models.CharField("género", max_length=1, choices=Gender.choices, blank=True)
    marital_status = models.CharField("estado civil", max_length=15, choices=MaritalStatus.choices, blank=True)
    nationality = models.CharField("nacionalidad", max_length=50, default="Argentina")

    # Contacto
    personal_email = models.EmailField("email personal", blank=True)
    work_email = models.EmailField("email laboral", blank=True)
    phone = models.CharField("teléfono", max_length=30, blank=True)
    mobile = models.CharField("celular", max_length=30, blank=True)
    address = models.CharField("domicilio", max_length=200, blank=True)
    city = models.CharField("localidad", max_length=100, blank=True)
    province = models.CharField("provincia", max_length=4, choices=PROVINCIAS, blank=True)
    postal_code = models.CharField("código postal", max_length=10, blank=True)

    # Datos laborales
    status = models.CharField("estado", max_length=15, choices=Status.choices, default=Status.ACTIVO)
    hire_date = models.DateField("fecha de ingreso")
    seniority_date = models.DateField(
        "fecha de antigüedad reconocida",
        null=True,
        blank=True,
        help_text="Si se reconoce antigüedad anterior. Si queda vacío se usa la fecha de ingreso.",
    )
    trial_end_date = models.DateField("fin del período de prueba", null=True, blank=True)
    contract_type = models.CharField(
        "modalidad de contratación", max_length=20, choices=ContractType.choices, default=ContractType.INDETERMINADO
    )
    contract_end_date = models.DateField("fin de contrato", null=True, blank=True)
    pay_type = models.CharField("modalidad de pago", max_length=10, choices=PayType.choices, default=PayType.MENSUAL)
    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.SET_NULL, related_name="employees", verbose_name="área"
    )
    position = models.ForeignKey(
        Position, null=True, blank=True, on_delete=models.SET_NULL, related_name="employees", verbose_name="puesto"
    )
    location = models.ForeignKey(
        Location, null=True, blank=True, on_delete=models.SET_NULL, related_name="employees", verbose_name="sede"
    )
    manager = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="reports", verbose_name="jefe directo"
    )
    weekly_hours = models.DecimalField("horas semanales", max_digits=5, decimal_places=2, default=45)
    start_time = models.TimeField("hora de entrada", null=True, blank=True, help_text="Vacío = horario de la empresa.")
    end_time = models.TimeField("hora de salida", null=True, blank=True)
    works_saturday = models.BooleanField("trabaja sábados", default=False)

    # Encuadre
    union_agreement = models.CharField("convenio colectivo (CCT)", max_length=100, blank=True, help_text="Ej.: 130/75 Comercio")
    category = models.CharField("categoría", max_length=100, blank=True)
    union = models.CharField("sindicato", max_length=100, blank=True)
    health_insurance = models.CharField("obra social", max_length=100, blank=True)
    health_plan = models.CharField("prepaga / plan", max_length=100, blank=True)

    # Pago
    bank = models.CharField("banco", max_length=80, blank=True)
    cbu = models.CharField("CBU / CVU", max_length=22, blank=True, validators=[validate_cbu])
    bank_alias = models.CharField("alias", max_length=50, blank=True)

    # Baja
    termination_date = models.DateField("fecha de egreso", null=True, blank=True)
    termination_reason = models.CharField(
        "motivo de egreso", max_length=20, choices=TerminationReason.choices, blank=True
    )
    termination_notes = models.TextField("observaciones del egreso", blank=True)

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="employee",
        verbose_name="usuario del sistema",
    )
    notes = models.TextField("observaciones", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "empleado"
        verbose_name_plural = "empleados"
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.last_name}, {self.first_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def initials(self):
        return (self.first_name[:1] + self.last_name[:1]).upper()

    @property
    def is_active(self):
        return self.status != self.Status.DESVINCULADO

    @property
    def age(self):
        if not self.birth_date:
            return None
        today = datetime.date.today()
        return today.year - self.birth_date.year - ((today.month, today.day) < (self.birth_date.month, self.birth_date.day))

    @property
    def seniority_start(self):
        return self.seniority_date or self.hire_date

    def seniority_years(self, at=None):
        """Años completos de antigüedad a la fecha indicada."""
        at = at or datetime.date.today()
        start = self.seniority_start
        if at < start:
            return 0
        return at.year - start.year - ((at.month, at.day) < (start.month, start.day))

    @property
    def seniority_display(self):
        today = datetime.date.today()
        start = self.seniority_start
        months = (today.year - start.year) * 12 + today.month - start.month - (today.day < start.day)
        if months < 0:
            return "Ingreso futuro"
        years, months = divmod(months, 12)
        parts = []
        if years:
            parts.append(f"{years} año{'s' if years != 1 else ''}")
        parts.append(f"{months} mes{'es' if months != 1 else ''}")
        return " y ".join(parts)

    @property
    def current_salary(self):
        adj = self.salary_adjustments.filter(effective_date__lte=datetime.date.today()).order_by(
            "-effective_date", "-id"
        ).first()
        return adj.new_salary if adj else None

    @property
    def dependents_count(self):
        return self.family_members.filter(dependent=True).count()

    def effective_start_time(self):
        if self.start_time:
            return self.start_time
        from apps.core.models import CompanySettings

        return CompanySettings.get().default_start_time


class EmergencyContact(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="emergency_contacts")
    name = models.CharField("nombre", max_length=120)
    relationship = models.CharField("vínculo", max_length=50)
    phone = models.CharField("teléfono", max_length=30)
    notes = models.CharField("observaciones", max_length=200, blank=True)

    class Meta:
        verbose_name = "contacto de emergencia"
        verbose_name_plural = "contactos de emergencia"

    def __str__(self):
        return f"{self.name} ({self.relationship})"


class FamilyMember(models.Model):
    class Relationship(models.TextChoices):
        CONYUGE = "conyuge", "Cónyuge / conviviente"
        HIJO = "hijo", "Hijo/a"
        PADRE = "padre", "Padre / madre"
        HERMANO = "hermano", "Hermano/a"
        OTRO = "otro", "Otro"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="family_members")
    name = models.CharField("nombre y apellido", max_length=150)
    relationship = models.CharField("vínculo", max_length=10, choices=Relationship.choices)
    dni = models.CharField("DNI", max_length=12, blank=True)
    birth_date = models.DateField("fecha de nacimiento", null=True, blank=True)
    dependent = models.BooleanField("a cargo", default=False, help_text="Familiar a cargo (art. 208 LCT / asignaciones).")
    disability = models.BooleanField("con discapacidad (CUD)", default=False)

    class Meta:
        verbose_name = "familiar"
        verbose_name_plural = "grupo familiar"

    def __str__(self):
        return f"{self.name} ({self.get_relationship_display()})"


class EmployeeDocument(models.Model):
    class Category(models.TextChoices):
        DNI = "dni", "DNI"
        CUIL = "cuil", "Constancia de CUIL"
        ALTA = "alta", "Alta temprana AFIP/ARCA"
        CONTRATO = "contrato", "Contrato / acuerdo"
        CV = "cv", "Currículum"
        TITULO = "titulo", "Título / certificado de estudios"
        MEDICO = "medico", "Certificado médico"
        PREOCUPACIONAL = "preocupacional", "Examen preocupacional"
        RECIBO = "recibo", "Recibo de sueldo"
        FAMILIA = "familia", "Partida / documentación familiar"
        DOMICILIO = "domicilio", "Constancia de domicilio"
        SANCION = "sancion", "Apercibimiento / sanción"
        TELEGRAMA = "telegrama", "Telegrama / carta documento"
        CAPACITACION = "capacitacion", "Capacitación"
        FOTO = "foto", "Fotografía"
        OTRO = "otro", "Otro"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="documents", verbose_name="empleado")
    category = models.CharField("categoría", max_length=20, choices=Category.choices, default=Category.OTRO)
    title = models.CharField("título", max_length=150)
    file = models.FileField("archivo", upload_to=upload_document, validators=[validate_document])
    issue_date = models.DateField("fecha del documento", null=True, blank=True)
    expiry_date = models.DateField("vencimiento", null=True, blank=True)
    visible_to_employee = models.BooleanField("visible para el empleado", default=True)
    notes = models.TextField("observaciones", blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="cargado por"
    )
    created_at = models.DateTimeField("fecha de carga", auto_now_add=True)

    class Meta:
        verbose_name = "documento"
        verbose_name_plural = "documentos"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} - {self.employee}"

    @property
    def filename(self):
        return os.path.basename(self.file.name)

    @property
    def is_image(self):
        return os.path.splitext(self.file.name)[1].lower() in (".jpg", ".jpeg", ".png", ".webp")

    @property
    def is_expired(self):
        return bool(self.expiry_date and self.expiry_date < datetime.date.today())


class SalaryAdjustment(models.Model):
    class Reason(models.TextChoices):
        INGRESO = "ingreso", "Salario de ingreso"
        PARITARIA = "paritaria", "Paritaria / acuerdo CCT"
        MERITO = "merito", "Mérito / desempeño"
        PROMOCION = "promocion", "Promoción / cambio de puesto"
        INFLACION = "inflacion", "Ajuste por inflación"
        RECATEGORIZACION = "recategorizacion", "Recategorización"
        ACUERDO = "acuerdo", "Acuerdo individual"
        CORRECCION = "correccion", "Corrección"
        OTRO = "otro", "Otro"

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="salary_adjustments", verbose_name="empleado"
    )
    effective_date = models.DateField("vigencia desde")
    previous_salary = models.DecimalField("salario anterior ($)", max_digits=14, decimal_places=2, null=True, blank=True)
    new_salary = models.DecimalField("nuevo salario bruto ($)", max_digits=14, decimal_places=2)
    reason = models.CharField("motivo", max_length=20, choices=Reason.choices, default=Reason.PARITARIA)
    notes = models.TextField("observaciones", blank=True)
    attachment = models.FileField(
        "respaldo", upload_to=upload_salary, blank=True, validators=[validate_document],
        help_text="Acta, acuerdo firmado, etc.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="registrado por"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "ajuste salarial"
        verbose_name_plural = "ajustes salariales"
        ordering = ["-effective_date", "-id"]

    def __str__(self):
        return f"{self.employee} - {self.effective_date:%d/%m/%Y}"

    def save(self, *args, **kwargs):
        if self.previous_salary is None and self.employee_id:
            prev = (
                SalaryAdjustment.objects.filter(employee_id=self.employee_id, effective_date__lte=self.effective_date)
                .exclude(pk=self.pk)
                .order_by("-effective_date", "-id")
                .first()
            )
            self.previous_salary = prev.new_salary if prev else None
        super().save(*args, **kwargs)

    @property
    def variation_pct(self):
        if not self.previous_salary:
            return None
        return (self.new_salary - self.previous_salary) / self.previous_salary * 100
