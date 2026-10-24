from django.urls import path

from . import views

app_name = "empleados"


def crud(prefix, slug, list_v, create_v, update_v, delete_v, detail_v=None):
    pats = [
        path(f"{slug}/", list_v.as_view(), name=f"{prefix}_list"),
        path(f"{slug}/nuevo/", create_v.as_view(), name=f"{prefix}_create"),
        path(f"{slug}/<int:pk>/editar/", update_v.as_view(), name=f"{prefix}_update"),
        path(f"{slug}/<int:pk>/eliminar/", delete_v.as_view(), name=f"{prefix}_delete"),
    ]
    if detail_v:
        pats.append(path(f"{slug}/<int:pk>/", detail_v.as_view(), name=f"{prefix}_detail"))
    return pats


urlpatterns = [
    *crud("empleado", "empleados", views.EmployeeList, views.EmployeeCreate, views.EmployeeUpdate,
          views.EmployeeDelete, views.EmployeeDetail),
    path("empleados/exportar/", views.employee_export, name="empleado_export"),
    path("empleados/<int:pk>/baja/", views.employee_terminate, name="empleado_baja"),
    path("empleados/<int:pk>/reactivar/", views.employee_reactivate, name="empleado_reactivar"),
    path("empleados/<int:employee_pk>/familia/nuevo/", views.family_member_edit, name="familiar_create"),
    path("empleados/<int:employee_pk>/familia/<int:pk>/", views.family_member_edit, name="familiar_update"),
    path("empleados/<int:employee_pk>/contactos/nuevo/", views.emergency_contact_edit, name="contacto_create"),
    path("empleados/<int:employee_pk>/contactos/<int:pk>/", views.emergency_contact_edit, name="contacto_update"),
    path("empleados/<int:employee_pk>/documentos/subir/", views.document_multi_upload, name="documento_multi"),
    path("empleados/<int:pk>/vcard/", views.vcard, name="vcard"),
    path("mi-legajo/", views.my_profile, name="mi_legajo"),
    path("mi-equipo/", views.my_team, name="mi_equipo"),
    path("mi-equipo/<int:pk>/", views.team_member, name="mi_equipo_detalle"),
    path("directorio/", views.directory, name="directorio"),
    path("organigrama/", views.org_chart, name="organigrama"),
    *crud("documento", "documentos", views.DocumentList, views.DocumentCreate, views.DocumentUpdate,
          views.DocumentDelete),
    *crud("salario", "salarios", views.SalaryList, views.SalaryCreate, views.SalaryUpdate, views.SalaryDelete),
    path("salarios/masivo/", views.salary_bulk, name="salario_masivo"),
    *crud("area", "areas", views.DepartmentList, views.DepartmentCreate, views.DepartmentUpdate,
          views.DepartmentDelete),
    *crud("puesto", "puestos", views.PositionList, views.PositionCreate, views.PositionUpdate, views.PositionDelete),
    *crud("sede", "sedes", views.LocationList, views.LocationCreate, views.LocationUpdate, views.LocationDelete),
]
