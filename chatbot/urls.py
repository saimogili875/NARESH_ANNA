from django.urls import path
from . import views

urlpatterns = [
    # Swecha AI Chatbot
    path('', views.chatbot_page, name='chatbot_page'),
    path('api/chat/', views.chat_api, name='chat_api'),
    path('api/clear/', views.clear_history_api, name='chat_clear'),
    path('api/stats/', views.quick_stats_api, name='chat_stats'),

    # Groq Usage Monitor & Quota Dashboard
    path('monitor/', views.monitor_dashboard, name='monitor_dashboard'),
    path('monitor/analytics/', views.monitor_analytics, name='monitor_analytics'),
    path('monitor/requests/', views.monitor_requests, name='monitor_requests'),
    path('monitor/requests/export-csv/', views.monitor_export_csv, name='monitor_export_csv'),
    path('monitor/models/', views.monitor_models, name='monitor_models'),
    path('monitor/rate-limits/', views.monitor_ratelimits, name='monitor_ratelimits'),
    path('monitor/speech-to-text/', views.monitor_speech_to_text, name='monitor_speech_to_text'),
    path('monitor/quotas/', views.monitor_quotas, name='monitor_quotas'),
    path('monitor/settings/', views.monitor_settings, name='monitor_settings'),
]
