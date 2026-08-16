from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path

urlpatterns = [
    # Nothing is served at the root, so send visitors to the thing they came for.
    path("", lambda request: redirect("admin:index", permanent=False)),
    path("admin/", admin.site.urls),
    path("api/v1/", include("api.urls")),
]

# In production these are served by whitenoise (static) and the web server or a
# bucket (media); this helper is a no-op unless DEBUG is on.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)