from django.urls import path
from . import views

urlpatterns = [
    path('', views.fee_list, name='fee_list'),
    path('bulk-tuition/', views.fee_set_bulk, name='fee_set_bulk'),
    path('types/', views.fee_type_manage, name='fee_type_manage'),
    path('types/<int:pk>/edit/', views.fee_type_edit, name='fee_type_edit'),
    path('types/<int:pk>/assign/', views.fee_type_assign, name='fee_type_assign'),
    path('types/<int:pk>/assign-individual/', views.fee_type_assign_individual, name='fee_type_assign_individual'),
    path('types/<int:pk>/delete/', views.fee_type_delete, name='fee_type_delete'),
    path('student/<int:pk>/', views.fee_detail, name='fee_detail'),
    path('student/<int:pk>/set/', views.fee_set, name='fee_set'),
    path('student/<int:pk>/collect/', views.fee_collect, name='fee_collect'),
    path('student/<int:pk>/adjust/', views.payment_adjust, name='payment_adjust'),
    path('student/<int:pk>/charge/<int:charge_id>/set/', views.fee_charge_set, name='fee_charge_set'),
    path('student/<int:pk>/payment/<int:payment_id>/edit/', views.payment_edit, name='payment_edit'),
    path('student/<int:pk>/payment/<int:payment_id>/delete/', views.payment_delete, name='payment_delete'),
    path('student/<int:pk>/receipt/<int:payment_id>/', views.receipt_download, name='receipt_download'),
    path('student/<int:pk>/receipt/<int:payment_id>/send-whatsapp/', views.receipt_send_whatsapp, name='receipt_send_whatsapp'),
    path('types/<int:pk>/unassign-section/<int:section_id>/', views.fee_type_unassign_section, name='fee_type_unassign_section'),
    path('types/<int:pk>/charge/<int:charge_id>/delete/', views.fee_charge_delete, name='fee_charge_delete'),
]

urlpatterns += [
    path('export/', views.fee_export, name='fee_export'),
]
