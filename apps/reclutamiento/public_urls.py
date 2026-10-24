from django.urls import path

from . import views

app_name = "empleos"

urlpatterns = [
    path("", views.public_jobs, name="lista"),
    path("<int:pk>/", views.public_job_detail, name="detalle"),
]
