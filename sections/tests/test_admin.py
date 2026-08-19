"""The About page admin, where the bullet columns are edited.

`AboutColumn` holds either prose (`body`) or a bullet list (`items`), and for
the bullet columns `body` is correctly blank. Django admin cannot nest an
inline inside an inline, so those bullets were once invisible on the About
page and the empty Body box read as lost content. These tests hold open the
two places the wording can now be found and changed.
"""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from common.cache import content_version
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


class PublishToggleTests(TestCase):
    """Publishing from the list, without re-POSTing every row on the page."""

    def setUp(self):
        User.objects.create_superuser("switch", "s@example.com", "pw")
        self.client.login(username="switch", password="pw")
        section = AboutSection.objects.first() or AboutSection.objects.create()
        self.column = AboutColumn.objects.create(
            section=section, heading="Facilities", is_published=True
        )
        self.url = reverse("admin:sections_aboutcolumn_ajax_toggle")

    def post(self, **body):
        return self.client.post(
            self.url, data=json.dumps(body), content_type="application/json"
        )

    def test_unpublishing_from_the_list_saves(self):
        response = self.post(pk=self.column.pk, field="is_published", value=False)
        self.assertEqual(response.status_code, 200)
        self.column.refresh_from_db()
        self.assertFalse(self.column.is_published)

    def test_it_bumps_the_content_version(self):
        """The reason this uses save() and not queryset.update().

        common/signals.py invalidates the public site's cached payload on
        post_save. An update() skips that, so the site would keep serving an
        unpublished column until something unrelated happened to save.
        """
        before = content_version()
        self.post(pk=self.column.pk, field="is_published", value=False)
        self.assertNotEqual(content_version(), before)

    def test_a_field_outside_the_allowlist_is_refused(self):
        """`field` arrives from the browser; without the allowlist it chooses
        which column to write."""
        response = self.post(pk=self.column.pk, field="heading", value="Hijacked")
        self.assertEqual(response.status_code, 400)
        self.column.refresh_from_db()
        self.assertEqual(self.column.heading, "Facilities")

    def test_a_signed_out_visitor_cannot_publish_anything(self):
        self.client.logout()
        response = self.post(pk=self.column.pk, field="is_published", value=False)
        self.assertEqual(response.status_code, 401)
        self.column.refresh_from_db()
        self.assertTrue(self.column.is_published)

    def test_list_editable_is_kept_as_the_no_javascript_path(self):
        from sections.admin import AboutColumnAdmin

        self.assertIn("is_published", AboutColumnAdmin.list_editable)
