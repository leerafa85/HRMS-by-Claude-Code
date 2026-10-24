"""Admin técnico de Django (solo superusuarios). La operación diaria se hace desde la interfaz del HRMS."""

from django.apps import apps
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import RolePermission, User


class RolePermissionInline(admin.TabularInline):
    model = RolePermission
    extra = 0


@admin.register(User)
class HRUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("HRMS", {"fields": ("roles",)}),)
    filter_horizontal = ("roles", "groups", "user_permissions")


admin.site.register(apps.get_model("core", "Role"), inlines=[RolePermissionInline])

for label in ["core.CompanySettings", "core.AuditLog"]:
    admin.site.register(apps.get_model(label))

for app_label in ["empleados", "licencias", "asistencia", "reclutamiento", "onboarding", "anuncios"]:
    for model in apps.get_app_config(app_label).get_models():
        try:
            admin.site.register(model)
        except admin.sites.AlreadyRegistered:
            pass
