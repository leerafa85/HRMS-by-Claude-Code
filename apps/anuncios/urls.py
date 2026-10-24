from django.urls import path

from . import views

app_name = "anuncios"

urlpatterns = [
    path("", views.AnnouncementList.as_view(), name="anuncio_list"),
    path("nuevo/", views.AnnouncementCreate.as_view(), name="anuncio_create"),
    path("<int:pk>/", views.announcement_detail, name="anuncio_detail"),
    path("<int:pk>/editar/", views.AnnouncementUpdate.as_view(), name="anuncio_update"),
    path("<int:pk>/eliminar/", views.AnnouncementDelete.as_view(), name="anuncio_delete"),
]
