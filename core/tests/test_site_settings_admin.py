"""The Site settings form, which is where the header's logo is chosen.

The form carries one thing that is not an ordinary field: a mock of the header.
It is easy to break without noticing, and a preview that has quietly stopped
reflecting the settings is worse than no preview, because it is still believed.

There is no size control to test. The logo is drawn at a fixed height, so the
only thing that can be got wrong here is which mark is shown.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.admin import LOGO_HEIGHT_PX, LOGO_MAX_WIDTH_PX
from core.models import NavLink, SiteSettings


class NavbarPreviewTests(TestCase):
    def setUp(self):
        get_user_model().objects.create_superuser("root", "root@example.com", "pw")
        self.client.login(username="root", password="pw")
        self.row = SiteSettings.load()
        self.row.save()

    def form(self):
        return self.client.get(
            reverse("admin:core_sitesettings_change", args=[self.row.pk])
        ).content.decode()

    def test_the_preview_comes_before_the_fields_it_previews(self):
        html = self.form()
        self.assertIn("data-navbar-preview", html)
        self.assertLess(html.index("data-navbar-preview"), html.index("id_brand_name"))

    def test_the_preview_draws_the_logo_at_the_fixed_size(self):
        self.row.logo_url = "https://cdn.example.com/logo.svg"
        self.row.save()

        html = self.form()
        self.assertIn(f"height:{LOGO_HEIGHT_PX}px", html)
        self.assertIn(f"max-width:{LOGO_MAX_WIDTH_PX}px", html)

    def test_the_preview_shows_the_header_links_and_cta(self):
        NavLink.objects.create(label="Home", href="/", show_in_header=True, order=0)
        NavLink.objects.create(
            label="Footer only", href="/x", show_in_header=False, order=1
        )

        html = self.form()
        self.assertIn("salon-navbar__link", html)
        self.assertIn(">Home<", html)
        # A footer-only link is not in the header, so previewing it would be a
        # picture of a bar that does not exist.
        self.assertNotIn(">Footer only<", html)
        self.assertIn(self.row.nav_cta_label, html)

    def test_both_marks_are_rendered_so_the_script_can_swap_them(self):
        # With no logo the wordmark shows and the <img> is hidden, not absent:
        # navbar-preview.js reveals it when a file is chosen, and cannot build
        # an <img> for a file that has not been uploaded yet.
        html = self.form()
        self.assertIn("salon-navbar__logo", html)
        self.assertIn("salon-navbar__wordmark", html)
        self.assertIn("navbar-preview.js", html)

    def test_the_form_offers_no_logo_sizing(self):
        # The header's height is what the rest of the page is laid out against,
        # so it is not editable. Re-adding a control here would reopen that.
        html = self.form()
        for gone in ("id_logo_height", "id_logo_height_mobile", "id_logo_width"):
            self.assertNotIn(gone, html)
