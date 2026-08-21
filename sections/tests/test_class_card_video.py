"""Clips on the "Moments Captured In The Chair" cards.

A card shows a photo or a clip. The clip is set by pasting the address of a
video hosted somewhere else -- in practice a Cloudinary video URL, since that
is where this site's media already lives -- and while that address is filled
in it is what the card plays.

There is no upload here and no hard either/or rule, and both are deliberate
reversals of earlier designs:

*   Uploading meant a second storage service to configure before the field did
    anything, and the field sat dead until somebody had one.
*   Refusing to save a card carrying both a photo and a clip blocked every
    card in the database, because they all ship with a seeded `image_url`. A
    precedence rule costs nothing and blocks nobody: the clip wins while it is
    there, and the photo comes back when it is removed.

There is also no upload field and no `video_uid`. Both were removed once the
design settled on a pasted address: uploading meant a second storage service
to configure, and it left video files sitting in the backend that nobody
wanted there. This project now stores no video at all.
"""

import re

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from api.serializers import ClassCardSerializer
from sections.models import ClassCard, ClassesSection

CLOUDINARY_VIDEO = "https://res.cloudinary.com/demo/video/upload/v1/clip.mp4"


class VideoUrlTests(TestCase):
    """Pasting an address, which is the whole of how a clip gets on a card."""

    @classmethod
    def setUpTestData(cls):
        cls.section = ClassesSection.objects.create()

    def card(self, **kwargs):
        return ClassCard.objects.create(
            section=self.section,
            slug=kwargs.pop("slug", "fresh-cut"),
            name="Fresh Cut",
            href="/services",
            **kwargs,
        )

    def test_a_card_with_no_clip_has_no_video(self):
        self.assertEqual(self.card().video(), {})

    def test_a_pasted_url_is_what_the_card_plays(self):
        video = self.card(video_url=CLOUDINARY_VIDEO).video()
        self.assertEqual(video["src"], CLOUDINARY_VIDEO)

    def test_a_cloudinary_url_gets_a_poster_frame(self):
        """Cloudinary renders a still of any video it holds if the URL asks
        for a picture format, so the tile is not black while it buffers."""
        video = self.card(video_url=CLOUDINARY_VIDEO).video()
        self.assertEqual(
            video["thumbnail"],
            "https://res.cloudinary.com/demo/video/upload/v1/clip.jpg",
        )

    def test_a_cloudinary_public_id_with_no_extension_still_gets_one(self):
        video = self.card(
            video_url="https://res.cloudinary.com/demo/video/upload/f_auto/abc123"
        ).video()
        self.assertTrue(video["thumbnail"].endswith("/abc123.jpg"))

    def test_a_cloudinary_hls_url_is_passed_through_as_the_source(self):
        video = self.card(
            video_url="https://res.cloudinary.com/demo/video/upload/v1/clip.m3u8"
        ).video()
        self.assertTrue(video["src"].endswith(".m3u8"))

    def test_someone_elses_mp4_gets_no_invented_poster(self):
        """A guess would render a broken `poster`, which is worse than none."""
        video = self.card(video_url="https://example.com/clip.mp4").video()
        self.assertEqual(video["src"], "https://example.com/clip.mp4")
        self.assertEqual(video["thumbnail"], "")

    def test_a_cloudinary_image_url_is_not_mistaken_for_a_video(self):
        video = self.card(
            video_url="https://res.cloudinary.com/demo/image/upload/v1/photo.jpg"
        ).video()
        self.assertEqual(video["thumbnail"], "")


class PhotoAndClipTests(TestCase):
    """The precedence rule that replaced a validation error.

    Every seeded card carries an `image_url`, so refusing to save a card with
    both made the video field unusable on all of them. Nothing is refused now.
    """

    @classmethod
    def setUpTestData(cls):
        cls.section = ClassesSection.objects.create()

    def card(self, **kwargs):
        return ClassCard.objects.create(
            section=self.section,
            slug="fresh-cut",
            name="Fresh Cut",
            href="/services",
            **kwargs,
        )

    def test_a_card_may_carry_both_without_complaint(self):
        card = self.card(
            image_url="https://example.com/a.jpg", video_url=CLOUDINARY_VIDEO
        )
        card.full_clean()  # would raise if anything still refused this

    def test_the_clip_is_what_such_a_card_plays(self):
        card = self.card(
            image_url="https://example.com/a.jpg", video_url=CLOUDINARY_VIDEO
        )
        payload = ClassCardSerializer(card).data
        self.assertEqual(payload["video"]["src"], CLOUDINARY_VIDEO)
        # The photo is still sent; the frontend simply does not reach for it
        # while there is a clip. Emptying the URL brings it straight back.
        self.assertEqual(payload["image"], "https://example.com/a.jpg")

    def test_emptying_the_url_brings_the_photo_back(self):
        card = self.card(
            image_url="https://example.com/a.jpg", video_url=CLOUDINARY_VIDEO
        )
        card.video_url = ""
        card.save()
        self.assertEqual(ClassCardSerializer(card).data["video"], {})


class SerializerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.section = ClassesSection.objects.create()

    def test_a_card_without_a_clip_serialises_an_empty_object(self):
        """`{}` and not null, so the frontend narrows on one shape."""
        card = ClassCard.objects.create(
            section=self.section, slug="a", name="A", href="/services"
        )
        self.assertEqual(ClassCardSerializer(card).data["video"], {})

    def test_a_card_with_a_clip_serialises_a_playable_source(self):
        card = ClassCard.objects.create(
            section=self.section,
            slug="b",
            name="B",
            href="/services",
            video_url=CLOUDINARY_VIDEO,
        )
        video = ClassCardSerializer(card).data["video"]
        self.assertEqual(video["src"], CLOUDINARY_VIDEO)
        self.assertTrue(video["thumbnail"])


class AdminPageTests(TestCase):
    """Where the field has to actually be, which is where the work happens.

    Both pages are checked. The video field went missing from the section page
    twice -- it is the page named after the band, with every card on it, and
    it is not the one a fields list should get trimmed to fit.
    """

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_superuser("boss", "boss@example.com", "pw")
        cls.section = ClassesSection.objects.create()
        cls.card = ClassCard.objects.create(
            section=cls.section, slug="fresh-cut", name="Fresh Cut", href="/services"
        )

    def setUp(self):
        self.client.force_login(self.staff)

    def get(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode("utf-8", "replace")

    def section_url(self):
        return reverse("admin:sections_classessection_change", args=[self.section.pk])

    def card_url(self):
        return reverse("admin:sections_classcard_change", args=[self.card.pk])

    def test_the_section_page_has_a_video_url_box_for_every_card(self):
        html = self.get(self.section_url())
        self.assertEqual(len(re.findall(r'name="cards-\d+-video_url"', html)), 1)

    def test_the_card_page_has_one_too(self):
        self.assertIn('name="video_url"', self.get(self.card_url()))

    def test_neither_page_still_offers_a_clip_upload(self):
        """Removed on purpose: it needed a second service configured before it
        did anything, and sat dead until somebody had one."""
        for url in (self.section_url(), self.card_url()):
            html = self.get(url)
            self.assertNotIn('name="video_file"', html)
            self.assertNotIn('name="clear_video"', html)

    def test_the_page_says_a_clip_replaces_the_photo(self):
        """The rule is precedence now, so it has to be stated on the page
        rather than enforced by a refusal."""
        self.assertIn("replaces the photo", self.get(self.card_url()))
