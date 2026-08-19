"""The SMTP settings screen.

Two things are worth pinning down here and neither is the form rendering.

The first is precedence. There are now two places SMTP settings can come from,
and "which one is in force" is exactly the question nobody can answer from
looking at either one. Getting it wrong is silent: mail keeps sending, from
the wrong account.

The second is that the password does not leak. It is a working credential for
a real Gmail account, and the two ways it escapes are a database copy and the
HTML of the admin page it is edited on.
"""

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse

from common.crypto import PREFIX, decrypt, encrypt
from common.testing import admin_static_storage
from common.email_config import active_config
from core.admin import EmailSettingsForm
from core.models import EmailSettings

PASSWORD = "abcdefghijklmnop"


class EncryptionTests(TestCase):
    def test_a_password_round_trips(self):
        self.assertEqual(decrypt(encrypt(PASSWORD)), PASSWORD)

    def test_the_same_password_encrypts_differently_each_time(self):
        """A random IV, so a repeated value is not recognisable as repeated."""
        self.assertNotEqual(encrypt(PASSWORD), encrypt(PASSWORD))

    def test_empty_stays_empty_rather_than_becoming_an_opaque_blob(self):
        """"Not configured yet" has to stay distinguishable from "set"."""
        self.assertEqual(encrypt(""), "")
        self.assertEqual(decrypt(""), "")

    def test_a_plaintext_value_from_before_this_existed_is_readable(self):
        self.assertEqual(decrypt("typed-in-by-hand"), "typed-in-by-hand")

    @override_settings(SECRET_KEY="a-completely-different-key")
    def test_a_rotated_secret_key_reads_back_empty_rather_than_raising(self):
        """Mail stops; no page 500s. The admin re-enters the password."""
        ciphertext = PREFIX + "gAAAAABnot-a-real-token"
        with self.assertLogs("common", level="ERROR"):
            self.assertEqual(decrypt(ciphertext), "")

    def test_the_column_never_holds_the_plaintext(self):
        """The point of the exercise: a database dump leaks nothing usable."""
        obj = EmailSettings.objects.create(username="a@b.com", password=PASSWORD)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT password FROM core_emailsettings WHERE id = %s", [obj.pk]
            )
            stored = cursor.fetchone()[0]
        self.assertNotIn(PASSWORD, stored)
        self.assertTrue(stored.startswith(PREFIX))
        # ...and still reads back correctly through the ORM.
        self.assertEqual(EmailSettings.objects.get(pk=obj.pk).password, PASSWORD)


@override_settings(
    EMAIL_HOST_USER="env@example.com",
    EMAIL_HOST_PASSWORD="env-password",
    EMAIL_HOST="smtp.env.example",
    SALON_NOTIFY_EMAILS=["env-notify@example.com"],
    DEFAULT_FROM_EMAIL="env@example.com",
)
class PrecedenceTests(TestCase):
    def test_with_no_row_the_env_file_is_used(self):
        config = active_config()
        self.assertEqual(config.source, ".env")
        self.assertEqual(config.username, "env@example.com")

    def test_a_disabled_row_does_not_override_anything(self):
        """Switching emails off must not silently swap the credentials too."""
        EmailSettings.objects.create(
            is_enabled=False, username="admin@example.com", password=PASSWORD
        )
        config = active_config()
        self.assertEqual(config.source, ".env")
        self.assertEqual(config.username, "env@example.com")

    def test_an_enabled_row_wins(self):
        EmailSettings.objects.create(
            is_enabled=True, username="admin@example.com", password=PASSWORD
        )
        config = active_config()
        self.assertEqual(config.source, "admin")
        self.assertEqual(config.username, "admin@example.com")
        self.assertEqual(config.password, PASSWORD)

    def test_blank_fields_fall_through_instead_of_blanking_the_env_value(self):
        """Filling in only an account is a complete setup, not a broken one."""
        EmailSettings.objects.create(
            is_enabled=True, username="admin@example.com", password=PASSWORD, host=""
        )
        self.assertEqual(active_config().host, "smtp.env.example")

    def test_the_security_choice_sets_the_port_and_the_encryption_together(self):
        obj = EmailSettings.objects.create(
            is_enabled=True,
            username="admin@example.com",
            password=PASSWORD,
            security=EmailSettings.Security.SSL,
        )
        config = active_config()
        self.assertEqual((config.port, config.use_ssl, config.use_tls), (465, True, False))

        obj.security = EmailSettings.Security.STARTTLS
        obj.save()
        config = active_config()
        self.assertEqual((config.port, config.use_ssl, config.use_tls), (587, False, True))

    def test_an_explicit_port_beats_the_one_implied_by_the_choice(self):
        EmailSettings.objects.create(
            is_enabled=True, username="a@b.com", password=PASSWORD, port=2525
        )
        self.assertEqual(active_config().port, 2525)

    def test_recipients_default_to_the_sending_account(self):
        EmailSettings.objects.create(
            is_enabled=True, username="admin@example.com", password=PASSWORD
        )
        self.assertEqual(active_config().recipients, ["admin@example.com"])

    def test_recipients_accept_lines_and_commas_together(self):
        EmailSettings.objects.create(
            is_enabled=True,
            username="a@b.com",
            password=PASSWORD,
            # As a browser posts a textarea: CRLF endings.
            notify_emails="one@x.com,two@x.com\r\nthree@x.com\r\n",
        )
        self.assertEqual(
            active_config().recipients, ["one@x.com", "two@x.com", "three@x.com"]
        )

    def test_a_sender_name_becomes_a_display_name(self):
        EmailSettings.objects.create(
            is_enabled=True,
            username="a@b.com",
            password=PASSWORD,
            from_name="Salon Kathmandu",
        )
        self.assertEqual(active_config().from_email, "Salon Kathmandu <a@b.com>")


class FormTests(TestCase):
    def base(self, **overrides):
        data = {
            "is_enabled": "on",
            "username": "salon@gmail.com",
            "password": PASSWORD,
            "from_name": "",
            "notify_emails": "",
            "host": "",
            "port": "",
            "security": EmailSettings.Security.STARTTLS,
        }
        data.update(overrides)
        return data

    def test_the_spaces_google_shows_are_stripped(self):
        """Pasted as displayed, the spaces would fail as a wrong password."""
        form = EmailSettingsForm(self.base(password="abcd efgh ijkl mnop"))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["password"], PASSWORD)

    def test_a_blank_password_keeps_the_stored_one(self):
        """So editing the sender name is not a re-type of the password."""
        existing = EmailSettings.objects.create(
            is_enabled=True, username="salon@gmail.com", password=PASSWORD
        )
        form = EmailSettingsForm(
            self.base(password="", from_name="Salon"), instance=existing
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertEqual(EmailSettings.objects.get(pk=existing.pk).password, PASSWORD)

    def test_switching_on_without_credentials_is_refused(self):
        """Otherwise the screen reads "on" while nothing is ever sent."""
        form = EmailSettingsForm(self.base(password="", username=""))
        self.assertFalse(form.is_valid())
        self.assertIn("Gmail address", str(form.errors))

    def test_it_can_be_saved_switched_off_while_still_incomplete(self):
        form = EmailSettingsForm(self.base(is_enabled="", username="", password=""))
        self.assertTrue(form.is_valid(), form.errors)


class AdminScreenTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="boss", email="boss@example.com", password="x"
        )
        self.client.force_login(self.admin)
        self.settings_row = EmailSettings.objects.create(
            is_enabled=True, username="salon@gmail.com", password=PASSWORD
        )
        self.url = reverse(
            "admin:core_emailsettings_change", args=[self.settings_row.pk]
        )

    def test_the_password_is_never_rendered_into_the_page(self):
        """It would land in the HTML, in autofill, and in any proxy log."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, PASSWORD)

    def test_the_screen_offers_the_app_password_link(self):
        response = self.client.get(self.url)
        self.assertContains(response, "myaccount.google.com/apppasswords")

    def test_the_status_panel_names_which_source_is_in_force(self):
        response = self.client.get(self.url)
        self.assertContains(response, "this screen")

    def test_the_test_button_records_what_happened(self):
        url = reverse("admin:core_emailsettings_send_test")
        response = self.client.post(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.settings_row.refresh_from_db()
        self.assertIsNotNone(self.settings_row.last_test_at)
        self.assertTrue(self.settings_row.last_test_detail)

    def test_a_get_never_sends(self):
        """A prefetch or a crawler must not be able to fire it."""
        url = reverse("admin:core_emailsettings_send_test")
        self.client.get(url)
        self.settings_row.refresh_from_db()
        self.assertIsNone(self.settings_row.last_test_at)

    def test_a_signed_out_visitor_cannot_reach_the_test_button(self):
        self.client.logout()
        response = self.client.post(reverse("admin:core_emailsettings_send_test"))
        self.assertIn(response.status_code, (302, 403))
        self.settings_row.refresh_from_db()
        self.assertIsNone(self.settings_row.last_test_at)


class AdvancedServerFieldTests(TestCase):
    """The collapsed section. Everything in it is optional; 0 is not a port."""

    def base(self, **overrides):
        data = {
            "is_enabled": "",
            "username": "",
            "password": "",
            "from_name": "",
            "notify_emails": "",
            "host": "",
            "port": "",
            "security": EmailSettings.Security.STARTTLS,
        }
        data.update(overrides)
        return data

    def test_all_three_can_be_left_alone(self):
        """Gmail needs none of them, so blank has to be valid."""
        form = EmailSettingsForm(self.base())
        self.assertTrue(form.is_valid(), form.errors)

    def test_zero_is_refused_rather_than_quietly_meaning_unset(self):
        """Port 0 tells the OS to choose, which for a client is nowhere."""
        form = EmailSettingsForm(self.base(port="0"))
        self.assertFalse(form.is_valid())
        self.assertIn("port", form.errors)

    def test_a_port_above_the_valid_range_is_refused(self):
        form = EmailSettingsForm(self.base(port="70000"))
        self.assertFalse(form.is_valid())
        self.assertIn("port", form.errors)

    def test_a_real_port_is_accepted(self):
        form = EmailSettingsForm(self.base(port="2525"))
        self.assertTrue(form.is_valid(), form.errors)

    def test_security_defaults_to_the_gmail_answer(self):
        """It is marked required, so it must never be empty to begin with."""
        self.assertEqual(EmailSettings().security, EmailSettings.Security.STARTTLS)


class DescriptionMarkupTests(TestCase):
    """Fieldset descriptions are auto-escaped unless marked safe.

    Worth a test rather than an eyeball: escaped markup still *reads* almost
    right, so the failure is a link that is not a link -- and the App Password
    link is the one thing on this screen the salon cannot proceed without.
    """

    def setUp(self):
        self.client.force_login(
            get_user_model().objects.create_superuser(
                username="boss2", email="b@example.com", password="x"
            )
        )
        EmailSettings.objects.create(pk=1)
        self.url = reverse("admin:core_emailsettings_change", args=[1])

    def test_the_app_password_link_is_a_real_anchor(self):
        response = self.client.get(self.url)
        self.assertContains(
            response, '<a href="https://myaccount.google.com/apppasswords"'
        )

    def test_no_description_markup_is_shown_as_literal_text(self):
        response = self.client.get(self.url)
        page = response.content.decode()
        self.assertNotIn("&lt;b&gt;", page)
        self.assertNotIn("&lt;a href", page)


@admin_static_storage
class SendTestEmailAjaxTests(TestCase):
    """Sending the test without freezing the page for the length of the send.

    A send can take up to EMAIL_TIMEOUT, and the form-post version spends all
    of it on a blank screen to deliver one message and a refreshed table. The
    form post is deliberately kept and still tested above; these check that the
    JSON sibling reaches the same helper and answers in a shape the script can
    use whatever happens.
    """

    def setUp(self):
        self.client.force_login(
            get_user_model().objects.create_superuser(
                username="boss3", email="b3@example.com", password="x" * 20
            )
        )
        self.row = EmailSettings.objects.create(
            is_enabled=True, username="salon@gmail.com", password=PASSWORD
        )
        self.url = reverse("admin:core_emailsettings_send_test_json")

    def post(self):
        return self.client.post(self.url, data="{}", content_type="application/json")

    def test_it_records_what_happened(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.row.refresh_from_db()
        self.assertIsNotNone(self.row.last_test_at)
        self.assertTrue(self.row.last_test_detail)

    def test_it_answers_with_the_refreshed_status_panel(self):
        """The panel is the only thing on the page the send changes."""
        body = self.post().json()
        self.assertIn("status", body["panels"])
        self.assertIn("data-salon-panel", body["panels"]["status"])

    def test_it_reports_the_outcome_as_a_message(self):
        body = self.post().json()
        self.assertTrue(body["messages"])

    def test_both_buttons_go_through_one_helper(self):
        """Two ways of asking must not disagree about the answer."""
        self.post()
        self.row.refresh_from_db()
        from_json = self.row.last_test_detail

        self.client.post(reverse("admin:core_emailsettings_send_test"))
        self.row.refresh_from_db()
        self.assertEqual(self.row.last_test_detail, from_json)

    def test_a_get_never_sends(self):
        """A prefetch or a crawler must not be able to fire it."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)
        self.row.refresh_from_db()
        self.assertIsNone(self.row.last_test_at)

    def test_a_signed_out_visitor_gets_json_rather_than_a_login_page(self):
        self.client.logout()
        response = self.post()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["Content-Type"], "application/json")
        self.row.refresh_from_db()
        self.assertIsNone(self.row.last_test_at)

    def test_the_screen_carries_the_hooks_the_script_needs(self):
        """The script cannot add these; without them it silently does nothing."""
        html = self.client.get(
            reverse("admin:core_emailsettings_change", args=[self.row.pk])
        ).content.decode()
        self.assertIn("data-salon-json", html)
        self.assertIn('data-salon-panel="status"', html)
        self.assertIn("salon-ajax.js", html)

    def test_the_plain_form_still_posts_to_the_non_json_url(self):
        """It is the no-JavaScript path and must not have been replaced."""
        html = self.client.get(
            reverse("admin:core_emailsettings_change", args=[self.row.pk])
        ).content.decode()
        self.assertIn(reverse("admin:core_emailsettings_send_test"), html)

    def test_the_status_panel_uses_theme_tokens(self):
        """Hard-coded greys were close to illegible on the dark surface."""
        body = self.post().json()
        self.assertIn("var(--salon-", body["panels"]["status"])
