from django.urls import path

from . import views

app_name = "reclutamiento"

urlpatterns = [
    path("busquedas/", views.JobList.as_view(), name="busqueda_list"),
    path("busquedas/nueva/", views.JobCreate.as_view(), name="busqueda_create"),
    path("busquedas/<int:pk>/", views.JobDetail.as_view(), name="busqueda_detail"),
    path("busquedas/<int:pk>/editar/", views.JobUpdate.as_view(), name="busqueda_update"),
    path("busquedas/<int:pk>/eliminar/", views.JobDelete.as_view(), name="busqueda_delete"),
    path("candidatos/", views.CandidateList.as_view(), name="candidato_list"),
    path("candidatos/nuevo/", views.CandidateCreate.as_view(), name="candidato_create"),
    path("candidatos/<int:pk>/", views.CandidateDetail.as_view(), name="candidato_detail"),
    path("candidatos/<int:pk>/editar/", views.CandidateUpdate.as_view(), name="candidato_update"),
    path("candidatos/<int:pk>/eliminar/", views.CandidateDelete.as_view(), name="candidato_delete"),
    path("postulaciones/agregar/", views.application_add, name="postulacion_add"),
    path("postulaciones/<int:pk>/", views.application_detail, name="postulacion_detail"),
    path("postulaciones/<int:pk>/editar/", views.application_edit, name="postulacion_update"),
    path("postulaciones/<int:pk>/mover/", views.application_move, name="postulacion_move"),
    path("postulaciones/<int:pk>/contratar/", views.application_hire, name="postulacion_hire"),
    path("postulaciones/<int:application_pk>/entrevistas/nueva/", views.interview_edit, name="entrevista_create"),
    path("postulaciones/<int:application_pk>/entrevistas/<int:pk>/", views.interview_edit, name="entrevista_update"),
]
