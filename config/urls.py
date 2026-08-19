from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path

from core import admin_views

urlpatterns = [
    # Nothing is served at the root, so send visitors to the thing they came for.
    path("", lambda request: redirect("admin:index", permanent=False)),
    # The notification bell, before admin.site.urls rather than inside it.
    #
    # It sits on every admin page, so it belongs to no ModelAdmin and there is
    # no `get_urls()` that is the right home for it. Mounting it here keeps it
    # under /admin/ -- where its cookies and its session already are -- without
    # subclassing AdminSite for two views.
    #
    # Order matters: `admin.site.urls` contains `admin/<app_label>/`, which
    # would match "admin/notifications/" and answer with the admin's own 404
    # for an app that does not exist.
    path("admin/notifications/", admin_views.feed, name="admin_notifications"),
    path(
        "admin/notifications/read/",
        admin_views.mark_read,
        name="admin_notifications_read",
    ),
    path("admin/", admin.site.urls),
    path("api/v1/", include("api.urls")),
]

# In production these are served by whitenoise (static) and the web server or a
# bucket (media); this helper is a no-op unless DEBUG is on.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)