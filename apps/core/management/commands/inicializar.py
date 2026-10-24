import os

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.models import CompanySettings, Role
from apps.core.modules import DEFAULT_ROLES, Level, Module

LEAVE_TYPES = [
    # nombre, código, clase, color, con goce, cómputo, días/evento, tope anual, saldo, comprobante, aprobación, autogestión, ref
    ("Vacaciones", "vacaciones", "vacaciones", "#2b6cb0", True, "corridos", None, None, True, False, True, True,
     "Arts. 150-157 LCT. 14/21/28/35 días corridos según antigüedad. Ley 27.802: fraccionables por acuerdo en tramos de 7 días o más."),
    ("Enfermedad inculpable", "enfermedad", "enfermedad", "#e07a5f", True, "corridos", None, None, False, True, True, True,
     "Art. 208 LCT: 3 meses pagos (antigüedad < 5 años) o 6 meses (≥ 5 años); se duplica con cargas de familia. Aviso al empleador (art. 209)."),
    ("Accidente o enfermedad laboral (ART)", "art", "enfermedad", "#c94f7c", True, "corridos", None, None, False, True, True, False,
     "Ley 24.557 de Riesgos del Trabajo. Denuncia a la ART."),
    ("Matrimonio", "matrimonio", "especial", "#7b5ea7", True, "corridos", 10, None, False, True, True, True,
     "Art. 158 inc. b LCT: 10 días corridos."),
    ("Nacimiento de hijo/a", "nacimiento", "especial", "#3d9970", True, "corridos", 2, None, False, True, True, True,
     "Art. 158 inc. a LCT: 2 días corridos (verificar si el CCT otorga más)."),
    ("Fallecimiento de cónyuge, conviviente, hijo/a o padres", "fallecimiento", "especial", "#495057", True, "corridos", 3, None,
     False, True, True, True, "Art. 158 inc. c LCT: 3 días corridos."),
    ("Fallecimiento de hermano/a", "fallecimiento-hermano", "especial", "#6c757d", True, "corridos", 1, None, False, True, True,
     True, "Art. 158 inc. d LCT: 1 día."),
    ("Examen (estudios secundarios o universitarios)", "examen", "especial", "#f2b134", True, "corridos", 2, 10, False, True,
     True, True, "Art. 158 inc. e LCT: 2 días corridos por examen, máximo 10 por año calendario."),
    ("Maternidad", "maternidad", "especial", "#d1495b", True, "corridos", 90, None, False, True, True, False,
     "Art. 177 LCT: 90 días (45 antes y 45 después del parto; puede reducirse a 30 antes). La asignación la abona ANSES."),
    ("Donación de sangre", "donacion-sangre", "especial", "#b02a37", True, "corridos", 1, None, False, True, True, True,
     "Ley 22.990: el día de la donación."),
    ("Excedencia", "excedencia", "otra", "#adb5bd", False, "corridos", None, None, False, False, True, False,
     "Art. 183 LCT: 3 a 6 meses sin goce, luego de la licencia por maternidad."),
    ("Licencia sin goce de haberes", "sin-goce", "otra", "#868e96", False, "corridos", None, None, False, False, True, True,
     "Acuerdo de partes."),
    ("Trámite personal", "tramite", "otra", "#56a3c9", True, "habiles", 1, 2, False, False, True, True,
     "Política de la empresa (ajustable)."),
]

ONBOARDING = [
    ("Examen preocupacional", "RRHH", -5),
    ("Alta temprana en ARCA (Simplificación Registral)", "RRHH", -1),
    ("Crear usuario, email y accesos", "IT", -1),
    ("Firma de contrato, recepción de documentación (DNI, CUIL, CBU, domicilio)", "RRHH", 0),
    ("Alta en obra social y ART", "RRHH", 0),
    ("Entrega de equipamiento y elementos de trabajo", "IT", 0),
    ("Presentación al equipo y recorrido", "Jefe directo", 0),
    ("Inducción: políticas, seguridad e higiene", "RRHH", 2),
    ("Reunión de seguimiento a 30 días", "Jefe directo", 30),
    ("Evaluación antes del fin del período de prueba", "Jefe directo", 150),
]

OFFBOARDING = [
    ("Registrar renuncia / comunicación de despido (telegrama o carta documento)", "RRHH", 0),
    ("Baja en ARCA (Simplificación Registral)", "RRHH", 0),
    ("Liquidación final (proporcionales de SAC y vacaciones, indemnizaciones si corresponden)", "Liquidación", 2),
    ("Devolución de equipos, llaves y credenciales", "IT", 0),
    ("Baja de usuarios y accesos", "IT", 0),
    ("Entrevista de salida", "RRHH", 0),
    ("Entrega de certificado de trabajo y certificación de servicios (art. 80 LCT)", "RRHH", 30),
]


class Command(BaseCommand):
    help = "Carga los datos iniciales: roles, tipos de licencia (LCT), feriados, plantillas y usuario administrador."

    @transaction.atomic
    def handle(self, *args, **options):
        from apps.licencias.holidays_data import load_local
        from apps.licencias.models import LeaveType
        from apps.onboarding.models import ChecklistTemplate, Kind, TemplateTask

        CompanySettings.get()

        for name, perms in DEFAULT_ROLES.items():
            role, created = Role.objects.get_or_create(name=name)
            if created:
                for module in Module:
                    role.permissions.create(module=module.value, level=perms.get(module, Level.NINGUNO))
                self.stdout.write(f"  Rol creado: {name}")

        for (name, code, kind, color, paid, count, per_event, per_year, balance, attach, approval, self_service,
             ref) in LEAVE_TYPES:
            _, created = LeaveType.objects.get_or_create(
                code=code,
                defaults=dict(name=name, kind=kind, color=color, paid=paid, day_count=count, days_per_event=per_event,
                              days_per_year=per_year, tracks_balance=balance, requires_attachment=attach,
                              requires_approval=approval, self_service=self_service, legal_reference=ref),
            )
            if created:
                self.stdout.write(f"  Tipo de licencia: {name}")

        for year in (2026,):
            created, _ = load_local(year)
            if created:
                self.stdout.write(f"  Feriados {year}: {created}")

        for name, kind, tasks in [("Ingreso estándar", Kind.ONBOARDING, ONBOARDING),
                                  ("Egreso estándar", Kind.OFFBOARDING, OFFBOARDING)]:
            tpl, created = ChecklistTemplate.objects.get_or_create(name=name, kind=kind)
            if created:
                for i, (title, resp, offset) in enumerate(tasks, 1):
                    TemplateTask.objects.create(template=tpl, title=title, responsible=resp, due_offset_days=offset, order=i)
                self.stdout.write(f"  Plantilla: {name}")

        self._create_admin()
        self.stdout.write(self.style.SUCCESS("Inicialización completa."))

    def _create_admin(self):
        from apps.core.models import User

        username = os.environ.get("HRMS_ADMIN_USER") or os.environ.get("DJANGO_SUPERUSER_USERNAME")
        password = os.environ.get("HRMS_ADMIN_PASSWORD") or os.environ.get("DJANGO_SUPERUSER_PASSWORD")
        email = os.environ.get("HRMS_ADMIN_EMAIL") or os.environ.get("DJANGO_SUPERUSER_EMAIL", "")
        if not username or not password:
            if not User.objects.filter(is_superuser=True).exists():
                self.stdout.write(self.style.WARNING(
                    "  No hay administrador. Definí HRMS_ADMIN_USER y HRMS_ADMIN_PASSWORD o ejecutá "
                    "'python manage.py createsuperuser'."
                ))
            return
        if User.objects.filter(username=username).exists():
            return
        User.objects.create_superuser(username=username, email=email, password=password, first_name="Administrador")
        self.stdout.write(f"  Usuario administrador creado: {username}")
