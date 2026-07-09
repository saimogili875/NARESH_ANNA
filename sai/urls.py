from django.urls import path
from . import views

app_name = 'sai'

urlpatterns = [
    path('', views.lab_form, name='lab_form'),
    path('success/<int:report_id>/', views.lab_form_success, name='lab_form_success'),
    path('preview/<int:report_id>/', views.lab_preview, name='lab_preview'),
    path('pdf/<int:report_id>/', views.generate_pdf, name='generate_pdf'),
    path('list/', views.lab_reports_list, name='lab_reports_list'),
    path('detail/<int:report_id>/', views.lab_report_detail, name='lab_report_detail'),
]
