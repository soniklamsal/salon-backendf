"""The About page admin, where the bullet columns are edited.

`AboutColumn` holds either prose (`body`) or a bullet list (`items`), and for
the bullet columns `body` is correctly blank. Django admin cannot nest an
inline inside an inline, so those bullets were once invisible on the About
page and the empty Body box read as lost content. These tests hold open the
two places the wording can now be found and changed.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from common.testing import admin_static_storage
from sections.models import AboutColumn, AboutColumnItem, AboutSection

User = get_user_model()

BULLET = "Premium hair styling stations"


@admin_static_storage
class AboutBulletVisibilityTests(TestCase):
    def setUp(self):
        User.objects.create_superuser("boss", "boss@example.com", "pw")
        self.client.login(username="boss", password="pw")

        self.section = AboutSection.objects.first() or AboutSection.objects.create()
        self.column = AboutColumn.objects.create(
            section=self.section, heading="Our Facilities", body="", order=90
        )
        AboutColumnItem.objects.create(column=self.column, text=BULLET, order=0)

    def test_the_about_page_shows_the_bullets_next_to_the_blank_body(self):
        """The screen the empty Body box appears on must show them too."""
        response = self.client.get(
            reverse("admin:sections_aboutsection_change", args=[self.section.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, BULLET)

    def test_bullets_have_a_changelist_of_their_own(self):
        response = self.client.get(reverse("admin:sections_aboutcolumnitem_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, BULLET)

    def test_the_text_is_editable_from_that_changelist(self):
        """`text` in list_editable is what makes the wording changeable there."""
        response = self.client.get(reverse("admin:sections_aboutcolumnitem_changelist"))
        self.assertIn("text", response.context["cl"].list_editable)

    def test_a_prose_column_says_so_instead_of_looking_empty(self):
        AboutColumn.objects.create(
            section=self.section, heading="Mission", body="Prose here.", order=91
        )
        response = self.client.get(
            reverse("admin:sections_aboutsection_change", args=[self.section.pk])
        )
        self.assertContains(response, "uses the Body box instead")
