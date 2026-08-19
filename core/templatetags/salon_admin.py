"""What the admin's JavaScript needs to know, handed to it as data.

One tag, rendered once per admin page by `templates/admin/base_site.html`.
It carries two things `static/admin/salon-ajax.js` cannot work out for itself:

*   **A CSRF token.** The obvious source is a hidden input in the page's form,
    and that works everywhere except the one page that has no form -- the
    dashboard, which is exactly where the row buttons need to post from.
    `get_token(request)` gives one unconditionally, which is why this is a tag
    and not a `querySelector`.
*   **The endpoints for whatever admin is on screen.** A changelist knows its
    own ModelAdmin; the JavaScript does not, and hard-coding URLs in it would
    put the URL conf in two places.

Rendered with `json_script`, which escapes `<`, `>` and `&` so a value can
never close the script tag it is inside.
"""

from django import template
from django.middleware.csrf import get_token
from django.urls import reverse
from django.utils.html import json_script

from core.dashboard import dashboard_context

register = template.Library()

CONFIG_ID = "salon-ajax-config"


def _model_admin(context):
    """The ModelAdmin for this page, if it is a page that has one.

    A changelist puts it on `cl`; a change form reaches it through
    `adminform`. Anything else -- the dashboard, a delete confirmation --
    has neither, and gets the token alone.
    """
    changelist = context.get("cl")
    if changelist is not None:
        return getattr(changelist, "model_admin", None)

    adminform = context.get("adminform")
    if adminform is not None:
        return getattr(adminform, "model_admin", None)

    return None


@register.simple_tag(takes_context=True)
def salon_ajax_config(context):
    request = context.get("request")
    if request is None:
        return ""

    config = {"csrfToken": get_token(request), "endpoints": {}}

    # The bell's endpoints, on every admin page rather than per-model: it is
    # in the navbar, so there is no page it is not on. Kept in this block
    # rather than hard-coded in the script for the same reason as the rest --
    # one URL conf, not two.
    config["notifications"] = {
        "feed": reverse("admin_notifications"),
        "read": reverse("admin_notifications_read"),
    }

    model_admin = _model_admin(context)
    if model_admin is not None and hasattr(model_admin, "ajax_endpoints"):
        try:
            config["endpoints"] = model_admin.ajax_endpoints()
        except Exception:  # noqa: BLE001
            # A broken endpoint lookup must not take the whole admin page down
            # with it. Without endpoints the JavaScript simply does nothing,
            # and every no-JS path still works.
            config["endpoints"] = {}

    return json_script(config, CONFIG_ID)


@register.inclusion_tag("admin/includes/salon_dashboard.html", takes_context=True)
def salon_dashboard(context):
    """The counters strip above Jazzmin's app list.

    Server-rendered, so the page says something useful before any JavaScript
    runs and continues to with none at all. The only thing the script touches
    afterwards is a number that an inline approval has just made wrong.
    """
    data = dashboard_context()
    data["request"] = context.get("request")
    return data
