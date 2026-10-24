from django.urls import path

from . import views

app_name = "asistencia"


def crud(prefix, slug, list_v, create_v, update_v, delete_v):
    return [
        path(f"{slug}/", list_v.as_view(), name=f"{prefix}_list"),
        path(f"{slug}/nuevo/", create_v.as_view(), name=f"{prefix}_create"),
        path(f"{slug}/<int:pk>/editar/", update_v.as_view(), name=f"{prefix}_update"),
        path(f"{slug}/<int:pk>/eliminar/", delete_v.as_view(), name=f"{prefix}_delete"),
    ]


urlpatterns = [
    *crud("inasistencia", "inasistencias", views.AbsenceList, views.AbsenceCreate, views.AbsenceUpdate, views.AbsenceDelete),
    *crud("tardanza", "llegadas-tarde", views.TardinessList, views.TardinessCreate, views.TardinessUpdate,
          views.TardinessDelete),
    *crud("horaextra", "horas-extras", views.OvertimeList, views.OvertimeCreate, views.OvertimeUpdate,
          views.OvertimeDelete),
    path("horas-extras/<int:pk>/revisar/", views.overtime_review, name="horaextra_review"),
    path("resumen/", views.summary, name="resumen"),
    path("mi-asistencia/", views.my_attendance, name="mi_asistencia"),
]
