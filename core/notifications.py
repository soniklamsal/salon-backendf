"""Putting a booking or an enquiry in front of staff who are already looking.

`common/notifications.py` sends the email. This writes the row behind the bell
in the admin navbar. They are separate on purpose: one is SMTP, a background
thread and a rendered template, the other is a single insert, and a module
that did both would be about two unrelated failures at once.

Both are called from the same two places in `api/views.py`, next to each
other, which is what keeps "something arrived" from meaning different things
in different code paths.

Every function here swallows its own failures. A notification is a
convenience; a customer who has filled in the booking form and uploaded a
payment screenshot must not be shown an error because a convenience could not
be written.
"""

import logging

from django.db import DatabaseError

from core.models import AdminNotification

logger = logging.getLogger("core")


def _record(kind, obj, title, summary) -> AdminNotification | None:
    """Insert one row, or log and return None.

    The truncation is not decoration. `title` and `summary` are built from
    text a stranger typed into a public form, and a name longer than the
    column would otherwise raise here -- inside the request that is trying to
    save their booking.
    """
    meta = obj._meta
    try:
        notification = AdminNotification.objects.create(
            kind=kind,
            title=title[:200],
            summary=summary[:255],
            target_app_label=meta.app_label,
            target_model=meta.model_name,
            target_object_id=str(obj.pk),
        )
    except (DatabaseError, ValueError):
        logger.exception("Could not record an admin notification for %s", obj)
        return None

    try:
        AdminNotification.prune()
    except DatabaseError:
        # A table that is one row too long is not worth losing the row that
        # was just written, which is already committed by this point.
        logger.warning("Could not prune admin notifications", exc_info=True)

    return notification


def record_new_booking(appointment) -> AdminNotification | None:
    """Ring the bell for a booking that was just created."""
    parts = []
    if appointment.service_id and appointment.service:
        parts.append(appointment.service.label)
    if appointment.barber_id and appointment.barber:
        parts.append(f"with {appointment.barber.name}")
    if appointment.phone:
        parts.append(f"· {appointment.phone}")

    return _record(
        AdminNotification.Kind.BOOKING,
        appointment,
        title=appointment.name,
        summary=" ".join(parts),
    )


def record_new_contact_message(message) -> AdminNotification | None:
    """Ring the bell for an enquiry that was just submitted."""
    return _record(
        AdminNotification.Kind.ENQUIRY,
        message,
        title=message.subject or message.name,
        # The first line of the message rather than the subject again. It is
        # what tells somebody glancing at the dropdown whether this needs
        # answering now or after lunch.
        summary=f"{message.name}: {message.message}".replace("\n", " ").strip(),
    )
