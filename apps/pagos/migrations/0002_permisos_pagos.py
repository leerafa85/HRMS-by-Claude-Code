from django.db import migrations


def grant(apps, schema_editor):
    """Los roles existentes reciben en el módulo nuevo «Pagos» el mismo nivel que tienen en «Salarios»."""
    RolePermission = apps.get_model("core", "RolePermission")
    for perm in RolePermission.objects.filter(module="salarios"):
        RolePermission.objects.get_or_create(role_id=perm.role_id, module="pagos", defaults={"level": perm.level})


class Migration(migrations.Migration):
    dependencies = [("pagos", "0001_initial"), ("core", "0001_initial")]
    operations = [migrations.RunPython(grant, migrations.RunPython.noop)]
