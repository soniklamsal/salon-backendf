"""The admin's AJAX layer, at the level of the mechanism rather than a feature.

Two things here are worth more than the rest.

The first is that a JSON endpoint answers **JSON** whatever happens to it. An
expired session, a wrong verb, a locked database and an outright bug all have
to arrive as something the caller can read; the moment one of them returns an
HTML page, `response.json()` throws a parse error and the person clicking sees
nothing at all.

The second is the allowlists. `field` and `action` arrive in a request body
written by the browser, and without `ajax_toggle_fields` / `ajax_row_actions`
those are an arbitrary column write and a route to `delete_selected`.

Nothing here tests the JavaScript, which is untested by design -- so the tests
that matter most assert that the *hooks it depends on* are present in the
rendered page, in the manner of core/tests/test_site_settings_admin.py.
"""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from common.testing import admin_static_storage
from core.models import NavLink

User = get_user_model()


@admin_static_storage
class ScriptLoadingTests(TestCase):
    """Every admin page has to reach the script, and the login page must not."""

    def setUp(self):
        self.client.force_login(
            User.objects.create_superuser("boss", "b@salon.test", "x" * 20)
        )

    def test_the_script_loads_on_the_dashboard(self):
        """The index renders no {{ media }}, so a class Media would never arrive."""
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, "salon-ajax.js")

    def test_the_script_loads_on_a_changelist(self):
        """Jazzmin's change_list.html has its own extrajs; this rides its block.super."""
        response = self.client.get(reverse("admin:core_navlink_changelist"))
        self.assertContains(response, "salon-ajax.js")

    def test_the_script_loads_on_a_change_form(self):
        link = NavLink.objects.create(label="Home", href="/")
        response = self.client.get(
            reverse("admin:core_navlink_change", args=[link.pk])
        )
        self.assertContains(response, "salon-ajax.js")

    def test_the_config_block_carries_a_token_on_the_dashboard(self):
        """The dashboard has no form, so there is no hidden input to scrape."""
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, "salon-ajax-config")
        self.assertTrue(self._config(response)["csrfToken"])

    def test_a_changelist_advertises_its_own_endpoints(self):
        response = self.client.get(reverse("admin:core_navlink_changelist"))
        endpoints = self._config(response)["endpoints"]
        self.assertIn("toggle", endpoints)
        self.assertIn("is_published", endpoints["toggleFields"])

    def test_an_admin_that_did_not_opt_in_advertises_nothing(self):
        """The mixin is inert until a ModelAdmin names what it will accept."""
        response = self.client.get(reverse("admin:auth_user_changelist"))
        self.assertEqual(self._config(response)["endpoints"], {})

    def test_the_login_page_does_not_load_the_script(self):
        self.client.logout()
        response = self.client.get(reverse("admin:login"))
        self.assertNotContains(response, "salon-ajax.js")

    def _config(self, response):
        html = response.content.decode()
        raw = html.split('id="salon-ajax-config"', 1)[1]
        return json.loads(raw.split(">", 1)[1].split("</script>", 1)[0])


class ToggleEndpointTests(TestCase):
    def setUp(self):
        self.client.force_login(
            User.objects.create_superuser("boss", "b@salon.test", "x" * 20)
        )
        self.link = NavLink.objects.create(label="Home", href="/", is_published=True)
        self.url = reverse("admin:core_navlink_ajax_toggle")

    def post(self, **body):
        return self.client.post(
            self.url, data=json.dumps(body), content_type="application/json"
        )

    def test_a_toggle_saves_and_answers_json(self):
        response = self.post(pk=self.link.pk, field="is_published", value=False)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.link.refresh_from_db()
        self.assertFalse(self.link.is_published)

    def test_the_value_sent_is_the_value_set_rather_than_a_flip(self):
        """A stale row plus a flip turns something back on; a value does not."""
        self.post(pk=self.link.pk, field="is_published", value=False)
        self.post(pk=self.link.pk, field="is_published", value=False)
        self.link.refresh_from_db()
        self.assertFalse(self.link.is_published)

    def test_a_field_outside_the_allowlist_is_refused(self):
        """Otherwise the request body chooses which column to write."""
        response = self.post(pk=self.link.pk, field="label", value=True)
        self.assertEqual(response.status_code, 400)
        self.link.refresh_from_db()
        self.assertEqual(self.link.label, "Home")

    def test_a_get_changes_nothing(self):
        """A prefetch or a crawler must not be able to publish anything."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)
        self.link.refresh_from_db()
        self.assertTrue(self.link.is_published)

    def test_a_signed_out_request_gets_json_not_a_login_page(self):
        """The whole client-side session handling rests on this.

        admin_view() would answer with a 302 to the login form, fetch would
        follow it, and .json() on the resulting HTML throws a SyntaxError that
        reads exactly like a bug in our own script.
        """
        self.client.logout()
        response = self.post(pk=self.link.pk, field="is_published", value=False)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response.json()["reason"], "signed_out")
        self.link.refresh_from_db()
        self.assertTrue(self.link.is_published)

    def test_a_non_staff_user_is_refused(self):
        self.client.force_login(User.objects.create_user("walkin", password="x" * 20))
        response = self.post(pk=self.link.pk, field="is_published", value=False)
        self.assertEqual(response.status_code, 401)
        self.link.refresh_from_db()
        self.assertTrue(self.link.is_published)

    def test_a_missing_row_says_so_rather_than_raising(self):
        response = self.post(pk=99999, field="is_published", value=False)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["reason"], "missing")

    def test_a_malformed_body_is_refused(self):
        response = self.client.post(
            self.url, data="not json", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["reason"], "bad_request")

    def test_a_toggle_writes_a_log_entry(self):
        """The list_editable checkbox it replaces wrote one; history must not stop."""
        from django.contrib.admin.models import LogEntry

        self.post(pk=self.link.pk, field="is_published", value=False)
        self.assertEqual(LogEntry.objects.count(), 1)

    def test_the_response_carries_no_message_on_success(self):
        """One alert per checkbox would bury the changelist it is on."""
        response = self.post(pk=self.link.pk, field="is_published", value=False)
        self.assertEqual(response.json()["messages"], [])


class CsrfTests(TestCase):
    """CSRF is enforced by the decorator, not left to the caller."""

    def test_a_post_without_a_token_is_refused(self):
        from django.test import Client

        user = User.objects.create_superuser("boss", "b@salon.test", "x" * 20)
        link = NavLink.objects.create(label="Home", href="/", is_published=True)

        client = Client(enforce_csrf_checks=True)
        client.force_login(user)
        response = client.post(
            reverse("admin:core_navlink_ajax_toggle"),
            data=json.dumps({"pk": link.pk, "field": "is_published", "value": False}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        link.refresh_from_db()
        self.assertTrue(link.is_published)
