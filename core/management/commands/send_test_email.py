"""Prove the email settings work, from a terminal.

    python manage.py send_test_email you@example.com

The same check the admin's "Send test email" button runs -- both call
`common.mail_test.send_test_message` -- so the two can never disagree about
whether mail is working. This one exists for a deploy, where there may be no
browser to hand and the interesting question is which of the admin and `.env`
is actually in force.

Prints the resolved settings (never the password) before sending, because the
usual surprise is not that the send failed but that it went out with settings
from the source nobody was looking at.
"""

from django.core.management.base import BaseCommand, CommandError

from common.email_config import active_config
from common.mail_test import send_test_message


class Command(BaseCommand):
    help = "Send a test email to check the SMTP configuration."

    def add_arguments(self, parser):
        parser.add_argument(
            "recipient",
            nargs="?",
            help=(
                "Where to send it. Defaults to the first configured "
                "notification address."
            ),
        )

    def handle(self, *args, **options):
        config = active_config()

        recipient = options.get("recipient")
        if not recipient:
            if not config.recipients:
                raise CommandError(
                    "No recipient given and none is configured. Pass an "
                    "address, or set one in the admin under Email / SMTP "
                    "settings."
                )
            recipient = config.recipients[0]

        self.stdout.write("Sending with:")
        for label, value in (
            ("Settings from", "the admin screen" if config.source == "admin" else ".env"),
            ("Host", "{}:{}".format(config.host, config.port)),
            ("Encryption", "SSL" if config.use_ssl else "STARTTLS" if config.use_tls else "none"),
            ("Username", config.username or "(blank)"),
            # Length only. An App Password is 16 characters, and the usual
            # mistake is pasting something else entirely.
            (
                "Password",
                "set, {} characters".format(len(config.password))
                if config.password
                else "(blank)",
            ),
            ("From", config.from_email or "(blank)"),
            ("To", recipient),
        ):
            self.stdout.write("  {:<14} {}".format(label, value))
        self.stdout.write("")

        if not config.is_configured:
            self.stdout.write(
                self.style.WARNING(
                    "No username and password from either source, so this is "
                    "the console backend: the message is printed below and "
                    "nothing is sent."
                )
            )
            self.stdout.write("")

        ok, detail = send_test_message(recipient)

        if not ok and config.is_configured:
            raise CommandError(detail)

        self.stdout.write(
            self.style.SUCCESS("Sent. Look in {} (and its spam folder).".format(recipient))
            if ok
            else self.style.WARNING(detail)
        )
