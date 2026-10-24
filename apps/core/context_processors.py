from django.urls import reverse

from .models import CompanySettings
from .modules import Level, Module

# (sección, [(etiqueta, url_name, icono, módulo requerido o None, nivel)])
MENU = [
    ("Personas", [
        ("Empleados", "empleados:empleado_list", "people", Module.EMPLEADOS, Level.VER),
        ("Directorio", "empleados:directorio", "person-lines-fill", None, None),
        ("Organigrama", "empleados:organigrama", "diagram-3", None, None),
        ("Documentos", "empleados:documento_list", "folder2-open", Module.DOCUMENTOS, Level.VER),
        ("Salarios", "empleados:salario_list", "cash-coin", Module.SALARIOS, Level.VER),
    ]),
    ("Tiempo libre", [
        ("Solicitudes", "licencias:solicitud_list", "calendar2-check", Module.LICENCIAS, Level.VER),
        ("Calendario", "licencias:calendario", "calendar3", Module.LICENCIAS, Level.VER),
        ("Saldos", "licencias:saldo_list", "hourglass-split", Module.LICENCIAS, Level.VER),
        ("Feriados", "licencias:feriado_list", "flag", Module.FERIADOS, Level.VER),
    ]),
    ("Asistencia", [
        ("Inasistencias", "asistencia:inasistencia_list", "person-x", Module.ASISTENCIA, Level.VER),
        ("Llegadas tarde", "asistencia:tardanza_list", "alarm", Module.ASISTENCIA, Level.VER),
        ("Horas extras", "asistencia:horaextra_list", "clock-history", Module.ASISTENCIA, Level.VER),
        ("Resumen mensual", "asistencia:resumen", "table", Module.ASISTENCIA, Level.VER),
    ]),
    ("Talento", [
        ("Búsquedas", "reclutamiento:busqueda_list", "briefcase", Module.RECLUTAMIENTO, Level.VER),
        ("Candidatos", "reclutamiento:candidato_list", "person-badge", Module.RECLUTAMIENTO, Level.VER),
        ("Onboarding / Offboarding", "onboarding:checklist_list", "list-check", Module.ONBOARDING, Level.VER),
    ]),
    ("Comunicación", [
        ("Anuncios", "anuncios:anuncio_list", "megaphone", Module.ANUNCIOS, Level.VER),
    ]),
    ("Análisis", [
        ("Reportes", "reportes:index", "bar-chart", Module.REPORTES, Level.VER),
    ]),
    ("Administración", [
        ("Usuarios", "core:usuario_list", "person-gear", Module.USUARIOS, Level.VER),
        ("Roles y permisos", "core:rol_list", "shield-lock", Module.USUARIOS, Level.VER),
        ("Configuración", "core:configuracion", "gear", Module.CONFIGURACION, Level.VER),
        ("Auditoría", "core:auditoria", "journal-text", Module.USUARIOS, Level.ADMINISTRAR),
    ]),
]


def build_menu(user):
    sections = []
    for title, items in MENU:
        visible = [
            {"label": label, "url": reverse(name), "icon": icon, "name": name}
            for label, name, icon, module, level in items
            if module is None or user.can(module, level)
        ]
        if visible:
            sections.append({"title": title, "items": visible})
    return sections


def hrms(request):
    ctx = {"company": CompanySettings.get(), "Module": Module, "Level": Level}
    user = request.user
    if not user.is_authenticated:
        return ctx
    from apps.licencias.models import LeaveRequest

    employee = getattr(user, "employee", None)
    pending = LeaveRequest.objects.filter(status=LeaveRequest.Status.PENDIENTE)
    if user.can(Module.LICENCIAS, Level.ADMINISTRAR):
        pending_count = pending.count()
    elif employee:
        pending_count = pending.filter(employee__manager=employee).count()
    else:
        pending_count = 0
    ctx.update(
        {
            "menu": build_menu(user),
            "my_employee": employee,
            "has_team": bool(employee and employee.reports.exists()),
            "pending_approvals": pending_count,
            "can_approve": pending_count > 0 or user.can(Module.LICENCIAS, Level.ADMINISTRAR)
            or bool(employee and employee.reports.exists()),
        }
    )
    return ctx
