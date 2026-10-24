"""Catálogo de módulos del HRMS y niveles de acceso que puede tener un rol."""

from django.db import models


class Module(models.TextChoices):
    EMPLEADOS = "empleados", "Legajos de personal"
    DOCUMENTOS = "documentos", "Documentos de legajo"
    SALARIOS = "salarios", "Salarios y ajustes"
    PAGOS = "pagos", "Adelantos de sueldo y liquidaciones finales"
    LICENCIAS = "licencias", "Vacaciones y licencias"
    ASISTENCIA = "asistencia", "Asistencia (inasistencias, tardanzas, horas extras)"
    FERIADOS = "feriados", "Feriados"
    RECLUTAMIENTO = "reclutamiento", "Reclutamiento (búsquedas y candidatos)"
    ONBOARDING = "onboarding", "Onboarding / Offboarding"
    EVALUACIONES = "evaluaciones", "Evaluaciones (metas por equipo y personal)"
    ANUNCIOS = "anuncios", "Anuncios"
    REPORTES = "reportes", "Reportes"
    CONFIGURACION = "configuracion", "Configuración (áreas, puestos, tipos de licencia)"
    USUARIOS = "usuarios", "Usuarios y roles"


class Level(models.IntegerChoices):
    NINGUNO = 0, "Sin acceso"
    VER = 1, "Ver"
    EDITAR = 2, "Ver y editar"
    ADMINISTRAR = 3, "Administrar (eliminar / aprobar)"


# Roles iniciales sugeridos. El admin puede modificarlos o crear otros.
DEFAULT_ROLES = {
    "Administrador RRHH": {m: Level.ADMINISTRAR for m in Module.values},
    "Analista RRHH": {
        Module.EMPLEADOS: Level.EDITAR,
        Module.DOCUMENTOS: Level.EDITAR,
        Module.SALARIOS: Level.VER,
        Module.PAGOS: Level.EDITAR,
        Module.LICENCIAS: Level.ADMINISTRAR,
        Module.ASISTENCIA: Level.ADMINISTRAR,
        Module.FERIADOS: Level.EDITAR,
        Module.RECLUTAMIENTO: Level.EDITAR,
        Module.ONBOARDING: Level.EDITAR,
        Module.EVALUACIONES: Level.EDITAR,
        Module.ANUNCIOS: Level.EDITAR,
        Module.REPORTES: Level.VER,
        Module.CONFIGURACION: Level.VER,
    },
    "Líder de equipo": {
        Module.EMPLEADOS: Level.VER,
        Module.LICENCIAS: Level.VER,
        Module.ASISTENCIA: Level.EDITAR,
        Module.EVALUACIONES: Level.EDITAR,
        Module.FERIADOS: Level.VER,
        Module.RECLUTAMIENTO: Level.VER,
        Module.ANUNCIOS: Level.VER,
    },
    "Reclutador": {
        Module.RECLUTAMIENTO: Level.ADMINISTRAR,
        Module.ONBOARDING: Level.EDITAR,
        Module.ANUNCIOS: Level.VER,
        Module.FERIADOS: Level.VER,
    },
    "Liquidación de sueldos": {
        Module.EMPLEADOS: Level.VER,
        Module.SALARIOS: Level.ADMINISTRAR,
        Module.PAGOS: Level.ADMINISTRAR,
        Module.LICENCIAS: Level.VER,
        Module.ASISTENCIA: Level.VER,
        Module.FERIADOS: Level.VER,
        Module.REPORTES: Level.VER,
    },
    "Empleado": {
        Module.FERIADOS: Level.VER,
        Module.ANUNCIOS: Level.VER,
    },
}
