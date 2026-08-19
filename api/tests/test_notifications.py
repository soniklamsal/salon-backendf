"""The salon finds out when something arrives.

These tests care about two things and not about wording. First, that a
submission produces exactly one notification with the details the salon needs
to act on it. Second — and this is the one worth having — that a broken mail
server cannot cost the salon a booking. That failure mode is silent by
definition: it only shows up as customers who filled in the form and were told
something went wrong, which nobody reports as an email problem.

`locmem` is Django's test email backend; TestCase wraps each test in a
transaction that never commits, so `captureOnCommitCallbacks` is what actually
runs the queued send.

Most of these run with EMAIL_NOTIFY_ASYNC off, because asserting on a thread
that may not have finished yet is how a test suite earns a reputation for
flaking. `ThreadedDeliveryTests` at the bottom covers the threaded path that
production actually uses, by waiting for the thread instead of hoping.
"""

import shutil
import tempfile
import threading

from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from api.tests.test_bookings import png_upload
from bookings.models import Appointment, Barber, ContactMessage
from common.notifications import NOTIFY_THREAD_NAME
from sections.models import Service


def join_notification_threads(timeout: float = 10.0) -> None:
    """Block until every in-flight notification thread has finished."""
    for thread in threading.enumerate():
        if thread.name == NOTIFY_THREAD_NAME:
            thread.join(timeout)


class HtmlPartMixin:
    """Reaching the HTML half of a multipart/alternative message."""

    def html_part(self, sent) -> str:
        """The text/html alternative, failing the test if there isn't one.

        Returning "" instead would let an email that quietly stopped sending
        HTML pass every assertNotIn in this file.
        """
        for content, mimetype in sent.alternatives:
            if mimetype == "text/html":
                return content
        self.fail("The message has no text/html part.")


@override_settings(
    SALON_NOTIFY_EMAILS=["salon@example.com"],
    DEFAULT_FROM_EMAIL="site@example.com",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PUBLIC_BASE_URL="https://salon.example.com",
    EMAIL_NOTIFY_ASYNC=False,
)
class ContactNotificationTests(HtmlPartMixin, TestCase):
    def post(self, **overrides):
        payload = {
            "name": "Asha",
            "email": "asha@example.com",
            "subject": "Opening hours",
            "message": "Are you open on Sunday?",
        }
        payload.update(overrides)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse("contact-create"), payload)

    def test_an_enquiry_emails_the_salon(self):
        response = self.post()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(mail.outbox), 1)

        sent = mail.outbox[0]
        self.assertEqual(sent.to, ["salon@example.com"])
        self.assertEqual(sent.from_email, "site@example.com")
        self.assertIn("Opening hours", sent.subject)
        self.assertIn("Are you open on Sunday?", sent.body)

    def test_reply_goes_to_the_customer_not_the_salon(self):
        """Otherwise Reply in Gmail answers the salon's own sending address."""
        self.post()
        self.assertEqual(mail.outbox[0].reply_to, ["asha@example.com"])

    def test_no_admin_link_reaches_the_inbox(self):
        """Deliberately removed.

        The link only ever resolved for somebody already signed in to the
        admin, and on a development machine it was a 127.0.0.1 URL that meant
        nothing on the phone actually reading the email. The enquiry itself is
        in the body; the admin is where you go to reply, not where the email
        has to send you.
        """
        self.post()
        for part in (mail.outbox[0].body, self.html_part(mail.outbox[0])):
            self.assertNotIn("Open in admin", part)
            self.assertNotIn("/admin/", part)

    def test_both_a_text_and_an_html_part_go_out(self):
        """multipart/alternative: the text part is not a leftover."""
        self.post()
        sent = mail.outbox[0]
        self.assertEqual(sent.content_subtype, "plain")
        self.assertEqual(
            [mime for _, mime in sent.alternatives], ["text/html"]
        )

    def test_the_enquiry_is_readable_in_the_html_part_too(self):
        """Whatever is worth mailing is in both parts, not only the pretty one."""
        self.post()
        html = self.html_part(mail.outbox[0])
        for expected in ("Asha", "asha@example.com", "Opening hours", "Sunday"):
            self.assertIn(expected, html)

    def test_a_customer_cannot_inject_markup_through_the_form(self):
        """The message is a stranger's text rendered into HTML we then send."""
        self.post(message="<script>alert(1)</script> and <b>bold</b>")
        html = self.html_part(mail.outbox[0])
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    @override_settings(SALON_NOTIFY_EMAILS=[])
    def test_no_recipients_configured_is_not_an_error(self):
        """A fresh install takes enquiries; it just does not announce them."""
        response = self.post()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(ContactMessage.objects.count(), 1)

    def test_a_rejected_enquiry_sends_nothing(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("contact-create"), {})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(mail.outbox), 0)

    def test_a_dead_mail_server_does_not_cost_the_salon_the_enquiry(self):
        """The whole point. The row is saved and the customer is told 201."""
        with patch(
            "django.core.mail.EmailMessage.send", side_effect=OSError("no route")
        ):
            response = self.post()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(ContactMessage.objects.count(), 1)


@override_settings(
    SALON_NOTIFY_EMAILS=["salon@example.com"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PUBLIC_BASE_URL="https://salon.example.com",
    EMAIL_NOTIFY_ASYNC=False,
)
class BookingNotificationTests(HtmlPartMixin, TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._tmp = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        # Screenshots are financial records and never belong in the repo's
        # own private-media folder during a test run.
        self.overridden = override_settings(PRIVATE_MEDIA_ROOT=self._tmp)
        self.overridden.enable()
        self.addCleanup(self.overridden.disable)
        # The booking throttle counts into a process-wide cache that outlives
        # a test; without this the eleventh POST of the run gets a 429 and the
        # failure looks like it belongs to whatever test ran eleventh.
        cache.clear()

        self.service = Service.objects.create(label="Fresh Cut", is_published=True)
        self.barber = Barber.objects.create(name="Ram", is_published=True)

    def post(self, **overrides):
        payload = {
            "name": "Bikash",
            "phone": "9800000000",
            "address": "Thamel",
            "notes": "A trim, not too short",
            "service": self.service.pk,
            "barber": self.barber.pk,
            "paymentScreenshot": png_upload(),
        }
        payload.update(overrides)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse("appointment-create"), payload)

    def test_a_booking_emails_the_salon_with_what_it_needs_to_act_on(self):
        response = self.post()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(mail.outbox), 1)

        sent = mail.outbox[0]
        self.assertEqual(sent.to, ["salon@example.com"])
        self.assertIn("Bikash", sent.subject)
        for expected in ("Bikash", "9800000000", "Thamel", "Fresh Cut", "Ram"):
            self.assertIn(expected, sent.body)

    def test_the_screenshot_is_named_but_never_attached(self):
        """It is a financial record behind a signed URL, not mail content."""
        self.post()
        sent = mail.outbox[0]
        self.assertEqual(sent.attachments, [])
        self.assertIn("payment screenshot was uploaded", sent.body)

    def test_the_booking_reference_is_in_the_body(self):
        """It is how the salon ties the email to the customer's own screen."""
        self.post()
        reference = Appointment.objects.get().reference
        self.assertTrue(reference)
        self.assertIn(reference, mail.outbox[0].body)

    def test_the_html_part_carries_the_same_booking_details(self):
        """A salon reading the pretty half must not be reading a shorter one."""
        self.post()
        html = self.html_part(mail.outbox[0])
        reference = Appointment.objects.get().reference
        for expected in (
            "Bikash",
            "9800000000",
            "Thamel",
            "Fresh Cut",
            "Ram",
            reference,
            "A trim, not too short",
        ):
            self.assertIn(expected, html)

    def test_the_html_part_names_the_screenshot_without_linking_the_admin(self):
        self.post()
        html = self.html_part(mail.outbox[0])
        self.assertIn("payment screenshot was uploaded", html)
        self.assertNotIn("/admin/", html)

    def test_an_anonymous_booking_has_no_reply_to_rather_than_a_blank_one(self):
        """The form does not ask for an email; it comes from the Clerk token."""
        self.post()
        self.assertEqual(Appointment.objects.get().email, "")
        self.assertFalse(mail.outbox[0].reply_to)

    def test_a_dead_mail_server_does_not_cost_the_salon_the_booking(self):
        with patch(
            "django.core.mail.EmailMessage.send", side_effect=OSError("no route")
        ):
            response = self.post()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Appointment.objects.count(), 1)


@override_settings(
    SALON_NOTIFY_EMAILS=["salon@example.com"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_NOTIFY_ASYNC=True,
)
class ThreadedDeliveryTests(TestCase):
    """The path production runs: delivery on a background thread."""

    def submit(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("contact-create"),
                {
                    "name": "Asha",
                    "email": "asha@example.com",
                    "subject": "Hello",
                    "message": "Hi",
                },
            )
        join_notification_threads()
        return response

    def test_the_thread_actually_delivers(self):
        self.assertEqual(self.submit().status_code, 201)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["salon@example.com"])

    def test_a_thread_that_raises_is_swallowed_and_logged(self):
        """A traceback on a daemon thread has nowhere to go but the log."""
        with patch(
            "django.core.mail.EmailMessage.send", side_effect=OSError("no route")
        ):
            with self.assertLogs("common", level="ERROR") as captured:
                response = self.submit()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(ContactMessage.objects.count(), 1)
        self.assertTrue(
            any("Could not send notification email" in line for line in captured.output)
        )
