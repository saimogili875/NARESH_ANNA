from django.contrib import admin
from django.urls import path, include, re_path
from django.views.static import serve
from django.conf import settings
from core.views import privacy_policy

urlpatterns = [
    path('privacy/', privacy_policy, name='privacy-policy'),
    path('admin/', admin.site.urls),
    path('', include('accounts.urls')),
    path('students/', include('students.urls')),
    path('attendance/', include('attendance.urls')),
    path('marks/', include('marks.urls')),
    path('fees/', include('fees.urls')),
    path('faculty/', include('faculty.urls')),
    path('reports/', include('reports.urls')),
    path('lab/', include('sai.urls')),
    path('misc/', include('misc.urls')),
    path('whatsapp/', include('whatsapp.urls')),
    path('captcha/', include('captcha.urls')),
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]

