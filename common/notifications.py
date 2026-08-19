"""Tell the salon when a booking or an enquiry arrives.

The admin already holds every submission, but only if somebody thinks to open
it. These are the messages that make a new booking show up where the salon is
already looking, which is the inbox.

Three rules hold everywhere in this module, and they are the whole design:

*   **A failed email never fails the submission.** A customer who filled in the
    booking form and uploaded a payment screenshot has done their part; a
    Gmail outage, a revoked App Password or an expired card on the account
    must not turn that into an error page. Everything is caught and logged.
*   **Nothing is sent until the row is committed.** `transaction.on_commit`
    means the salon is never told about a booking that then rolled back.
*   **The customer does not wait for Gmail.** The SMTP round trip is a second
    or two on a good day and `EMAIL_TIMEOUT` on a bad one, so it happens on a
    background thread while the response goes out. `EMAIL_NOTIFY_ASYNC=False`
    sends inline instead, which is what the tests use and what a future move
    to a real task queue would replace.

Every message goes out as both plain text and HTML -- `multipart/alternative`,
with the text part first so a client that prefers it takes it. The HTML is in
`templates/email/`, styled from the same tokens as the site; the text part is
built here and is what a terminal client, a screen reader in plain-text mode
and a spam filter all read. Neither is a second-class copy of the other: any
detail worth mailing appears in both.

Rendering happens on the request thread, before anything is queued. That is
deliberate -- it keeps the delivery thread away from the ORM, so it never
opens a second database connection it would then have to remember to close.

Nothing here emails the *customer*. That is a deliberate gap, not an oversight
-- see `notify_new_booking` for what would need deciding first.
"""

import logging
import threading

from django.apps import apps
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import DatabaseError, transaction
from django.template.loader import render_to_string

from common.email_config import active_config

logger = logging.getLogger("common")

# Named so a stuck send is identifiable in a thread dump, and so the tests
# can wait for the real threaded path rather than only the inline one.
NOTIFY_THREAD_NAME = "salon-notify"


def _brand_name() -> str:
    """The wordmark for the email header, or a plain default.

    `apps.get_model` rather than an import, for the same reason
    `common.email_config` does it: `common` is the base layer and `core` sits
    above it, so importing upward here is a cycle waiting to happen.

    A missing row or an unreachable database is not a reason to lose the
    email, so every failure lands on the default.
    """
    try:
        SiteSettings = apps.get_model("core", "SiteSettings")
        return SiteSettings.load().brand_name or "Salon"
    except (LookupError, DatabaseError, AttributeError):
        return "Salon"


def _render(template: str, context: dict) -> str:
    """The HTML part, or "" if it cannot be built.

    Swallows on purpose. A template that fails to render is a bug worth the
    log line, but the salon should still get the plain-text notification
    telling them somebody just booked.
    """
    try:
        return render_to_string(template, {"brand_name": _brand_name(), **context})
    except Exception:
        logger.exception("Could not render notification template: %s", template)
        return ""


def _deliver(subject: str, body: str, html: str, reply_to: list[str]) -> None:
    """The blocking half. Runs on a background thread; must not raise."""
    config = active_config()
    try:
        email = EmailMultiAlternatives(
            subject=subject,
            body=body,
            from_email=config.from_email,
            to=config.recipients,
            # So hitting Reply in Gmail answers the customer rather than the
            # salon's own sending address.
            reply_to=reply_to or None,
        )
        if html:
            email.attach_alternative(html, "text/html")
        email.send(fail_silently=False)
    except Exception:
        # Broad on purpose. The caller is a thread with nowhere to return an
        # error to, and the alternative to swallowing it is a traceback on
        # stderr that no longer names the booking it belongs to.
        logger.exception("Could not send notification email: %s", subject)


def _queue(
    subject: str,
    body: str,
    html: str = "",
    reply_to: list[str] | None = None,
) -> None:
    """Send once the surrounding transaction commits, off the request thread."""
    if not active_config().recipients:
        # Not an error. An install that has not filled in .env still takes
        # bookings; it just does not announce them.
        logger.debug("No SALON_NOTIFY_EMAILS configured; skipping: %s", subject)
        return

    def dispatch():
        if not getattr(settings, "EMAIL_NOTIFY_ASYNC", True):
            _deliver(subject, body, html, reply_to or [])
            return
        # daemon=True so a shutdown is never held open by a notification. Both
        # parts are already rendered by this point and the thread touches no
        # model, which is what keeps it from opening a second database
        # connection it would then have to remember to close.
        threading.Thread(
            target=_deliver,
            args=(subject, body, html, reply_to or []),
            daemon=True,
            name=NOTIFY_THREAD_NAME,
        ).start()

    transaction.on_commit(dispatch)


def notify_new_booking(appointment) -> None:
    """Email the salon about a booking that was just created.

    Sends to the salon only. Confirming to the *customer* is a real feature
    and deliberately not folded in here: it puts the site's address in front
    of a member of the public, which makes SPF/DKIM on the sending domain and
    an unsubscribe story matter in a way that an internal notice does not.
    """
    lines = [
        f"Name:     {appointment.name}",
        f"Phone:    {appointment.phone or '-'}",
        f"Email:    {appointment.email or '-'}",
        f"Address:  {appointment.address or '-'}",
        f"Service:  {appointment.service.label if appointment.service else '-'}",
        f"Barber:   {appointment.barber.name if appointment.barber else '-'}",
        f"Ref:      {appointment.reference or '-'}",
        f"Status:   {appointment.get_status_display()}",
    ]
    if appointment.notes:
        lines += ["", "Notes:", appointment.notes]
    if appointment.payment_screenshot:
        # The file itself is deliberately not attached. It is a financial
        # record living behind a signed URL, and a mailbox is not where it
        # should end up in the clear.
        lines += ["", "A payment screenshot was uploaded; view it in the admin."]

    _queue(
        subject=f"New booking: {appointment.name}",
        body="\n".join(lines) + "\n",
        html=_render("email/booking.html", {"appointment": appointment}),
        reply_to=[appointment.email] if appointment.email else [],
    )


def notify_new_contact_message(message) -> None:
    """Email the salon about an enquiry that was just submitted."""
    lines = [
        f"Name:     {message.name}",
        f"Email:    {message.email or '-'}",
        f"Subject:  {message.subject or '-'}",
        "",
        message.message,
    ]

    _queue(
        subject=f"New enquiry: {message.subject or message.name}",
        body="\n".join(lines) + "\n",
        html=_render("email/contact.html", {"message": message}),
        reply_to=[message.email] if message.email else [],
    )
