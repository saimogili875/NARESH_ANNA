from django.urls import path
from . import views

urlpatterns = [
    path('', views.student_list, name='student_list'),
    path('add/', views.student_add, name='student_add'),
    path('<int:pk>/', views.student_profile, name='student_profile'),
    path('<int:pk>/photo/', views.student_photo, name='student_photo'),

    path('<int:pk>/edit/', views.student_edit, name='student_edit'),
    path('<int:pk>/delete/', views.student_delete, name='student_delete'),
    path('<int:pk>/transfer/', views.student_transfer, name='student_transfer'),
    path('<int:pk>/promote/', views.student_promote, name='student_promote'),
    path('<int:pk>/inline-update/', views.student_inline_update, name='student_inline_update'),
    path('inline-bulk-save/', views.student_inline_bulk_save, name='student_inline_bulk_save'),
    path('bulk-delete/', views.student_bulk_delete, name='student_bulk_delete'),
    path('bulk-transfer/', views.student_bulk_transfer, name='student_bulk_transfer'),
    path('bulk-edit/', views.student_bulk_edit, name='student_bulk_edit'),
    path('export/', views.student_export_excel, name='student_export'),
    path('import/', views.student_import_excel, name='student_import'),
]
