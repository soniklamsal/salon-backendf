"""What the notification bell in the admin navbar asks for.

Two endpoints, both POST and both JSON, wired in `config/urls.py` ahead of
`admin.site.urls` -- see the note there for why they are not on a ModelAdmin.

The bell polls `feed` on a timer. That is a query every staff member's open
tab makes twice a minute, so the shape of it matters: one indexed count and at
most `FEED_LIMIT` rows, never the whole table, and no join back to bookings or
contact messages because `AdminNotification` already carries what is shown.

Everything is scoped to `request.user`. Read state is per person -- see the
model -- so "how many are unread" has no answer that is not somebody's.
"""

import logging

from django.utils import timezone

from common.admin_ajax import AdminAjaxError, admin_json_endpoint
from core.models import AdminNotification

logger = logging.getLogger("core")

#: How many entries the dropdown holds. The bell is for what arrived while
#: somebody was working, not an archive -- the changelists are the archive.
FEED_LIMIT = 12


def _entry(notification, unread: bool) -> dict:
    return {
        "id": notification.pk,
        "kind": notification.kind,
        "title": notification.title,
        "summary": notification.summary,
        "url": notification.admin_url(),
        "at": timezone.localtime(notification.created_at).isoformat(),
        "unread": unread,
    }


def _feed_for(user) -> dict:
    """The dropdown's contents and the badge's number, for one person.

    Two queries: the page of rows, and the set of those this user has already
    read. Deliberately not `exclude(read_by=user)` per row -- that is a
    subquery for every entry rendered.
    """
    page = list(AdminNotification.objects.all()[:FEED_LIMIT])
    read_ids = set(
        AdminNotification.objects.filter(pk__in=[n.pk for n in page], read_by=user)
        .values_list("pk", flat=True)
    )
    return {
        "unread": AdminNotification.unread_for(user).count(),
        "items": [_entry(n, n.pk not in read_ids) for n in page],
    }


@admin_json_endpoint
def feed(request, body):
    """Everything the bell needs to render itself, in one call."""
    return _feed_for(request.user)


@admin_json_endpoint
def mark_read(request, body):
    """Mark one entry, or everything, as read by this user.

    `{"id": 7}` marks one -- what clicking an entry in the dropdown sends.
    `{"all": true}` marks the visible lot, for the "Mark all read" control.

    Returns the whole feed rather than just the new count, so the badge and
    the list can never disagree after a click: one response, one render.
    """
    if body.get("all"):
        # Only what this user could actually see. Marking rows that were never
        # on screen read is how a notification silently disappears.
        unread = AdminNotification.unread_for(request.user)[:FEED_LIMIT]
        for notification in list(unread):
            notification.read_by.add(request.user)
        return _feed_for(request.user)

    pk = body.get("id")
    if pk in (None, ""):
        raise AdminAjaxError("No notification was given.", 400)

    try:
        notification = AdminNotification.objects.get(pk=pk)
    except (AdminNotification.DoesNotExist, ValueError, TypeError):
        # Pruned out from under an open dropdown, most likely. The tab should
        # refresh its list rather than be told off about it.
        raise AdminAjaxError(
            "That notification is no longer there.", 404, "missing"
        )

    # add() on an existing pair is a no-op, so clicking the same entry twice
    # cannot drive the count negative.
    notification.read_by.add(request.user)
    return _feed_for(request.user)
