"""The read side: the aggregate payloads the frontend actually fetches.

The point of most of these is that an *empty* database still serves a complete
page. `SingletonModel.load()` falls back to an unsaved instance carrying the
field defaults, and those defaults are the copy the site shipped with — so a
fresh deploy that has not been seeded is not a broken page.
"""

from django.test import TestCase
from django.urls import reverse

from bookings.models import Barber
from core.models import NavLink, SocialLink
from sections.models import ClassCard, ClassesSection, GalleryImage, GallerySection, Service


class HomepageTests(TestCase):
    def test_empty_database_still_serves_every_band(self):
        response = self.client.get(reverse("homepage"))
        self.assertEqual(response.status_code, 200)
        for band in ("site", "hero", "whoWeAre", "gallery", "classes", "footer"):
            self.assertIn(band, response.json())

    def test_defaults_are_the_shipped_copy(self):
        payload = self.client.get(reverse("homepage")).json()
        self.assertEqual(payload["site"]["brandName"], "SALON")

    def test_keys_are_camel_case(self):
        payload = self.client.get(reverse("homepage")).json()
        self.assertIn("metaTitle", payload["site"])
        self.assertNotIn("meta_title", payload["site"])

    def test_unpublished_links_are_omitted(self):
        NavLink.objects.create(label="Shown", href="/a", is_published=True)
        NavLink.objects.create(label="Hidden", href="/b", is_published=False)
        payload = self.client.get(reverse("homepage")).json()
        labels = [link["label"] for link in payload["navLinks"]]
        self.assertEqual(labels, ["Shown"])

    def test_header_and_footer_link_lists_are_separate(self):
        NavLink.objects.create(label="Header only", href="/a", show_in_footer=False)
        payload = self.client.get(reverse("homepage")).json()
        self.assertEqual(len(payload["navLinks"]), 1)
        self.assertEqual(len(payload["footerLinks"]), 0)

    def test_social_link_falls_back_to_a_generated_label(self):
        SocialLink.objects.create(platform="instagram", url="https://x.test")
        payload = self.client.get(reverse("homepage")).json()
        self.assertEqual(payload["socialLinks"][0]["label"], "Salon on Instagram")

    def test_query_count_does_not_grow_with_content(self):
        """The N+1 test, written as a comparison rather than a magic number.

        Asserting an exact count just records whatever the code does today and
        fails on every unrelated change. What actually matters is that adding
        rows does not add queries — that is the difference between one query
        for the gallery and one per image.
        """
        with self.assertNumQueries(
            self.count_queries_for_homepage()
        ):
            self.client.get(reverse("homepage"))

    def count_queries_for_homepage(self):
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        gallery = GallerySection.objects.create()
        for i in range(20):
            GalleryImage.objects.create(section=gallery, alt=f"img {i}")
        NavLink.objects.bulk_create(
            NavLink(label=f"L{i}", href=f"/{i}") for i in range(20)
        )
        SocialLink.objects.bulk_create(
            SocialLink(platform="instagram", url=f"https://x{i}.test") for i in range(20)
        )

        with CaptureQueriesContext(connection) as ctx:
            self.client.get(reverse("homepage"))
        loaded = len(ctx)

        GalleryImage.objects.all().delete()
        NavLink.objects.all().delete()
        SocialLink.objects.all().delete()
        return loaded


class BookingConfigTests(TestCase):
    def test_lists_only_published_services_and_barbers(self):
        Service.objects.create(label="Shown", is_published=True)
        Service.objects.create(label="Hidden", is_published=False)
        Barber.objects.create(name="Shown", is_published=True)
        Barber.objects.create(name="Hidden", is_published=False)

        payload = self.client.get(reverse("booking-config")).json()
        self.assertEqual([s["label"] for s in payload["services"]], ["Shown"])
        self.assertEqual([b["name"] for b in payload["barbers"]], ["Shown"])

    def test_unavailable_barbers_are_still_listed_with_a_badge(self):
        """Hiding someone who is only on holiday reads as "they have left"."""
        Barber.objects.create(name="Here", is_published=True)
        Barber.objects.create(
            name="Away",
            is_published=True,
            is_available=False,
            unavailable_note="Back on 20 August",
        )

        payload = self.client.get(reverse("booking-config")).json()
        by_name = {b["name"]: b for b in payload["barbers"]}

        self.assertEqual(sorted(by_name), ["Away", "Here"])
        self.assertTrue(by_name["Here"]["isAvailable"])
        self.assertEqual(by_name["Here"]["availabilityLabel"], "Available")
        self.assertFalse(by_name["Away"]["isAvailable"])
        self.assertEqual(by_name["Away"]["availabilityLabel"], "Back on 20 August")

    def test_an_unavailable_barber_without_a_note_gets_a_plain_badge(self):
        Barber.objects.create(name="Away", is_published=True, is_available=False)
        payload = self.client.get(reverse("booking-config")).json()
        self.assertEqual(payload["barbers"][0]["availabilityLabel"], "Not available")

    def test_unpublished_barbers_are_still_hidden_entirely(self):
        """Availability and publication are different switches."""
        Barber.objects.create(name="Gone", is_published=False)
        payload = self.client.get(reverse("booking-config")).json()
        self.assertEqual(payload["barbers"], [])

    def test_esewa_block_is_present_without_an_uploaded_qr(self):
        """The payment step has to render before anyone uploads a QR."""
        payload = self.client.get(reverse("booking-config")).json()
        self.assertEqual(payload["esewa"]["qr"], "")
        self.assertEqual(payload["esewa"]["depositPercent"], 100)


class ReadOnlyEndpointTests(TestCase):
    def test_list_endpoints_are_paginated(self):
        Service.objects.create(label="One", is_published=True)
        payload = self.client.get(reverse("service-list")).json()
        self.assertIn("results", payload)
        self.assertEqual(payload["count"], 1)

    def test_unpublished_rows_are_not_retrievable_by_id(self):
        hidden = Service.objects.create(label="Hidden", is_published=False)
        response = self.client.get(reverse("service-detail", args=[hidden.pk]))
        self.assertEqual(response.status_code, 404)

    def test_writes_are_refused_on_read_only_resources(self):
        for method in (self.client.post, self.client.put, self.client.delete):
            self.assertIn(method(reverse("service-list")).status_code, (403, 405))

    def test_classes_are_addressed_by_slug(self):
        ClassCard.objects.create(
            slug="fade",
            name="Fade",
            is_published=True,
            section=ClassesSection.objects.create(),
        )
        response = self.client.get(reverse("classcard-detail", args=["fade"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Fade")


class RootAndHealthTests(TestCase):
    def test_api_root_lists_every_named_route(self):
        payload = self.client.get(reverse("api-root")).json()
        # The hand-written version of this had already lost my-bookings.
        for key in ("homepage", "booking-config", "my-bookings", "health"):
            self.assertIn(key, payload)

    def test_health_reports_ok_when_the_database_answers(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_health_says_nothing_beyond_status(self):
        """It is unauthenticated, so it must not describe the deployment."""
        self.assertEqual(list(self.client.get(reverse("health")).json()), ["status"])
