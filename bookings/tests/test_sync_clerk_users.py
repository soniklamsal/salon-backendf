"""`manage.py sync_clerk_users`, against a mocked Clerk.

Nothing here touches the network. The command is read-only against Clerk, so
the interesting behaviour is all on this side: how a Clerk user maps onto a
`auth.User` + `ClerkProfile` pair, that re-running never duplicates anyone, and
that the mirrored rows cannot be used to log into Django.
"""

from io import StringIO
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from bookings.models import ClerkProfile

User = get_user_model()


def clerk_user(user_id="user_abc", email="asha@example.com", **extra):
    """One entry as Clerk's /v1/users actually shapes it."""
    payload = {
        "id": user_id,
        "first_name": "Asha",
        "last_name": "Sharma",
        "image_url": "https://img.clerk.test/asha.png",
        "created_at": 1_700_000_000_000,
        "last_sign_in_at": 1_700_100_000_000,
        "banned": False,
        "primary_email_address_id": "idn_1",
        "email_addresses": [
            {
                "id": "idn_1",
                "email_address": email,
                "verification": {"status": "verified", "strategy": "email_code"},
            }
        ],
        "phone_numbers": [],
        "external_accounts": [],
    }
    payload.update(extra)
    return payload


def fake_session(pages):
    """A requests.Session whose GET returns each page in turn."""
    session = MagicMock()
    responses = []
    for page in pages:
        response = MagicMock(status_code=200)
        response.json.return_value = page
        responses.append(response)
    session.get.side_effect = responses
    return session


@override_settings(CLERK_SECRET_KEY="sk_test_fake")
class SyncClerkUsersTests(TestCase):
    def run_sync(self, pages, **options):
        out = StringIO()
        with patch("requests.Session", return_value=fake_session(pages)):
            call_command("sync_clerk_users", stdout=out, **options)
        return out.getvalue()

    def test_creates_a_user_and_profile(self):
        self.run_sync([[clerk_user()]])

        profile = ClerkProfile.objects.get()
        self.assertEqual(profile.clerk_user_id, "user_abc")
        self.assertEqual(profile.user.email, "asha@example.com")
        self.assertEqual(profile.user.first_name, "Asha")
        self.assertTrue(profile.email_verified)

    def test_mirrored_user_cannot_log_into_django(self):
        """They authenticate through Clerk; a usable password here would be a
        second way in that nobody is watching."""
        self.run_sync([[clerk_user()]])
        self.assertFalse(ClerkProfile.objects.get().user.has_usable_password())

    def test_rerunning_updates_rather_than_duplicates(self):
        self.run_sync([[clerk_user()]])
        self.run_sync([[clerk_user(email="new@example.com")]])

        self.assertEqual(ClerkProfile.objects.count(), 1)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(ClerkProfile.objects.get().user.email, "new@example.com")

    def test_survives_a_user_row_whose_profile_was_deleted(self):
        """One manual delete in the admin used to abort the sync for everyone.

        The mirrored `auth.User` outlives its profile, and the username is
        derived from the Clerk id — so the next sync tried to create a user
        that already existed and died on the unique constraint.
        """
        self.run_sync([[clerk_user()]])
        ClerkProfile.objects.all().delete()

        self.run_sync([[clerk_user()]])

        self.assertEqual(ClerkProfile.objects.count(), 1)
        self.assertEqual(User.objects.count(), 1)

    def test_coexists_with_an_account_created_by_a_booking(self):
        """`_ensure_account_visible` builds a row with the same username."""
        from api.views import _ensure_account_visible

        _ensure_account_visible({"sub": "user_abc", "email": "asha@example.com"})
        self.run_sync([[clerk_user()]])

        self.assertEqual(ClerkProfile.objects.count(), 1)
        self.assertEqual(User.objects.count(), 1)

    def test_google_signup_reports_one_provider_not_two(self):
        """Clerk names the same route twice: `from_oauth_google` on the email
        and `oauth_google` on the linked account."""
        item = clerk_user(
            email_addresses=[
                {
                    "id": "idn_1",
                    "email_address": "asha@example.com",
                    "verification": {
                        "status": "verified",
                        "strategy": "from_oauth_google",
                    },
                }
            ],
            external_accounts=[{"provider": "oauth_google"}],
            primary_email_address_id="idn_1",
        )
        self.run_sync([[item]])

        profile = ClerkProfile.objects.get()
        self.assertEqual(profile.providers, "oauth_google")
        self.assertEqual(profile.provider_labels, "Google")
        self.assertTrue(profile.signed_in_with_google)

    def test_paginates_until_a_short_page(self):
        first = [clerk_user(user_id=f"user_{i}") for i in range(100)]
        second = [clerk_user(user_id="user_last")]
        self.run_sync([first, second])
        self.assertEqual(ClerkProfile.objects.count(), 101)

    def test_prune_removes_accounts_deleted_in_clerk(self):
        self.run_sync([[clerk_user(user_id="user_a"), clerk_user(user_id="user_b")]])
        self.assertEqual(ClerkProfile.objects.count(), 2)

        self.run_sync([[clerk_user(user_id="user_a")]], prune=True)

        self.assertEqual(
            list(ClerkProfile.objects.values_list("clerk_user_id", flat=True)),
            ["user_a"],
        )

    def test_prune_also_removes_the_orphaned_user_row(self):
        """Otherwise it sits in the admin looking like a real account."""
        self.run_sync([[clerk_user(user_id="user_a"), clerk_user(user_id="user_b")]])
        self.run_sync([[clerk_user(user_id="user_a")]], prune=True)
        self.assertEqual(User.objects.count(), 1)

    def test_without_prune_nothing_is_removed(self):
        self.run_sync([[clerk_user(user_id="user_a"), clerk_user(user_id="user_b")]])
        self.run_sync([[clerk_user(user_id="user_a")]])
        self.assertEqual(ClerkProfile.objects.count(), 2)

    def test_a_staff_superuser_is_never_touched(self):
        """Pruning must not reach accounts that are not Clerk mirrors."""
        User.objects.create_superuser("owner", "owner@salon.test", "x" * 20)
        self.run_sync([[clerk_user()]], prune=True)
        self.assertTrue(User.objects.filter(username="owner").exists())

    def test_timestamps_come_across_as_real_datetimes(self):
        self.run_sync([[clerk_user()]])
        profile = ClerkProfile.objects.get()
        self.assertIsNotNone(profile.clerk_created_at)
        self.assertIsNotNone(profile.last_sign_in_at)
        self.assertIsNotNone(profile.last_synced_at)

    def test_missing_timestamps_stay_none(self):
        self.run_sync([[clerk_user(last_sign_in_at=None)]])
        self.assertIsNone(ClerkProfile.objects.get().last_sign_in_at)

    def test_user_with_no_email_is_handled(self):
        self.run_sync([[clerk_user(email_addresses=[], primary_email_address_id=None)]])
        self.assertEqual(ClerkProfile.objects.get().user.email, "")


class SyncClerkUsersConfigTests(TestCase):
    @override_settings(CLERK_SECRET_KEY="")
    def test_missing_secret_key_explains_itself(self):
        with self.assertRaises(CommandError) as caught:
            call_command("sync_clerk_users", stdout=StringIO())
        self.assertIn("CLERK_SECRET_KEY", str(caught.exception))

    @override_settings(CLERK_SECRET_KEY="sk_test_wrong")
    def test_rejected_key_is_reported_as_a_key_problem(self):
        session = MagicMock()
        session.get.return_value = MagicMock(status_code=401)
        with patch("requests.Session", return_value=session):
            with self.assertRaises(CommandError) as caught:
                call_command("sync_clerk_users", stdout=StringIO())
        self.assertIn("401", str(caught.exception))
