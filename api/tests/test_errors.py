"""The error contract.

Every failure has to arrive in the same shape, because the frontend has one
piece of code that unwraps it. DRF's default is whatever the exception happened
to carry — a dict here, a list there — which pushes that decision onto the
client, per endpoint.
"""

from django.test import TestCase
from django.urls import reverse

from bookings.models import Appointment


class ErrorShapeTests(TestCase):
    def test_field_errors_arrive_under_errors_with_a_summary_detail(self):
        response = self.client.post(reverse("contact-create"), {})
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("detail", payload)
        self.assertIn("errors", payload)
        self.assertIn("name", payload["errors"])
        self.assertIsInstance(payload["errors"]["name"], list)

    def test_not_found_has_detail_and_no_errors_key(self):
        response = self.client.get(
            reverse("payment-screenshot", kwargs={"reference": "SLN-NOPE99"})
        )
        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertIn("detail", payload)
        self.assertNotIn("errors", payload)

    def test_method_not_allowed_is_normalised_too(self):
        response = self.client.delete(reverse("homepage"))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(list(response.json()), ["detail"])

    def test_detail_is_always_a_string(self):
        """Not a list, not a dict — the frontend renders it directly."""
        response = self.client.post(reverse("contact-create"), {})
        self.assertIsInstance(response.json()["detail"], str)

    def test_throttled_response_keeps_its_status_and_retry_header(self):
        """Normalising the body must not strip DRF's own headers."""
        last = None
        for _ in range(25):
            last = self.client.post(reverse("contact-create"), {})
            if last.status_code == 429:
                break
        self.assertEqual(last.status_code, 429)
        self.assertIn("Retry-After", last)
        self.assertIn("detail", last.json())


class ContactEndpointTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()

    def test_valid_message_is_stored(self):
        response = self.client.post(
            reverse("contact-create"),
            {"name": "Asha", "email": "a@b.com", "message": "Hello"},
        )
        self.assertEqual(response.status_code, 201)

    def test_email_is_required_and_validated(self):
        response = self.client.post(
            reverse("contact-create"),
            {"name": "Asha", "email": "not-an-email", "message": "Hello"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.json()["errors"])

    def test_is_handled_cannot_be_set_by_the_caller(self):
        self.client.post(
            reverse("contact-create"),
            {"name": "A", "email": "a@b.com", "message": "M", "is_handled": True},
        )
        from bookings.models import ContactMessage

        self.assertFalse(ContactMessage.objects.get().is_handled)
