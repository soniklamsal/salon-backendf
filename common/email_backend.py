"""The email backend the project sends through.

Django resolves `EMAIL_BACKEND` once, at startup, and an SMTP backend reads
its host and password from `settings` in `__init__`. Neither of those can see
a password typed into the admin ten minutes later, which is why this exists:
one backend, pointed at by settings, that asks `common.email_config` what to
use each time it is constructed.

It also owns the console fallback. With no username and password from either
source, there is nothing to log into, so mail is printed instead of sent --
which keeps a fresh clone and the test suite working with no configuration at
all, and makes "I have not set this up yet" a visible state rather than a
stream of authentication failures.
"""

import logging

from django.core.mail.backends.console import EmailBackend as ConsoleBackend
from django.core.mail.backends.smtp import EmailBackend as SMTPBackend

from common.email_config import active_config

logger = logging.getLogger("common")


class ConfiguredEmailBackend(SMTPBackend):
    """SMTP using the admin's settings, falling back to `.env`, then console.

    Subclasses the SMTP backend and delegates to a console one when there is
    nothing to authenticate with, rather than the other way round: the SMTP
    path is the real one, and the console path is a stand-in for it.
    """

    def __init__(self, *args, fail_silently=False, **kwargs):
        config = active_config()
        self._config = config
        self._console = None

        if not config.is_configured:
            # No credentials from either source. Print instead of sending.
            self._console = ConsoleBackend(fail_silently=fail_silently)

        # Explicit keyword arguments, not `settings`, are what make the
        # admin's values reach the SMTP connection at all.
        super().__init__(
            host=config.host,
            port=config.port,
            username=config.username,
            password=config.password,
            use_tls=config.use_tls,
            use_ssl=config.use_ssl,
            timeout=config.timeout,
            fail_silently=fail_silently,
        )

    def send_messages(self, email_messages):
        if self._console is not None:
            return self._console.send_messages(email_messages)

        # Anything left without an explicit sender gets the resolved one, so a
        # `send_mail()` call elsewhere in the project cannot end up sending as
        # whatever DEFAULT_FROM_EMAIL happened to be at startup.
        for message in email_messages:
            if not message.from_email and self._config.from_email:
                message.from_email = self._config.from_email

        return super().send_messages(email_messages)
