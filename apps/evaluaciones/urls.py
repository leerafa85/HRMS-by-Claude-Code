from django.urls import path

from . import views

app_name = "evaluaciones"

urlpatterns = [
    path("metas/<str:tipo>/", views.PlanList.as_view(), name="plan_list"),
    path("planes/nuevo/", views.PlanCreate.as_view(), name="plan_create"),
    path("planes/<int:pk>/", views.plan_detail, name="plan_detail"),
    path("planes/<int:pk>/editar/", views.PlanUpdate.as_view(), name="plan_update"),
    path("planes/<int:pk>/eliminar/", views.PlanDelete.as_view(), name="plan_delete"),
    path("planes/<int:pk>/duplicar/", views.plan_duplicate, name="plan_duplicate"),
]
