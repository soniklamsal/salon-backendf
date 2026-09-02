"""The bell in the admin navbar.

Three things are worth testing here and the rest is markup. First, that a
submission produces exactly one notification -- the salon should not be told
twice about one booking. Second, that read state is *per person*: the bug this
guards against is a manager opening the bell and clearing it for the owner,
which is invisible until somebody misses a booking. Third, that the endpoints
refuse anybody who is not signed-in staff, because they hang off the URL conf
rather than `admin_view` and so have no framework check behind them.

The polling cost is asserted too. The feed is fetched by every open admin tab
twice a minute, and it is the one query in this project that gets run whether
or not anyone is doing anything.
"""

import json

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from bookings.models import Appointment, Barber, ContactMessage
from core.models import AdminNotification
from core.notifications import record_new_booking, record_new_contact_message
from sections.models import Service


class RecordingTests(TestCase):
    """Turning a submission into a row somebody can click."""

    def setUp(self):
        self.service = Service.objects.create(label="Fresh Cut", is_published=True)
        self.barber = Barber.objects.create(name="Ram", is_published=True)

    def test_a_booking_records_what_the_dropdown_shows(self):
        appointment = Appointment.objects.create(
            name="Bikash", phone="9800000000",
            service=self.service, barber=self.barber,
        )
        record_new_booking(appointment)

        notification = AdminNotification.objects.get()
        self.assertEqual(notification.kind, AdminNotification.Kind.BOOKING)
        self.assertEqual(notification.title, "Bikash")
        self.assertIn("Fresh Cut", notification.summary)
        self.assertIn("Ram", notification.summary)
        self.assertEqual(
            notification.admin_url(),
            reverse("admin:bookings_appointment_change", args=[appointment.pk]),
        )

    def test_an_enquiry_records_the_message_not_just_the_subject(self):
        """The subject is the heading; the summary is what tells you whether
        this needs answering now."""
        message = ContactMessage.objects.create(
            name="Asha", email="asha@example.com",
            subject="Opening hours", message="Are you open\non Sunday?",
        )
        record_new_contact_message(message)

        notification = AdminNotification.objects.get()
        self.assertEqual(notification.kind, AdminNotification.Kind.ENQUIRY)
        self.assertEqual(notification.title, "Opening hours")
        self.assertIn("Are you open on Sunday?", notification.summary)

    def test_a_long_message_does_not_break_the_submission_that_carries_it(self):
        """`summary` is built from `ContactMessage.message`, a TextField.

        Nothing caps that at the form, so the only thing standing between a
        thousand-word enquiry and a DataError -- raised inside the request
        trying to save it -- is the truncation in `_record`.
        """
        message = ContactMessage.objects.create(
            name="Asha", email="asha@example.com", message="x" * 5000,
        )
        self.assertIsNotNone(record_new_contact_message(message))
        self.assertEqual(len(AdminNotification.objects.get().summary), 255)

    def test_a_deleted_target_leaves_an_entry_without_a_link(self):
        """Worth still being able to see that a booking came in and went."""
        appointment = Appointment.objects.create(name="Bikash", phone="98")
        record_new_booking(appointment)
        notification = AdminNotification.objects.get()
        notification.target_model = "nosuchmodel"
        self.assertEqual(notification.admin_url(), "")

    def test_pruning_keeps_the_table_from_growing_without_bound(self):
        for index in range(6):
            AdminNotification.objects.create(
                kind=AdminNotification.Kind.BOOKING,
                title=f"Booking {index}",
                target_app_label="bookings",
                target_model="appointment",
                target_object_id=str(index),
            )
        AdminNotification.prune(keep=4)

        remaining = list(AdminNotification.objects.values_list("title", flat=True))
        self.assertEqual(len(remaining), 4)
        # Newest kept, oldest dropped.
        self.assertIn("Booking 5", remaining)
        self.assertNotIn("Booking 0", remaining)


@override_settings(SALON_NOTIFY_EMAILS=[])
class SubmissionTests(TestCase):
    """The public endpoints, from POST to a row in the bell."""

    def setUp(self):
        from django.core.cache import cache

        # The submissions throttle counts into a process-wide cache.
        cache.clear()

    def test_an_enquiry_through_the_api_rings_the_bell_once(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("contact-create"),
                {
                    "name": "Asha",
                    "email": "asha@example.com",
                    "subject": "Opening hours",
                    "message": "Are you open on Sunday?",
                },
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(AdminNotification.objects.count(), 1)

    def test_a_rejected_enquiry_rings_nothing(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("contact-create"), {})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(AdminNotification.objects.count(), 0)


class FeedEndpointTests(TestCase):
    """What the navbar polls, and who is allowed to poll it."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            "owner", password="pw", is_staff=True, is_active=True
        )
        cls.manager = User.objects.create_user(
            "manager", password="pw", is_staff=True, is_active=True
        )
        cls.customer = User.objects.create_user("customer", password="pw")

    def setUp(self):
        self.feed_url = reverse("admin_notifications")
        self.read_url = reverse("admin_notifications_read")

    def make(self, title="Bikash"):
        return AdminNotification.objects.create(
            kind=AdminNotification.Kind.BOOKING,
            title=title,
            target_app_label="bookings",
            target_model="appointment",
            target_object_id="1",
        )

    def feed(self):
        response = self.client.post(
            self.feed_url, data="{}", content_type="application/json"
        )
        return response, json.loads(response.content)

    def read(self, **body):
        response = self.client.post(
            self.read_url, data=json.dumps(body), content_type="application/json"
        )
        return response, json.loads(response.content)

    # --- access ---------------------------------------------------------

    def test_a_signed_out_visitor_is_told_so_in_json_not_redirected(self):
        """A 302 to the login page is HTML, and response.json() on it throws."""
        response, payload = self.feed()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(payload["reason"], "signed_out")

    def test_a_signed_in_non_staff_account_is_refused(self):
        """Every customer who books with Google has a User row."""
        self.client.force_login(self.customer)
        response, payload = self.feed()
        self.assertEqual(response.status_code, 401)

    def test_a_get_is_refused(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.feed_url)
        self.assertEqual(response.status_code, 405)

    # --- reading --------------------------------------------------------

    def test_the_feed_carries_the_count_and_the_entries(self):
        self.make("Bikash")
        self.make("Asha")
        self.client.force_login(self.owner)

        response, payload = self.feed()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["unread"], 2)
        self.assertEqual([item["title"] for item in payload["items"]], ["Asha", "Bikash"])
        self.assertTrue(all(item["unread"] for item in payload["items"]))

    def test_clicking_one_entry_drops_the_count_by_one(self):
        first = self.make("Bikash")
        self.make("Asha")
        self.client.force_login(self.owner)

        response, payload = self.read(id=first.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["unread"], 1)
        read = [item for item in payload["items"] if item["id"] == first.pk][0]
        self.assertFalse(read["unread"])

    def test_clicking_the_same_entry_twice_cannot_go_negative(self):
        notification = self.make()
        self.client.force_login(self.owner)

        self.read(id=notification.pk)
        _, payload = self.read(id=notification.pk)
        self.assertEqual(payload["unread"], 0)

    def test_mark_all_read_clears_the_badge(self):
        for index in range(3):
            self.make(f"Booking {index}")
        self.client.force_login(self.owner)

        _, payload = self.read(all=True)
        self.assertEqual(payload["unread"], 0)

    def test_one_persons_reading_does_not_clear_it_for_anybody_else(self):
        """The reason read state is a table and not a boolean column."""
        notification = self.make()

        self.client.force_login(self.owner)
        _, payload = self.read(id=notification.pk)
        self.assertEqual(payload["unread"], 0)

        self.client.force_login(self.manager)
        _, payload = self.feed()
        self.assertEqual(payload["unread"], 1)

    def test_an_entry_pruned_out_from_under_an_open_dropdown_says_so(self):
        self.client.force_login(self.owner)
        response, payload = self.read(id=999999)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(payload["reason"], "missing")

    def test_read_with_no_id_is_a_refusal_not_a_crash(self):
        self.client.force_login(self.owner)
        response, payload = self.read()
        self.assertEqual(response.status_code, 400)

    # --- cost -----------------------------------------------------------

    def test_the_feed_costs_a_fixed_number_of_queries(self):
        """Polled by every open tab twice a minute, whether or not anyone is
        doing anything. It must not be one query per entry."""
        for index in range(8):
            self.make(f"Booking {index}")
        self.client.force_login(self.owner)

        # The page, the read-ids, the count -- plus session and user lookups.
        with self.assertNumQueries(5):
            self.client.post(self.feed_url, data="{}", content_type="application/json")

    def test_the_dropdown_is_capped(self):
        from core.admin_views import FEED_LIMIT

        for index in range(FEED_LIMIT + 5):
            self.make(f"Booking {index}")
        self.client.force_login(self.owner)

        _, payload = self.feed()
        self.assertEqual(len(payload["items"]), FEED_LIMIT)
        # The badge still counts everything, not just what fits on screen.
        self.assertEqual(payload["unread"], FEED_LIMIT + 5)
