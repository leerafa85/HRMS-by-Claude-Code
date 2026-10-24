from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("perfil/", views.profile, name="perfil"),
    path("usuarios/", views.UserList.as_view(), name="usuario_list"),
    path("usuarios/nuevo/", views.UserCreate.as_view(), name="usuario_create"),
    path("usuarios/<int:pk>/editar/", views.UserUpdate.as_view(), name="usuario_update"),
    path("usuarios/<int:pk>/eliminar/", views.UserDelete.as_view(), name="usuario_delete"),
    path("roles/", views.RoleList.as_view(), name="rol_list"),
    path("roles/matriz/", views.role_matrix, name="rol_matriz"),
    path("roles/nuevo/", views.RoleCreate.as_view(), name="rol_create"),
    path("roles/<int:pk>/editar/", views.RoleUpdate.as_view(), name="rol_update"),
    path("roles/<int:pk>/eliminar/", views.RoleDelete.as_view(), name="rol_delete"),
    path("configuracion/", views.configuration, name="configuracion"),
    path("auditoria/", views.AuditList.as_view(), name="auditoria"),
]
