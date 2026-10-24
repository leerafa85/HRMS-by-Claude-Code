from django.urls import path

from . import views

app_name = "onboarding"

urlpatterns = [
    path("", views.ChecklistList.as_view(), name="checklist_list"),
    path("nuevo/", views.checklist_start, name="checklist_create"),
    path("<int:pk>/", views.checklist_detail, name="checklist_detail"),
    path("<int:pk>/eliminar/", views.ChecklistDelete.as_view(), name="checklist_delete"),
    path("tareas/<int:pk>/toggle/", views.task_toggle, name="tarea_toggle"),
    path("tareas/<int:pk>/eliminar/", views.task_delete, name="tarea_delete"),
    path("mis-tareas/", views.my_tasks, name="mis_tareas"),
    path("plantillas/", views.TemplateList.as_view(), name="plantilla_list"),
    path("plantillas/nueva/", views.template_edit, name="plantilla_create"),
    path("plantillas/<int:pk>/editar/", views.template_edit, name="plantilla_update"),
    path("plantillas/<int:pk>/eliminar/", views.TemplateDelete.as_view(), name="plantilla_delete"),
]
