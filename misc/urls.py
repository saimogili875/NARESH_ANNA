from django.urls import path
from . import views

urlpatterns = [
    path('', views.misc_sheet, name='misc_sheet'),
    path('save/', views.misc_save, name='misc_save'),
    path('export/', views.misc_export, name='misc_export'),
]
