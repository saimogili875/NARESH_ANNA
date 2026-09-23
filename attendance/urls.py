from django.urls import path
from . import views

urlpatterns = [
    path('', views.attendance_list, name='attendance_list'),
    path('classifier/', views.attendance_classifier, name='attendance_classifier'),
    path('quick-login/', views.quick_login_view, name='attendance_quick_login'),
    path('window-closed/', views.window_closed_view, name='attendance_window_closed'),
    path('tap/', views.tap_attendance_sections, name='attendance_tap_sections'),
    path('tap/<int:section_id>/', views.tap_attendance_view, name='attendance_tap_section'),
    path('tap/api/mark/', views.tap_mark_api, name='attendance_tap_mark_api'),
    path('review/', views.attendance_review, name='attendance_review'),
    path('send-section-absent/', views.enqueue_section_absent_whatsapp, name='attendance_send_section_absent'),
    path('trigger-whatsapp-sender/', views.trigger_whatsapp_sender_view, name='attendance_trigger_whatsapp_sender'),
    path('mark/', views.attendance_mark, name='attendance_mark'),


    path('save-reasons/', views.attendance_save_reasons, name='attendance_save_reasons'),
    path('send-whatsapp/', views.attendance_send_whatsapp, name='attendance_send_whatsapp'),
    path('report/', views.attendance_report, name='attendance_report'),
    path('report/export/', views.attendance_report_export, name='attendance_report_export'),
    path('yearly/', views.attendance_yearly, name='attendance_yearly'),
    path('yearly/export/excel/', views.attendance_yearly_export_excel, name='attendance_yearly_export_excel'),
]

