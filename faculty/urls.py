from django.urls import path
from . import views

urlpatterns = [
    path('', views.faculty_list, name='faculty_list'),
    path('add/', views.faculty_add, name='faculty_add'),
    path('<int:pk>/edit/', views.faculty_edit, name='faculty_edit'),
    path('<int:pk>/delete/', views.faculty_delete, name='faculty_delete'),
    path('attendance/', views.faculty_attendance, name='faculty_attendance'),
]
