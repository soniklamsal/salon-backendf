"""One real send, and a readable account of why it failed.

Shared by the admin's "Send test email" button and `manage.py
send_test_email`, so the two cannot drift into disagreeing about whether the
settings work.

The error translation is the substance here. SMTP failures are famously
uninformative -- Gmail answers a missing App Password, 2-Step Verification
being off, and a typo'd address with the same 535 -- and the person reading
this is a salon owner in an admin screen, not someone who is going to search
the response code.
"""

import smtplib

from django.core.mail import EmailMessage

from common.email_config import active_config

BODY = (
    "This is a test from the Salon website.\n\n"
    "If you are reading it in your inbox, the email settings are correct and "
    "the site can send you booking and enquiry notifications.\n"
)

AUTH_HELP = (
    "the mail server rejected the login. For Gmail this is almost always the "
    "password: it must be a 16-character App Password from "
    "myaccount.google.com/apppasswords, not the account's own password, and "
    "2-Step Verification has to be on for that page to offer one. A Google "
    "Workspace account may have App Passwords blocked by its administrator."
)

CONNECT_HELP = (
    "could not reach the mail server. Check the server and port under "
    "Server (advanced) -- Gmail is smtp.gmail.com on port 587 -- and whether "
    "outbound mail is blocked. Shared hosting often blocks port 587; port 465 "
    "with SSL sometimes works where it does not."
)


def send_test_message(recipient: str) -> tuple[bool, str]:
    """Send one test email. Returns (ok, human-readable detail).

    Never raises. Both callers are reporting a result to somebody rather than
    handling an exception, and an admin button that 500s on a wrong password
    is worse than one that says the password is wrong.
    """
    config = active_config()

    if not config.is_configured:
        return (
            False,
            "no address and password are set, so the message was written to "
            "the server log instead of sent.",
        )

    message = EmailMessage(
        subject="Salon website test email",
        body=BODY,
        from_email=config.from_email or config.username,
        to=[recipient],
    )

    try:
        message.send(fail_silently=False)
    except smtplib.SMTPAuthenticationError:
        return False, AUTH_HELP
    except (smtplib.SMTPException, OSError) as exc:
        return False, "{} ({})".format(CONNECT_HELP, exc)

    return True, "sent to {}".format(recipient)
