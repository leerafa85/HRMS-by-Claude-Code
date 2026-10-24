from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models

from .modules import Level, Module


class Role(models.Model):
    name = models.CharField("nombre", max_length=80, unique=True)
    description = models.TextField("descripción", blank=True)

    class Meta:
        verbose_name = "rol"
        verbose_name_plural = "roles"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def level_for(self, module):
        perm = next((p for p in self.permissions.all() if p.module == module), None)
        return perm.level if perm else Level.NINGUNO


class RolePermission(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="permissions")
    module = models.CharField("módulo", max_length=30, choices=Module.choices)
    level = models.PositiveSmallIntegerField("nivel", choices=Level.choices, default=Level.NINGUNO)

    class Meta:
        verbose_name = "permiso de rol"
        verbose_name_plural = "permisos de rol"
        unique_together = ("role", "module")

    def __str__(self):
        return f"{self.role} · {self.get_module_display()}: {self.get_level_display()}"


class User(AbstractUser):
    roles = models.ManyToManyField(Role, blank=True, related_name="users", verbose_name="roles")

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
        ordering = ["username"]

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def is_hrms_admin(self):
        return self.is_superuser

    def module_level(self, module):
        """Nivel efectivo: el máximo entre todos los roles del usuario."""
        if not self.is_active:
            return Level.NINGUNO
        if self.is_superuser:
            return Level.ADMINISTRAR
        cache = getattr(self, "_module_levels", None)
        if cache is None:
            cache = {}
            for perm in RolePermission.objects.filter(role__users=self):
                cache[perm.module] = max(cache.get(perm.module, 0), perm.level)
            self._module_levels = cache
        return cache.get(module, Level.NINGUNO)

    def can(self, module, level=Level.VER):
        return self.module_level(module) >= level

    @property
    def employee_or_none(self):
        return getattr(self, "employee", None)


class CompanySettings(models.Model):
    """Datos de la empresa y parámetros generales (registro único)."""

    name = models.CharField("razón social", max_length=150, default="Mi Empresa S.A.")
    trade_name = models.CharField("nombre de fantasía", max_length=150, blank=True)
    cuit = models.CharField("CUIT", max_length=13, blank=True)
    address = models.CharField("domicilio", max_length=200, blank=True)
    phone = models.CharField("teléfono", max_length=50, blank=True)
    email = models.EmailField("email de RRHH", blank=True)
    logo = models.ImageField("logo", upload_to="empresa/", blank=True)
    art = models.CharField("ART", max_length=100, blank=True)
    default_start_time = models.TimeField("hora de entrada por defecto", default="09:00")
    daily_hours = models.DecimalField("horas por jornada", max_digits=4, decimal_places=2, default=8)
    late_tolerance_minutes = models.PositiveIntegerField("tolerancia de llegada tarde (min)", default=5)
    vacation_min_block_days = models.PositiveIntegerField(
        "tramo mínimo de vacaciones fraccionadas (días)",
        default=7,
        help_text="Art. 154 LCT según Ley 27.802: cada tramo fraccionado debe ser de al menos 7 días corridos.",
    )
    vacation_notice_days = models.PositiveIntegerField(
        "preaviso de vacaciones (días)", default=30, help_text="Art. 154 LCT (Ley 27.802): 30 días de anticipación."
    )

    class Meta:
        verbose_name = "configuración de la empresa"
        verbose_name_plural = "configuración de la empresa"

    def __str__(self):
        return self.trade_name or self.name

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class AuditLog(models.Model):
    class Action(models.TextChoices):
        CREATE = "crear", "Alta"
        UPDATE = "editar", "Modificación"
        DELETE = "eliminar", "Baja"
        APPROVE = "aprobar", "Aprobación"
        REJECT = "rechazar", "Rechazo"
        LOGIN = "login", "Inicio de sesión"
        OTHER = "otro", "Otro"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, verbose_name="usuario")
    action = models.CharField("acción", max_length=20, choices=Action.choices)
    model = models.CharField("entidad", max_length=100)
    object_id = models.CharField(max_length=50, blank=True)
    description = models.CharField("detalle", max_length=300)
    created_at = models.DateTimeField("fecha", auto_now_add=True)

    class Meta:
        verbose_name = "registro de auditoría"
        verbose_name_plural = "auditoría"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at:%d/%m/%Y %H:%M} {self.user} {self.action} {self.description}"

    @classmethod
    def log(cls, user, action, obj, description=None):
        cls.objects.create(
            user=user if user and user.is_authenticated else None,
            action=action,
            model=obj._meta.verbose_name if hasattr(obj, "_meta") else str(type(obj)),
            object_id=str(getattr(obj, "pk", "") or ""),
            description=(description or str(obj))[:300],
        )


class SystemTask(models.Model):
    """Estado de tareas automáticas del sistema (sincronizaciones, heartbeat de la base)."""

    key = models.CharField("tarea", max_length=50, unique=True)
    last_attempt = models.DateTimeField("último intento", null=True, blank=True)
    last_success = models.DateTimeField("última actualización exitosa", null=True, blank=True)
    last_error = models.TextField("último error", blank=True)
    detail = models.CharField("detalle", max_length=250, blank=True)
    running_since = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "tarea del sistema"
        verbose_name_plural = "tareas del sistema"

    def __str__(self):
        return self.key
