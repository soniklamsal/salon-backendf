"""The public booking endpoint.

Everything here assumes the caller has bypassed the Next.js frontend entirely,
because that is the only assumption worth testing: the form's own validation is
a convenience, and the endpoint is open to the internet.
"""

import io
import shutil
import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from bookings.models import Appointment, Barber
from sections.models import Service


def png_upload(size=(20, 20), name="proof.png"):
    from django.core.files.uploadedfile import SimpleUploadedFile

    buffer = io.BytesIO()
    Image.new("RGB", size, "blue").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class BookingEndpointTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._tmp = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.overridden = override_settings(PRIVATE_MEDIA_ROOT=self._tmp)
        self.overridden.enable()
        self.addCleanup(self.overridden.disable)

        # DRF counts throttled requests in the default cache, which is process
        # -wide and outlives a test. Without this, whichever tests run after
        # the first ten all get a 429 and the failure looks like a bug in the
        # thing being tested.
        from django.core.cache import cache

        cache.clear()

        self.url = reverse("appointment-create")
        self.service = Service.objects.create(label="Haircut", is_published=True)
        self.barber = Barber.objects.create(name="Ram", is_published=True)
        self.tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()

    def payload(self, **overrides):
        # Everything the public form actually posts. No email: the form shows
        # it read-only from the account, and the API takes it from the verified
        # token rather than the body.
        data = {
            "name": "Asha",
            "address": "12 Thamel Marg",
            "phone": "9801234567",
            "notes": "A trim, not too short",
            "service": self.service.pk,
            "barber": self.barber.pk,
            "paymentScreenshot": png_upload(),
        }
        data.update(overrides)
        return data

    def test_valid_booking_is_accepted_and_returns_its_reference(self):
        response = self.client.post(self.url, self.payload())
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["reference"].startswith("SLN-"))

    def test_booking_defaults_to_pending(self):
        self.client.post(self.url, self.payload())
        self.assertEqual(Appointment.objects.get().status, Appointment.Status.PENDING)

    def test_status_cannot_be_set_by_the_caller(self):
        """Otherwise a booking approves itself without anyone checking payment."""
        self.client.post(self.url, self.payload(status="approved"))
        self.assertEqual(Appointment.objects.get().status, Appointment.Status.PENDING)

    def test_order_id_cannot_be_set_by_the_caller(self):
        self.client.post(self.url, self.payload(order_id="ORD-2026-0001"))
        self.assertEqual(Appointment.objects.get().order_id, None)

    def test_google_user_id_cannot_be_forged_through_the_body(self):
        """It comes from the verified token or nowhere."""
        self.client.post(self.url, self.payload(google_user_id="user_victim"))
        self.assertEqual(Appointment.objects.get().google_user_id, "")

    def test_verified_token_stamps_the_booking(self):
        with patch(
            "api.views.user_from_request",
            return_value={"sub": "user_abc", "email": "a@b.com"},
        ):
            self.client.post(self.url, self.payload(), HTTP_AUTHORIZATION="Bearer x")
        booking = Appointment.objects.get()
        self.assertEqual(booking.google_user_id, "user_abc")
        self.assertEqual(booking.email, "a@b.com")

    def test_screenshot_is_required(self):
        payload = self.payload()
        payload.pop("paymentScreenshot")
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("paymentScreenshot", response.json()["errors"])

    def test_unpublished_service_is_rejected(self):
        retired = Service.objects.create(label="Gone", is_published=False)
        response = self.client.post(self.url, self.payload(service=retired.pk))
        self.assertEqual(response.status_code, 400)

    def test_unpublished_barber_is_rejected(self):
        left = Barber.objects.create(name="Left", is_published=False)
        response = self.client.post(self.url, self.payload(barber=left.pk))
        self.assertEqual(response.status_code, 400)
        self.assertIn("barber", response.json()["errors"])

    def test_an_unavailable_barber_is_rejected(self):
        """The card is disabled in the browser, but the endpoint is public."""
        away = Barber.objects.create(
            name="Bina", is_published=True, is_available=False
        )
        response = self.client.post(self.url, self.payload(barber=away.pk))
        self.assertEqual(response.status_code, 400)
        self.assertIn("barber", response.json()["errors"])

    def test_the_rejection_names_the_barber(self):
        away = Barber.objects.create(
            name="Bina", is_published=True, is_available=False
        )
        response = self.client.post(self.url, self.payload(barber=away.pk))
        self.assertIn("Bina", response.json()["errors"]["barber"][0])

    def test_an_available_barber_is_accepted(self):
        response = self.client.post(self.url, self.payload())
        self.assertEqual(response.status_code, 201)

    def test_a_requested_date_is_ignored(self):
        """The customer does not choose when they come in; the salon does.

        Accepted rather than rejected, because a stray field should not cost
        somebody their booking — but it must not reach the record.
        """
        response = self.client.post(
            self.url,
            self.payload(
                preferredDate=self.tomorrow,
                preferredTime="14:30",
                scheduledDate=self.tomorrow,
                scheduled_date=self.tomorrow,
                scheduled_time="14:30",
            ),
        )
        self.assertEqual(response.status_code, 201)

        booking = Appointment.objects.get()
        self.assertIsNone(booking.preferred_date)
        self.assertIsNone(booking.preferred_time)
        self.assertIsNone(booking.scheduled_date)
        self.assertIsNone(booking.scheduled_time)

    def test_a_past_date_no_longer_fails_the_booking(self):
        """There is no date field left to be wrong about."""
        yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
        response = self.client.post(self.url, self.payload(preferredDate=yesterday))
        self.assertEqual(response.status_code, 201)

    def test_a_pasted_sentence_is_not_a_phone_number(self):
        response = self.client.post(self.url, self.payload(phone="call me later"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("phone", response.json()["errors"])

    def test_too_few_digits_is_rejected(self):
        response = self.client.post(self.url, self.payload(phone="12345"))
        self.assertEqual(response.status_code, 400)

    def test_real_phone_formats_are_accepted(self):
        """A validator that rejects a real customer costs a booking."""
        for number in ("9801234567", "+977 980-123-4567", "(01) 4567890", "01-4567890"):
            with self.subTest(number=number):
                from django.core.cache import cache

                cache.clear()
                Appointment.objects.all().delete()
                response = self.client.post(self.url, self.payload(phone=number))
                self.assertEqual(response.status_code, 201, number)

    def test_name_address_phone_and_description_are_all_required(self):
        for field in ("name", "address", "phone", "notes"):
            with self.subTest(field=field):
                from django.core.cache import cache

                cache.clear()
                payload = self.payload()
                payload.pop(field)
                response = self.client.post(self.url, payload)
                self.assertEqual(response.status_code, 400, field)
                self.assertIn(field, response.json()["errors"])

    def test_whitespace_does_not_count_as_filled_in(self):
        """`allow_blank=False` rejects "" but happily accepts "   "."""
        for field in ("name", "address", "phone", "notes"):
            with self.subTest(field=field):
                from django.core.cache import cache

                cache.clear()
                response = self.client.post(self.url, self.payload(**{field: "   "}))
                self.assertEqual(response.status_code, 400, field)

    def test_stored_values_are_trimmed(self):
        self.client.post(
            self.url,
            self.payload(name="  Asha  ", address="  12 Thamel  ", notes="  A trim  "),
        )
        booking = Appointment.objects.get()
        self.assertEqual(booking.name, "Asha")
        self.assertEqual(booking.address, "12 Thamel")
        self.assertEqual(booking.notes, "A trim")

    def test_email_comes_from_the_account_not_the_form(self):
        """The form shows it read-only; the token is the only source."""
        with patch(
            "api.views.user_from_request",
            return_value={"sub": "user_abc", "email": "signup@example.test"},
        ):
            response = self.client.post(
                self.url, self.payload(), HTTP_AUTHORIZATION="Bearer x"
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Appointment.objects.get().email, "signup@example.test")

    def test_a_posted_email_is_ignored(self):
        """The field is read-only, so a caller editing the request gets nowhere."""
        with patch(
            "api.views.user_from_request",
            return_value={"sub": "user_abc", "email": "signup@example.test"},
        ):
            self.client.post(
                self.url,
                self.payload(email="attacker@example.com"),
                HTTP_AUTHORIZATION="Bearer x",
            )

        self.assertEqual(Appointment.objects.get().email, "signup@example.test")

    def test_a_posted_email_cannot_fill_the_gap_for_an_anonymous_booking(self):
        """No token means no email, whatever the body says."""
        self.client.post(self.url, self.payload(email="attacker@example.com"))
        self.assertEqual(Appointment.objects.get().email, "")

    def test_a_malformed_posted_email_does_not_fail_the_booking(self):
        """Nothing the customer can type reaches the field, so nothing they
        can type should be able to reject a paid booking either."""
        response = self.client.post(self.url, self.payload(email="not-an-email"))
        self.assertEqual(response.status_code, 201)

    def test_an_account_with_no_email_still_books(self):
        with patch("api.views.user_from_request", return_value={"sub": "user_abc"}):
            response = self.client.post(
                self.url, self.payload(), HTTP_AUTHORIZATION="Bearer x"
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Appointment.objects.get().email, "")

    def test_a_pasted_sentence_is_not_a_phone_number(self):
        response = self.client.post(self.url, self.payload(phone="call me later"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("phone", response.json()["errors"])

    def test_too_few_digits_is_rejected(self):
        response = self.client.post(self.url, self.payload(phone="12345"))
        self.assertEqual(response.status_code, 400)

    def test_real_phone_formats_are_accepted(self):
        """A validator that rejects a real customer costs a booking."""
        for number in ("9801234567", "+977 980-123-4567", "(01) 4567890", "01-4567890"):
            with self.subTest(number=number):
                from django.core.cache import cache

                cache.clear()
                Appointment.objects.all().delete()
                response = self.client.post(self.url, self.payload(phone=number))
                self.assertEqual(response.status_code, 201, number)

    def test_name_address_phone_and_description_are_all_required(self):
        for field in ("name", "address", "phone", "notes"):
            with self.subTest(field=field):
                from django.core.cache import cache

                cache.clear()
                payload = self.payload()
                payload.pop(field)
                response = self.client.post(self.url, payload)
                self.assertEqual(response.status_code, 400, field)
                self.assertIn(field, response.json()["errors"])

    def test_whitespace_does_not_count_as_filled_in(self):
        """`allow_blank=False` rejects "" but happily accepts "   "."""
        for field in ("name", "address", "phone", "notes"):
            with self.subTest(field=field):
                from django.core.cache import cache

                cache.clear()
                response = self.client.post(self.url, self.payload(**{field: "   "}))
                self.assertEqual(response.status_code, 400, field)

    def test_stored_values_are_trimmed(self):
        self.client.post(
            self.url,
            self.payload(name="  Asha  ", address="  12 Thamel  ", notes="  A trim  "),
        )
        booking = Appointment.objects.get()
        self.assertEqual(booking.name, "Asha")
        self.assertEqual(booking.address, "12 Thamel")
        self.assertEqual(booking.notes, "A trim")

    @override_settings(MAX_UPLOAD_BYTES=1024)
    def test_oversized_upload_is_rejected(self):
        response = self.client.post(self.url, self.payload(paymentScreenshot=png_upload((900, 900))))
        self.assertEqual(response.status_code, 400)

    @override_settings(MAX_UPLOAD_PIXELS=100)
    def test_decompression_bomb_dimensions_are_rejected(self):
        response = self.client.post(self.url, self.payload(paymentScreenshot=png_upload((400, 400))))
        self.assertEqual(response.status_code, 400)

    def test_non_image_upload_is_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        bad = SimpleUploadedFile("x.png", b"not an image", content_type="image/png")
        response = self.client.post(self.url, self.payload(paymentScreenshot=bad))
        self.assertEqual(response.status_code, 400)

    def test_two_bookings_from_a_new_account_do_not_collide(self):
        """`_ensure_account_visible` used to race with itself here."""
        with patch("api.views.user_from_request", return_value={"sub": "user_new"}):
            first = self.client.post(self.url, self.payload(), HTTP_AUTHORIZATION="Bearer x")
            second = self.client.post(self.url, self.payload(), HTTP_AUTHORIZATION="Bearer x")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)

    def test_account_mirroring_failure_does_not_lose_the_booking(self):
        """A paid customer must not be rejected because a sidebar row failed.

        Mirroring the Google account into Django's Users list is a convenience
        for the admin. When it fails the booking must still be recorded — the
        customer has already paid.
        """
        from django.db import IntegrityError

        with patch("api.views.user_from_request", return_value={"sub": "user_x"}):
            with patch(
                "bookings.models.GoogleProfile.objects.get_or_create",
                side_effect=IntegrityError("lost the race"),
            ):
                response = self.client.post(
                    self.url, self.payload(), HTTP_AUTHORIZATION="Bearer x"
                )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Appointment.objects.get().google_user_id, "user_x")

    def test_throttle_limits_repeated_submissions(self):
        """The endpoint is anonymous and takes a file, so it has to have a cap."""
        payloads = [self.payload() for _ in range(11)]
        statuses = [self.client.post(self.url, p).status_code for p in payloads]
        self.assertIn(429, statuses)


class MyBookingsTests(TestCase):
    def setUp(self):
        self.url = reverse("my-bookings")
        self.mine = Appointment.objects.create(name="Mine", google_user_id="user_me")
        self.theirs = Appointment.objects.create(name="Theirs", google_user_id="user_them")

    def test_anonymous_gets_an_empty_list_not_an_error(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["bookings"], [])

    def test_only_the_callers_own_bookings_are_returned(self):
        with patch("api.views.user_from_request", return_value={"sub": "user_me"}):
            response = self.client.get(self.url, HTTP_AUTHORIZATION="Bearer x")
        names = [b["name"] for b in response.json()["bookings"]]
        self.assertEqual(names, ["Mine"])

    def test_a_pending_booking_carries_no_time(self):
        """Sending one would let the page promise a slot nobody has set."""
        with patch("api.views.user_from_request", return_value={"sub": "user_me"}):
            payload = self.client.get(
                reverse("my-bookings"), HTTP_AUTHORIZATION="Bearer x"
            ).json()

        booking = payload["bookings"][0]
        self.assertIsNone(booking["scheduledDate"])
        self.assertIsNone(booking["scheduledTime"])

    def test_the_salons_time_reaches_the_customer_after_approval(self):
        """The whole point: staff type it in the admin, the customer sees it."""
        from datetime import date, time

        self.mine.scheduled_date = date(2026, 9, 1)
        self.mine.scheduled_time = time(11, 0)
        self.mine.save()
        self.mine.approve()

        with patch("api.views.user_from_request", return_value={"sub": "user_me"}):
            payload = self.client.get(
                reverse("my-bookings"), HTTP_AUTHORIZATION="Bearer x"
            ).json()

        booking = payload["bookings"][0]
        self.assertEqual(booking["scheduledDate"], "2026-09-01")
        self.assertEqual(booking["scheduledTime"], "11:00:00")

    def test_changing_the_time_after_approval_reaches_the_customer(self):
        """Staff move a booking; the status page must follow, not freeze."""
        from datetime import date, time

        self.mine.scheduled_date = date(2026, 9, 1)
        self.mine.scheduled_time = time(11, 0)
        self.mine.save()
        self.mine.approve()

        self.mine.scheduled_time = time(16, 30)
        self.mine.save()

        with patch("api.views.user_from_request", return_value={"sub": "user_me"}):
            payload = self.client.get(
                reverse("my-bookings"), HTTP_AUTHORIZATION="Bearer x"
            ).json()

        self.assertEqual(payload["bookings"][0]["scheduledTime"], "16:30:00")

    def test_the_retired_request_fields_are_not_sent(self):
        """They only exist for old rows; exposing them invites the frontend to
        show two competing times again."""
        with patch("api.views.user_from_request", return_value={"sub": "user_me"}):
            payload = self.client.get(
                reverse("my-bookings"), HTTP_AUTHORIZATION="Bearer x"
            ).json()

        booking = payload["bookings"][0]
        self.assertNotIn("preferredDate", booking)
        self.assertNotIn("preferredTime", booking)
        self.assertNotIn("isRescheduled", booking)

    def test_the_list_is_not_filterable_by_a_query_parameter(self):
        """There is no caller-supplied id to tamper with, and adding one fails."""
        with patch("api.views.user_from_request", return_value={"sub": "user_me"}):
            response = self.client.get(
                self.url + "?google_user_id=user_them", HTTP_AUTHORIZATION="Bearer x"
            )
        names = [b["name"] for b in response.json()["bookings"]]
        self.assertEqual(names, ["Mine"])
