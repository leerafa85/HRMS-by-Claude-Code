from django.urls import path

from . import views

app_name = "pagos"

urlpatterns = [
    path("adelantos/", views.AdvanceList.as_view(), name="adelanto_list"),
    path("adelantos/nuevo/", views.AdvanceCreate.as_view(), name="adelanto_create"),
    path("adelantos/<int:pk>/editar/", views.AdvanceUpdate.as_view(), name="adelanto_update"),
    path("adelantos/<int:pk>/eliminar/", views.AdvanceDelete.as_view(), name="adelanto_delete"),
    path("adelantos/<int:pk>/pagado/", views.advance_mark_paid, name="adelanto_pagado"),
    path("adelantos/descontar/", views.advance_mark_discounted, name="adelanto_descontar"),
    path("adelantos/informe/", views.advance_report, name="adelanto_informe"),
    path("liquidaciones-finales/", views.SettlementList.as_view(), name="liquidacion_list"),
    path("liquidaciones-finales/nueva/", views.SettlementCreate.as_view(), name="liquidacion_create"),
    path("liquidaciones-finales/<int:pk>/", views.settlement_detail, name="liquidacion_detail"),
    path("liquidaciones-finales/<int:pk>/editar/", views.SettlementUpdate.as_view(), name="liquidacion_update"),
    path("liquidaciones-finales/<int:pk>/eliminar/", views.SettlementDelete.as_view(), name="liquidacion_delete"),
    path("liquidaciones-finales/<int:pk>/pago/", views.settlement_add_payment, name="liquidacion_pago"),
    path("liquidaciones-finales/<int:pk>/pago/<int:payment_pk>/eliminar/", views.settlement_delete_payment,
         name="liquidacion_pago_delete"),
    path("liquidaciones-finales/<int:pk>/estado/", views.settlement_set_status, name="liquidacion_estado"),
]
