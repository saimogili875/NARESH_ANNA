from django.urls import path
from . import views

urlpatterns = [
    path('', views.attendance_list, name='attendance_list'),
    path('mark/', views.attendance_mark, name='attendance_mark'),
    path('save-reasons/', views.attendance_save_reasons, name='attendance_save_reasons'),
    path('send-whatsapp/', views.attendance_send_whatsapp, name='attendance_send_whatsapp'),
    path('report/', views.attendance_report, name='attendance_report'),
    path('report/export/', views.attendance_report_export, name='attendance_report_export'),
    path('yearly/', views.attendance_yearly, name='attendance_yearly'),
    path('yearly/export/excel/', views.attendance_yearly_export_excel, name='attendance_yearly_export_excel'),
]
