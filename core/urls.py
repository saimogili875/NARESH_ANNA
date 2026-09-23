from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from core.views import privacy_policy, protected_media

urlpatterns = [
    path('media/<path:path>', protected_media, name='protected_media'),
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
]


