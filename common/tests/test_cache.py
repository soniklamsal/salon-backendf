"""The content cache, and the invalidation that keeps it honest.

Caching the published endpoints is only safe if an admin edit is visible on the
very next request. A stale site after saving is worse than a slow one -- staff
would reasonably conclude the admin is broken -- so the invalidation is what
these mostly cover.
"""

from unittest.mock import patch

from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from common.cache import bump_content_version, cached_payload

from bookings.models import Barber
from core.models import NavLink, SiteSettings
from sections.models import AboutColumn, AboutColumnItem, AboutSection


class ContentCacheTests(TestCase):
    def setUp(self):
        # LocMem is per-process and outlives a single test, so each starts
        # from empty rather than inheriting the previous test's warm keys.
        cache.clear()

    def test_the_second_request_does_not_query_again(self):
        self.client.get(reverse("homepage"))
        with self.assertNumQueries(0):
            response = self.client.get(reverse("homepage"))
        self.assertEqual(response.status_code, 200)

    def test_the_cached_payload_is_the_same_answer(self):
        first = self.client.get(reverse("homepage")).json()
        second = self.client.get(reverse("homepage")).json()
        self.assertEqual(first, second)

    def test_saving_content_shows_up_on_the_very_next_request(self):
        self.client.get(reverse("homepage"))

        settings_row = SiteSettings.load()
        settings_row.brand_name = "CHANGED IN ADMIN"
        settings_row.save()

        payload = self.client.get(reverse("homepage")).json()
        self.assertEqual(payload["site"]["brandName"], "CHANGED IN ADMIN")

    def test_adding_a_row_shows_up_on_the_very_next_request(self):
        self.client.get(reverse("homepage"))
        NavLink.objects.create(label="Brand New", href="/new")
        payload = self.client.get(reverse("homepage")).json()
        self.assertIn("Brand New", [link["label"] for link in payload["navLinks"]])

    def test_deleting_a_row_shows_up_on_the_very_next_request(self):
        link = NavLink.objects.create(label="Temporary", href="/tmp")
        self.client.get(reverse("homepage"))
        link.delete()
        payload = self.client.get(reverse("homepage")).json()
        self.assertNotIn("Temporary", [link["label"] for link in payload["navLinks"]])

    def test_a_bullet_edit_reaches_the_about_page(self):
        """The nested case: the bullet is two models below the cached payload."""
        section = AboutSection.objects.first() or AboutSection.objects.create()
        column = AboutColumn.objects.create(
            section=section, heading="Our Facilities", body="", order=90
        )
        item = AboutColumnItem.objects.create(column=column, text="Before", order=0)
        self.client.get(reverse("about"))

        item.text = "After"
        item.save()

        payload = self.client.get(reverse("about")).json()
        texts = [i["text"] for c in payload["columns"] for i in c["items"]]
        self.assertIn("After", texts)
        self.assertNotIn("Before", texts)

    def test_a_barber_edit_reaches_the_booking_form(self):
        """`bookings` is only partly content, so this arm is opted in by name."""
        barber = Barber.objects.create(name="Old Name")
        self.client.get(reverse("booking-config"))

        barber.name = "New Name"
        barber.save()

        payload = self.client.get(reverse("booking-config")).json()
        self.assertIn("New Name", [b["name"] for b in payload["barbers"]])


@override_settings(ALLOWED_HOSTS=["localhost", "salon.example", "testserver"])
class CacheKeyTests(TestCase):
    """Asserted on `cached_payload` directly.

    Going through a view could not tell a real cache hit from two builds that
    happened to agree -- on an empty database every host produces the same
    payload. Counting builds is the only unambiguous evidence.
    """

    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()
        self.builds = 0

    def build(self):
        self.builds += 1
        return {"built": self.builds}

    def test_the_same_host_is_built_once(self):
        request = self.factory.get("/", HTTP_HOST="localhost")
        cached_payload("thing", request, self.build)
        cached_payload("thing", request, self.build)
        self.assertEqual(self.builds, 1)

    def test_a_different_host_is_built_again(self):
        """Absolute image URLs make one host's payload wrong for another."""
        cached_payload("thing", self.factory.get("/", HTTP_HOST="localhost"), self.build)
        cached_payload("thing", self.factory.get("/", HTTP_HOST="salon.example"), self.build)
        self.assertEqual(self.builds, 2)

    def test_a_different_name_is_built_again(self):
        request = self.factory.get("/", HTTP_HOST="localhost")
        cached_payload("one", request, self.build)
        cached_payload("two", request, self.build)
        self.assertEqual(self.builds, 2)

    def test_a_bump_strands_the_old_entry(self):
        request = self.factory.get("/", HTTP_HOST="localhost")
        cached_payload("thing", request, self.build)
        bump_content_version()
        cached_payload("thing", request, self.build)
        self.assertEqual(self.builds, 2)

    def test_a_broken_cache_still_serves_the_page(self):
        """The cache is an optimisation; losing it must not lose the response."""
        request = self.factory.get("/", HTTP_HOST="localhost")
        with patch("common.cache.cache.get", side_effect=RuntimeError("redis down")):
            payload = cached_payload("thing", request, self.build)
        self.assertEqual(payload, {"built": 1})