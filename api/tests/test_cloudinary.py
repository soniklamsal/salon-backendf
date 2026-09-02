"""The Cloudinary code paths, against a mocked client.

Mocked rather than live: the real account is the salon's, on a metered plan,
and a test suite that uploads to it would cost money, need network, and leave
junk behind. `common.testing.SalonTestRunner` pins the whole run to local
storage, so these tests switch Cloudinary back on explicitly and assert on what
would be *asked* of Cloudinary rather than on what it answers.
"""

import io
import shutil
import tempfile
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from bookings.models import Appointment
from common.storage import private_media_storage, screenshot_token, signed_url

CLOUDINARY_ON = override_settings(
    USE_CLOUDINARY=True,
    CLOUDINARY_STORAGE={
        "CLOUD_NAME": "testcloud",
        "API_KEY": "123",
        "API_SECRET": "secret",
    },
)


def png():
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


class SignedUrlTests(TestCase):
    def test_returns_nothing_when_cloudinary_is_off(self):
        """Local storage has no signed URL; the view streams instead."""
        self.assertEqual(signed_url("payments/x.png"), "")

    def test_returns_nothing_for_an_empty_name(self):
        with CLOUDINARY_ON:
            self.assertEqual(signed_url(""), "")

    @CLOUDINARY_ON
    def test_builds_an_authenticated_signed_url(self):
        url = signed_url("media/payments/2026/08/proof.png")
        self.assertIn("res.cloudinary.com/testcloud", url)
        # `authenticated` is what makes Cloudinary refuse an unsigned request;
        # `s--` is the signature segment that lets this one through.
        self.assertIn("/authenticated/", url)
        self.assertIn("/s--", url)

    @CLOUDINARY_ON
    def test_the_signature_depends_on_the_file(self):
        first = signed_url("media/payments/a.png")
        second = signed_url("media/payments/b.png")
        self.assertNotEqual(
            first.split("/s--")[1][:10], second.split("/s--")[1][:10]
        )


@CLOUDINARY_ON
class PrivateCloudinaryStorageTests(TestCase):
    def test_the_backend_switches_when_cloudinary_is_configured(self):
        self.assertEqual(
            private_media_storage.__class__.__name__, "PrivateCloudinaryStorage"
        )

    def test_uploads_are_marked_authenticated(self):
        """The whole protection: a public-type upload would be world-readable."""
        with patch("cloudinary.uploader.upload") as upload:
            upload.return_value = {"public_id": "media/payments/proof"}
            private_media_storage.save("payments/proof.png", png())

        options = upload.call_args.kwargs
        self.assertEqual(options["type"], "authenticated")

    def test_deletes_target_the_authenticated_asset(self):
        """Deleting the default type would silently leave the file in place."""
        with patch("cloudinary.uploader.destroy") as destroy:
            destroy.return_value = {"result": "ok"}
            private_media_storage.delete("media/payments/proof")

        self.assertEqual(destroy.call_args.kwargs["type"], "authenticated")

    def test_still_refuses_to_produce_a_plain_url(self):
        with self.assertRaises(NotImplementedError):
            private_media_storage.url("media/payments/proof")


class ScreenshotViewOnCloudinaryTests(TestCase):
    """The view hands over a signed URL instead of streaming bytes."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        from django.core.files.uploadedfile import SimpleUploadedFile

        # Created while storage is local, so no upload is attempted.
        with override_settings(PRIVATE_MEDIA_ROOT=self.tmp):
            self.booking = Appointment.objects.create(
                name="Asha",
                google_user_id="user_owner",
                payment_screenshot=SimpleUploadedFile(
                    "proof.png", png().read(), content_type="image/png"
                ),
            )

        self.url = reverse(
            "payment-screenshot", kwargs={"reference": self.booking.reference}
        )
        self.token = screenshot_token(self.booking.reference)

    @CLOUDINARY_ON
    def test_authorised_request_redirects_to_a_signed_url(self):
        response = self.client.get(f"{self.url}?token={self.token}")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/authenticated/", response["Location"])
        self.assertIn("/s--", response["Location"])

    @CLOUDINARY_ON
    def test_the_redirect_is_not_issued_without_authorisation(self):
        """A 302 to a signed URL would defeat the point of the check."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)

    @CLOUDINARY_ON
    def test_a_token_for_another_booking_gets_no_redirect(self):
        other = Appointment.objects.create(name="Bim", google_user_id="user_other")
        response = self.client.get(f"{self.url}?token={screenshot_token(other.reference)}")
        self.assertEqual(response.status_code, 404)

    def test_the_same_request_streams_when_cloudinary_is_off(self):
        with override_settings(PRIVATE_MEDIA_ROOT=self.tmp):
            response = self.client.get(f"{self.url}?token={self.token}")
        self.assertEqual(response.status_code, 200)


class StorageSwitchingTests(TestCase):
    def test_turning_cloudinary_on_and_off_re_resolves_the_backend(self):
        """A LazyObject caches its answer; without a reset the override is a lie."""
        self.assertEqual(
            private_media_storage.__class__.__name__, "PrivateFileSystemStorage"
        )
        with CLOUDINARY_ON:
            self.assertEqual(
                private_media_storage.__class__.__name__, "PrivateCloudinaryStorage"
            )
        self.assertEqual(
            private_media_storage.__class__.__name__, "PrivateFileSystemStorage"
        )
