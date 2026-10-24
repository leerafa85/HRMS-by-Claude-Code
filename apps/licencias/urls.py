from django.urls import path

from . import views

app_name = "licencias"

urlpatterns = [
    path("solicitudes/", views.RequestList.as_view(), name="solicitud_list"),
    path("solicitudes/exportar/", views.request_export, name="solicitud_export"),
    path("solicitudes/nueva/", views.RequestCreate.as_view(), name="solicitud_create"),
    path("solicitudes/<int:pk>/", views.request_detail, name="solicitud_detail"),
    path("solicitudes/<int:pk>/editar/", views.RequestUpdate.as_view(), name="solicitud_update"),
    path("solicitudes/<int:pk>/eliminar/", views.RequestDelete.as_view(), name="solicitud_delete"),
    path("solicitudes/<int:pk>/revisar/", views.request_review, name="solicitud_review"),
    path("solicitudes/<int:pk>/cancelar/", views.request_cancel, name="solicitud_cancel"),
    path("aprobaciones/", views.approvals, name="aprobaciones"),
    path("mis-licencias/", views.my_leaves, name="mis_licencias"),
    path("calendario/", views.leave_calendar, name="calendario"),
    path("saldos/", views.BalanceList.as_view(), name="saldo_list"),
    path("saldos/exportar/", views.balance_export, name="saldo_export"),
    path("saldos/nuevo/", views.BalanceCreate.as_view(), name="saldo_create"),
    path("saldos/generar/", views.generate_balances, name="saldo_generar"),
    path("saldos/<int:pk>/editar/", views.BalanceUpdate.as_view(), name="saldo_update"),
    path("saldos/<int:pk>/eliminar/", views.BalanceDelete.as_view(), name="saldo_delete"),
    path("tipos/", views.TypeList.as_view(), name="tipo_list"),
    path("tipos/nuevo/", views.TypeCreate.as_view(), name="tipo_create"),
    path("tipos/<int:pk>/editar/", views.TypeUpdate.as_view(), name="tipo_update"),
    path("tipos/<int:pk>/eliminar/", views.TypeDelete.as_view(), name="tipo_delete"),
    path("feriados/", views.HolidayList.as_view(), name="feriado_list"),
    path("feriados/nuevo/", views.HolidayCreate.as_view(), name="feriado_create"),
    path("feriados/importar/", views.holiday_import, name="feriado_importar"),
    path("feriados/<int:pk>/editar/", views.HolidayUpdate.as_view(), name="feriado_update"),
    path("feriados/<int:pk>/eliminar/", views.HolidayDelete.as_view(), name="feriado_delete"),
]
