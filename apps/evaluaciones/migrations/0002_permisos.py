from django.db import migrations

# Nivel inicial del módulo nuevo para los roles precargados que ya existen en la base.
LEVELS = {"Administrador RRHH": 3, "Analista RRHH": 2, "Líder de equipo": 2}


def grant(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    RolePermission = apps.get_model("core", "RolePermission")
    for role in Role.objects.filter(name__in=LEVELS):
        RolePermission.objects.get_or_create(role=role, module="evaluaciones", defaults={"level": LEVELS[role.name]})


class Migration(migrations.Migration):
    dependencies = [("evaluaciones", "0001_initial"), ("core", "0001_initial")]
    operations = [migrations.RunPython(grant, migrations.RunPython.noop)]
