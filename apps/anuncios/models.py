from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.empleados.models import Department


class Announcement(models.Model):
    title = models.CharField("título", max_length=200)
    body = models.TextField("contenido")
    pinned = models.BooleanField("destacado", default=False)
    departments = models.ManyToManyField(
        Department, blank=True, verbose_name="áreas destinatarias", help_text="Vacío = toda la empresa."
    )
    publish_at = models.DateTimeField("publicar desde", default=timezone.now)
    expires_at = models.DateTimeField("visible hasta", null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="autor"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "anuncio"
        verbose_name_plural = "anuncios"
        ordering = ["-pinned", "-publish_at"]

    def __str__(self):
        return self.title

    @classmethod
    def visible_for(cls, user):
        now = timezone.now()
        qs = cls.objects.filter(publish_at__lte=now).filter(
            models.Q(expires_at__isnull=True) | models.Q(expires_at__gte=now)
        )
        emp = getattr(user, "employee", None)
        if emp and emp.department_id:
            qs = qs.filter(models.Q(departments__isnull=True) | models.Q(departments=emp.department_id))
        elif not user.is_superuser:
            qs = qs.filter(departments__isnull=True)
        return qs.distinct()
