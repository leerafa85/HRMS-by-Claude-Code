from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .models import AuditLog


@receiver(user_logged_in)
def log_login(sender, request, user, **kwargs):
    AuditLog.objects.create(user=user, action=AuditLog.Action.LOGIN, model="usuario", object_id=str(user.pk),
                            description=f"Inicio de sesión desde {request.META.get('REMOTE_ADDR', '')}")
