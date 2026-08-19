"""Where the SMTP settings actually come from.

Two sources, and one rule: **the admin wins where it has an answer**.

    admin screen  ->  .env  ->  built-in defaults

That order is the point of the whole module. `.env` is what a fresh clone, CI
and the test suite run on, and none of those have a database row to read. The
admin is what the salon uses, and somebody who has just typed a password into
a form expects it to be the one that gets used.

Resolved per send rather than at startup, so saving the form takes effect on
the next booking instead of the next deploy. That costs one indexed primary-key
read per email, which is nothing next to an SMTP round trip.
"""

import logging
from dataclasses import dataclass, field

from django.apps import apps
from django.conf import settings
from django.db import DatabaseError

logger = logging.getLogger("common")


@dataclass
class MailConfig:
    """Everything needed to send, from whichever source answered."""

    host: str
    port: int
    username: str
    password: str
    use_tls: bool
    use_ssl: bool
    timeout: int
    from_email: str
    recipients: list[str] = field(default_factory=list)
    # "admin" or ".env" -- shown by the test-email command and the admin
    # screen, because "which of the two is it using" is the first question
    # anyone asks when mail goes to the wrong place.
    source: str = ".env"

    @property
    def is_configured(self) -> bool:
        """Enough to attempt a real send. Anything less means console."""
        return bool(self.username and self.password)


def _from_env() -> MailConfig:
    return MailConfig(
        host=settings.EMAIL_HOST,
        port=settings.EMAIL_PORT,
        username=settings.EMAIL_HOST_USER,
        password=settings.EMAIL_HOST_PASSWORD,
        use_tls=settings.EMAIL_USE_TLS,
        use_ssl=settings.EMAIL_USE_SSL,
        timeout=settings.EMAIL_TIMEOUT,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipients=list(settings.SALON_NOTIFY_EMAILS),
        source=".env",
    )


def _stored():
    """The admin row, or None if there isn't one that can be read.

    `apps.get_model` rather than an import: `common` is the base layer and
    `core` sits above it, so importing upward here would be a cycle waiting to
    happen the first time `core` needs anything from `common` at import time.

    Swallows DatabaseError on purpose. This runs during `migrate`, on a
    database whose tables may not exist yet, and a missing table must not stop
    the migration that is about to create it.
    """
    try:
        EmailSettings = apps.get_model("core", "EmailSettings")
    except LookupError:
        return None
    try:
        return EmailSettings.objects.first()
    except DatabaseError:
        logger.debug("Email settings table not readable yet; using .env.")
        return None


def active_config() -> MailConfig:
    """The settings to send with right now."""
    config = _from_env()

    stored = _stored()
    if stored is None or not stored.is_enabled:
        return config

    # Only non-blank values override, so filling in just a username and
    # password on the form is a complete Gmail setup and everything else keeps
    # whatever `.env` said.
    if stored.username:
        config.username = stored.username
    if stored.password:
        config.password = stored.password
    if stored.host:
        config.host = stored.host

    if stored.security == "ssl":
        config.use_ssl, config.use_tls = True, False
        config.port = stored.port or 465
    elif stored.security == "none":
        config.use_ssl, config.use_tls = False, False
        config.port = stored.port or 25
    else:
        config.use_ssl, config.use_tls = False, True
        config.port = stored.port or 587

    if stored.from_email():
        config.from_email = stored.from_email()
    if stored.recipients():
        config.recipients = stored.recipients()

    config.source = "admin"
    return config


def notification_recipients() -> list[str]:
    """Who hears about a new booking or enquiry."""
    return active_config().recipients
