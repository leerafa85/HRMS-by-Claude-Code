from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path, re_path

from apps.core import views as core_views

urlpatterns = [
    path("", core_views.dashboard, name="dashboard"),
    path("estado/", core_views.health, name="estado"),
    path("ingresar/", auth_views.LoginView.as_view(template_name="auth/login.html", redirect_authenticated_user=True), name="login"),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "cambiar-clave/",
        auth_views.PasswordChangeView.as_view(template_name="auth/password_change.html", success_url="/"),
        name="password_change",
    ),
    path("sistema/", include("apps.core.urls")),
    path("personal/", include("apps.empleados.urls")),
    path("licencias/", include("apps.licencias.urls")),
    path("asistencia/", include("apps.asistencia.urls")),
    path("reclutamiento/", include("apps.reclutamiento.urls")),
    path("onboarding/", include("apps.onboarding.urls")),
    path("anuncios/", include("apps.anuncios.urls")),
    path("reportes/", include("apps.reportes.urls")),
    path("pagos/", include("apps.pagos.urls")),
    path("evaluaciones/", include("apps.evaluaciones.urls")),
    path("empleos/", include("apps.reclutamiento.public_urls")),
    re_path(r"^archivos/(?P<path>.+)$", core_views.protected_media, name="media"),
    path("django-admin/", admin.site.urls),
]

handler403 = "apps.core.views.error_403"
handler404 = "apps.core.views.error_404"

admin.site.site_header = "HRMS · Administración técnica"
