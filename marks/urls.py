from django.urls import path
from . import views

urlpatterns = [
    path('', views.exam_list, name='exam_list'),
    path('add/', views.exam_add, name='exam_add'),
    path('exam/<int:exam_id>/entry/', views.marks_entry, name='marks_entry'),
    path('exam/<int:exam_id>/unlock/<int:section_id>/<int:subject_id>/', views.marks_entry_unlock, name='marks_entry_unlock'),
    path('exam/<int:exam_id>/whatsapp/send/', views.marks_whatsapp_send, name='marks_whatsapp_send'),
    path('report/', views.marks_report, name='marks_report'),
    path('report/export/excel/', views.marks_report_export_excel, name='marks_report_export_excel'),
    path('report/export/pdf/', views.marks_report_export_pdf, name='marks_report_export_pdf'),
    path('student/<int:student_id>/export/pdf/', views.student_marks_export_pdf, name='student_marks_export_pdf'),
]
