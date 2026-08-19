"""JSON endpoints for the admin, so a click does not cost a page load.

The admin is the salon's staff interface -- there is no staff-facing API -- and
until now every action in it was a full round trip: approving a booking meant a
checkbox, a dropdown, a Go button and a re-rendered changelist, and publishing
one service re-POSTed every row on the page. This module is the shared half of
fixing that. Nothing here does anything on its own; a ModelAdmin opts in by
naming the fields and actions it will accept.

Three ideas hold it together:

*   **One place enforces the rules.** `admin_json_view` owns the verb check,
    the staff check, CSRF, and every error shape. A view method under it is
    only the interesting part: it returns a dict or raises `AdminAjaxError`.
*   **Nothing is re-implemented.** Row actions run the ModelAdmin's *existing*
    admin actions, and changed cells are re-rendered through Django's own
    `lookup_field` / `display_for_field`. There is no second approve path and
    no second copy of a status pill to drift out of step.
*   **The allowlists are the security boundary.** `field` and `action` arrive
    in a request body from the browser. Without `ajax_toggle_fields` that is an
    arbitrary column write, and without `ajax_row_actions` it is a way to reach
    `delete_selected` one row at a time.

## Why not `self.admin_site.admin_view()`

Every other custom admin URL in this project wraps its view in `admin_view`,
and these deliberately do not.

`admin_view` answers an expired session with a 302 to the login page. `fetch`
follows redirects by default, so the browser gets `200 text/html` holding a
login form, and `response.json()` throws a `SyntaxError` that looks exactly
like a bug in our own JavaScript. A caller that asked for JSON has to be told
"you are signed out" in a way it can act on.

So the decorator re-implements what `admin_view` actually gives us --
`AdminSite.has_permission` is `is_active and is_staff`, plus `csrf_protect` and
`never_cache` -- and answers 401 with a JSON body instead. `static/admin/
salon-ajax.js` turns that into a "sign in again" prompt that does not throw
away whatever is typed into the form.
"""

import functools
import json
import logging

from django.contrib.admin.utils import display_for_field, display_for_value, lookup_field
from django.core.exceptions import FieldDoesNotExist, ObjectDoesNotExist
from django.db import DatabaseError, models
from django.http import JsonResponse
from django.urls import path, reverse
from django.utils.decorators import method_decorator
from django.utils.html import conditional_escape
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

logger = logging.getLogger("common")


class AdminAjaxError(Exception):
    """A failure with a sentence the person clicking can act on.

    `reason` is for the JavaScript, which branches on it; `message` is for the
    human, and is the only part they see. Anything without an explicit message
    is a bug rather than a refusal, and is handled by the catch-all instead.
    """

    def __init__(self, message, status=400, reason="error"):
        super().__init__(message)
        self.message = message
        self.status = status
        self.reason = reason


def _payload(ok, status, **extra):
    return JsonResponse({"ok": ok, **extra}, status=status)


def _drain_messages(request):
    """Take the flash messages this request produced, as data.

    The row-action endpoint runs the ModelAdmin's real admin actions, and those
    call `message_user`. Reading the storage marks it used, so the middleware
    clears it and the messages do not reappear on top of the next page the
    person happens to load -- they come back in the response instead, and the
    JavaScript renders them where they were meant to appear.
    """
    from django.contrib.messages import get_messages

    drained = []
    for message in get_messages(request):
        drained.append({"level": message.level_tag or "info", "text": str(message)})
    return drained


def _serve_json(request, call, name):
    """The checks, the dispatch and every error shape, in one place.

    Split out from the decorators below so that a view method on a ModelAdmin
    and a plain function view outside one cannot answer the same failure two
    different ways -- the JavaScript branches on `reason`, and a second
    spelling of it is a bug that only shows up when something is already
    broken.

    `call` takes the parsed body and returns the success payload as a dict.
    """
    user = getattr(request, "user", None)
    # AdminSite.has_permission, spelled out. See the module docstring for
    # why this is not admin_view() -- in short, a redirect to the login
    # page is not something a fetch() caller can read.
    if not (user and user.is_active and user.is_staff):
        return _payload(
            False,
            401,
            reason="signed_out",
            error="Your sign-in has expired.",
        )

    if request.method != "POST":
        # A GET that acts is one prefetch away from firing on its own.
        return _payload(False, 405, reason="method", error="Use POST.")

    try:
        body = json.loads(request.body or b"{}")
        if not isinstance(body, dict):
            raise ValueError("not an object")
    except (ValueError, UnicodeDecodeError):
        return _payload(False, 400, reason="bad_request", error="Malformed request.")

    try:
        result = call(body)
    except AdminAjaxError as exc:
        return _payload(
            False,
            exc.status,
            reason=exc.reason,
            error=exc.message,
            messages=_drain_messages(request),
        )
    except DatabaseError:
        # Two people approving at the same moment. `approve()` takes
        # select_for_update over the year's order IDs, and SQLite answers a
        # second writer with "database is locked" rather than waiting.
        # Retryable, so it must not read as a crash.
        logger.warning("Admin AJAX hit a locked database", exc_info=True)
        return _payload(
            False,
            409,
            reason="busy",
            error=(
                "Another change was being saved at the same moment. Try again."
            ),
        )
    except Exception:
        # Broad on purpose. An unhandled exception would otherwise render
        # Django's HTML error page, and `response.json()` on that throws a
        # parse error that tells the person nothing at all.
        logger.exception("Admin AJAX view failed: %s", name)
        return _payload(
            False,
            500,
            reason="server",
            error="Something went wrong. The error has been logged.",
        )

    return _payload(True, 200, messages=_drain_messages(request), **result)


def admin_json_view(func):
    """Wrap an admin view method so it can only answer JSON.

    The wrapped method receives `(self, request, body)` -- `body` already
    parsed -- and returns the success payload as a dict.
    """

    @method_decorator(csrf_protect)
    @method_decorator(never_cache)
    @functools.wraps(func)
    def inner(self, request, *args, **kwargs):
        return _serve_json(
            request,
            lambda body: func(self, request, body, *args, **kwargs),
            func.__name__,
        )

    return inner


def admin_json_endpoint(func):
    """The same contract for a view that belongs to no ModelAdmin.

    The notification bell is on every admin page rather than on one model's
    changelist, so its endpoints hang off the URL conf instead of a
    `get_urls()`. They still have to answer an expired session the way
    everything else does, which is the whole reason this exists rather than a
    `staff_member_required` view returning `JsonResponse`.

    The wrapped function receives `(request, body)` and returns a dict.
    """

    @csrf_protect
    @never_cache
    @functools.wraps(func)
    def inner(request, *args, **kwargs):
        return _serve_json(
            request,
            lambda body: func(request, body, *args, **kwargs),
            func.__name__,
        )

    return inner


class AdminAjaxMixin:
    """Adds JSON endpoints to a ModelAdmin, for whatever it opts into.

    Inert by default: with none of the three attributes set, no URL is
    registered and nothing about the admin changes.
    """

    #: Boolean fields this admin will flip from the changelist. An allowlist,
    #: not a convenience -- the field name arrives from the browser.
    ajax_toggle_fields = ()

    #: Names from `actions` that may be run against a single row. Also an
    #: allowlist: `delete_selected` is registered on every ModelAdmin and must
    #: not be reachable from a row button.
    ajax_row_actions = ()

    #: `list_display` names re-rendered into every successful response, so the
    #: row that was just changed catches up without a reload.
    ajax_refresh_cells = ()

    # --- wiring ------------------------------------------------------------

    def get_urls(self):
        # Before super(), or Django's `<path:object_id>/change/` matches
        # "salon-ajax/toggle/" first and routes it to the change form.
        return [*self.get_ajax_urls(), *super().get_urls()]

    def get_ajax_urls(self):
        """The seam. Subclasses add their own endpoints by extending this."""
        urls = []
        if self.ajax_toggle_fields:
            urls.append(
                path(
                    "salon-ajax/toggle/",
                    self.ajax_toggle_view,
                    name=self.ajax_url_name("toggle"),
                )
            )
        if self.ajax_row_actions:
            urls.append(
                path(
                    "salon-ajax/action/",
                    self.ajax_action_view,
                    name=self.ajax_url_name("action"),
                )
            )
        return urls

    def ajax_url_name(self, suffix):
        opts = self.model._meta
        return "{}_{}_ajax_{}".format(opts.app_label, opts.model_name, suffix)

    def ajax_endpoints(self):
        """URLs for this admin, for the page's config block."""
        endpoints = {}
        if self.ajax_toggle_fields:
            endpoints["toggle"] = reverse("admin:" + self.ajax_url_name("toggle"))
            endpoints["toggleFields"] = list(self.ajax_toggle_fields)
        if self.ajax_row_actions:
            endpoints["action"] = reverse("admin:" + self.ajax_url_name("action"))
        return endpoints

    # --- shared helpers ----------------------------------------------------

    def ajax_object(self, request, pk):
        """Fetch one row, refusing it if this user may not change it.

        `has_change_permission(request, obj)` is the same method the changelist
        and the change form ask, so a per-object rule written once is honoured
        here too rather than needing to be repeated.
        """
        if pk in (None, ""):
            raise AdminAjaxError("No row was given.", 400)
        try:
            obj = self.get_queryset(request).get(pk=pk)
        except (ObjectDoesNotExist, ValueError, TypeError):
            raise AdminAjaxError("That row no longer exists.", 404, "missing")
        if not self.has_change_permission(request, obj):
            raise AdminAjaxError(
                "You do not have permission to change that.", 403, "permission"
            )
        return obj

    def render_cells(self, obj, names=None):
        """Re-render `list_display` cells the way the changelist would.

        Goes through Django's own `lookup_field` / `display_for_field` rather
        than calling the display methods directly, so a boolean renders as the
        tick icon and a `format_html` pill renders as itself -- exactly as
        `django.contrib.admin.templatetags.admin_list.items_for_result` does.
        Nothing here is a second copy of a display method.
        """
        cells = {}
        for name in names if names is not None else self.ajax_refresh_cells:
            try:
                field, attr, value = lookup_field(name, obj, self)
            except (AttributeError, ObjectDoesNotExist, FieldDoesNotExist):
                continue
            if field is None or field.auto_created:
                boolean = getattr(attr, "boolean", False)
                html = display_for_value(value, self.get_empty_value_display(), boolean)
            else:
                html = display_for_field(value, field, self.get_empty_value_display())
            # The escape boundary. This HTML is assigned with innerHTML, and
            # some of these values are typed by members of the public --
            # a customer's name, an enquiry's subject. `format_html` output is
            # already safe and passes through; a plain string does not.
            cells[name] = conditional_escape(html)
        return cells

    def ajax_extra_payload(self, request, body):
        """Anything else this admin wants to send back. Overridden per admin."""
        return {}

    # --- endpoints ---------------------------------------------------------

    @admin_json_view
    def ajax_toggle_view(self, request, body):
        """Flip one boolean on one row."""
        field_name = body.get("field")
        if field_name not in self.ajax_toggle_fields:
            raise AdminAjaxError("That field cannot be changed from the list.", 400)

        field = self.model._meta.get_field(field_name)
        if not isinstance(field, models.BooleanField) or field.null:
            # A nullable boolean is three-state, and a checkbox cannot say
            # which of the three it means.
            raise AdminAjaxError("That field is not a simple yes/no.", 400)

        obj = self.ajax_object(request, body.get("pk"))

        # The desired value, not a flip. If the row on screen is stale, "set it
        # to off" still lands on off; "flip it" would turn it back on.
        setattr(obj, field_name, bool(body.get("value")))

        update_fields = [field_name]
        if any(f.name == "updated_at" for f in self.model._meta.fields):
            # auto_now only fires for fields named in update_fields.
            update_fields.append("updated_at")

        # save(), never queryset.update(). common/signals.py bumps the content
        # cache version on post_save, and update() does not send it -- which
        # would leave the public site serving an unpublished item until
        # something else happened to save.
        obj.save(update_fields=update_fields)

        # The list_editable checkbox this replaces wrote a LogEntry, so this
        # must too, or the admin's history quietly stops recording publishes.
        self.log_change(request, obj, [{"changed": {"fields": [field_name]}}])

        return {
            "pk": obj.pk,
            "field": field_name,
            "value": getattr(obj, field_name),
            "cells": self.render_cells(obj),
            **self.ajax_extra_payload(request, body),
        }

    @admin_json_view
    def ajax_action_view(self, request, body):
        """Run one of this admin's existing actions against one row.

        Runs the *registered action*, not a reimplementation of it. Whatever
        the bulk path does -- skipping cancelled bookings, warning about a
        missing visit time -- happens here for free and cannot drift.
        """
        name = body.get("action")
        if name not in self.ajax_row_actions:
            raise AdminAjaxError("Unknown action.", 400)

        available = self.get_actions(request)
        if name not in available:
            raise AdminAjaxError(
                "You do not have permission to do that.", 403, "permission"
            )

        obj = self.ajax_object(request, body.get("pk"))
        func = available[name][0]
        # A one-row queryset, so the action's own loop and messages are
        # unchanged. Deliberately not wrapped in transaction.atomic(): approve()
        # opens its own, and an outer block would hold its select_for_update
        # lock across this whole request including serialising the response.
        func(self, request, self.get_queryset(request).filter(pk=obj.pk))

        obj.refresh_from_db()
        return {
            "pk": obj.pk,
            "cells": self.render_cells(obj),
            **self.ajax_extra_payload(request, body),
        }
