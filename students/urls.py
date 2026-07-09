from django.urls import path
from . import views

urlpatterns = [
    path('', views.student_list, name='student_list'),
    path('add/', views.student_add, name='student_add'),
    path('<int:pk>/', views.student_profile, name='student_profile'),
    path('<int:pk>/edit/', views.student_edit, name='student_edit'),
    path('<int:pk>/delete/', views.student_delete, name='student_delete'),
    path('<int:pk>/transfer/', views.student_transfer, name='student_transfer'),
    path('<int:pk>/promote/', views.student_promote, name='student_promote'),
    path('export/', views.student_export_excel, name='student_export'),
    path('import/', views.student_import_excel, name='student_import'),
]
