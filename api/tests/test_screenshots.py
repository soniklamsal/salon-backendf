"""Access control on payment screenshots.

These are financial records — a customer's name against an eSewa transfer — and
before the private-storage change they sat in MEDIA_ROOT, readable by anyone
who could guess or was handed the path. This is the test that the door is now
locked and that the right people still get through it.
"""

import io
import shutil
import tempfile
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from bookings.models import Appointment
from common.storage import screenshot_token


def _png(size=(20, 20)) -> io.BytesIO:
    buffer = io.BytesIO()
    Image.new("RGB", size, "red").save(buffer, format="PNG")
    buffer.seek(0)
    buffer.name = "proof.png"
    return buffer


class ScreenshotAccessTests(TestCase):
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

        from django.core.files.uploadedfile import SimpleUploadedFile

        self.booking = Appointment.objects.create(
            name="Asha",
            google_user_id="user_owner",
            payment_screenshot=SimpleUploadedFile(
                "proof.png", _png().read(), content_type="image/png"
            ),
        )
        self.url = reverse(
            "payment-screenshot", kwargs={"reference": self.booking.reference}
        )

    def test_anonymous_request_is_refused(self):
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_owner_with_verified_token_gets_the_file(self):
        with patch(
            "api.views.user_from_request", return_value={"sub": "user_owner"}
        ):
            response = self.client.get(self.url, HTTP_AUTHORIZATION="Bearer x")
        self.assertEqual(response.status_code, 200)

    def test_a_different_signed_in_customer_is_refused(self):
        """The reference is not the credential. Knowing it is not enough."""
        with patch(
            "api.views.user_from_request", return_value={"sub": "user_someone_else"}
        ):
            response = self.client.get(self.url, HTTP_AUTHORIZATION="Bearer x")
        self.assertEqual(response.status_code, 404)

    def test_refusal_is_indistinguishable_from_a_missing_booking(self):
        """Otherwise the response confirms which references are real."""
        with patch(
            "api.views.user_from_request", return_value={"sub": "user_someone_else"}
        ):
            denied = self.client.get(self.url, HTTP_AUTHORIZATION="Bearer x")
        absent = self.client.get(
            reverse("payment-screenshot", kwargs={"reference": "SLN-NOPE99"})
        )
        self.assertEqual(denied.status_code, absent.status_code)
        self.assertEqual(denied.json(), absent.json())

    def test_staff_session_is_allowed(self):
        User.objects.create_user("staff", password="x" * 20, is_staff=True)
        self.client.login(username="staff", password="x" * 20)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_non_staff_django_user_is_refused(self):
        User.objects.create_user("plain", password="x" * 20)
        self.client.login(username="plain", password="x" * 20)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_booking_without_a_screenshot_is_404(self):
        empty = Appointment.objects.create(name="No proof", google_user_id="user_owner")
        url = reverse("payment-screenshot", kwargs={"reference": empty.reference})
        with patch("api.views.user_from_request", return_value={"sub": "user_owner"}):
            response = self.client.get(url, HTTP_AUTHORIZATION="Bearer x")
        self.assertEqual(response.status_code, 404)

    def test_file_is_not_written_into_the_public_media_folder(self):
        """The whole point: nothing lands where the web server can serve it."""
        from pathlib import Path

        from django.conf import settings

        public_copy = Path(settings.MEDIA_ROOT) / self.booking.payment_screenshot.name
        self.assertFalse(public_copy.exists())

    def test_private_storage_refuses_to_produce_a_public_url(self):
        with self.assertRaises(NotImplementedError):
            self.booking.payment_screenshot.url

    def test_uploads_land_under_the_configured_private_root(self):
        """The storage must read PRIVATE_MEDIA_ROOT at access time.

        It used to capture the path when the storage object was built, which
        made the setting effectively immutable — every test wrote its uploads
        into the real project folder while appearing to use a temp directory.
        """
        from pathlib import Path

        written = Path(self._tmp) / self.booking.payment_screenshot.name
        self.assertTrue(written.exists(), f"not written under {self._tmp}")

    def test_changing_the_setting_moves_where_files_are_written(self):
        from pathlib import Path

        from django.core.files.uploadedfile import SimpleUploadedFile

        elsewhere = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, elsewhere, ignore_errors=True)

        with override_settings(PRIVATE_MEDIA_ROOT=elsewhere):
            booking = Appointment.objects.create(
                name="Later",
                payment_screenshot=SimpleUploadedFile(
                    "later.png", _png().read(), content_type="image/png"
                ),
            )

        self.assertTrue((Path(elsewhere) / booking.payment_screenshot.name).exists())


class ScreenshotTokenTests(TestCase):
    """The signed `?token=` path, which is what makes the `<img>` load."""

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

        from django.core.files.uploadedfile import SimpleUploadedFile

        self.booking = Appointment.objects.create(
            name="Asha",
            google_user_id="user_owner",
            payment_screenshot=SimpleUploadedFile(
                "proof.png", _png().read(), content_type="image/png"
            ),
        )
        self.other = Appointment.objects.create(
            name="Bim",
            google_user_id="user_other",
            payment_screenshot=SimpleUploadedFile(
                "proof2.png", _png().read(), content_type="image/png"
            ),
        )

    def url_for(self, booking, token=None):
        base = reverse("payment-screenshot", kwargs={"reference": booking.reference})
        return f"{base}?token={token}" if token else base

    def test_valid_token_grants_access_without_any_header(self):
        token = screenshot_token(self.booking.reference)
        response = self.client.get(self.url_for(self.booking, token))
        self.assertEqual(response.status_code, 200)

    def test_token_for_one_booking_does_not_open_another(self):
        token = screenshot_token(self.booking.reference)
        response = self.client.get(self.url_for(self.other, token))
        self.assertEqual(response.status_code, 404)

    def test_tampered_token_is_refused(self):
        token = screenshot_token(self.booking.reference)
        response = self.client.get(self.url_for(self.booking, token[:-3] + "aaa"))
        self.assertEqual(response.status_code, 404)

    def test_expired_token_is_refused(self):
        token = screenshot_token(self.booking.reference)
        with patch("api.views.reference_from_token", return_value=""):
            response = self.client.get(self.url_for(self.booking, token))
        self.assertEqual(response.status_code, 404)

    def test_my_bookings_hands_the_owner_a_working_url(self):
        """End to end: fetch the list, then fetch the image it points at."""
        with patch("api.views.user_from_request", return_value={"sub": "user_owner"}):
            listing = self.client.get(
                reverse("my-bookings"), HTTP_AUTHORIZATION="Bearer x"
            )

        url = listing.json()["bookings"][0]["paymentScreenshot"]
        self.assertIn("token=", url)
        # No auth header this time — exactly what an <img> does.
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_anonymous_booking_is_not_matched_by_an_empty_claim(self):
        """A booking with no account must not be readable by everyone."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        orphan = Appointment.objects.create(
            name="Walk-in",
            payment_screenshot=SimpleUploadedFile(
                "p.png", _png().read(), content_type="image/png"
            ),
        )
        self.assertEqual(orphan.google_user_id, "")
        with patch("api.views.user_from_request", return_value={"sub": ""}):
            response = self.client.get(
                self.url_for(orphan), HTTP_AUTHORIZATION="Bearer x"
            )
        self.assertEqual(response.status_code, 404)
