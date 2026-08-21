"""The nightly housekeeping command.

This is the one piece of the system that has to work with nobody watching, so
what is tested here is mostly its behaviour when something is wrong rather
than when everything is fine.

Three properties matter and each has a test:

*   a successful run is **silent**, because cron mails whatever a job prints
    and a nightly all-clear teaches the recipient to filter the address;
*   a failing step **does not stop the others**, because a full disk must not
    also mean sessions stop being purged;
*   a failure **exits non-zero and says what broke**, because that exit code
    is the only thing that turns a silent problem into an email.
"""

import io
from datetime import timedelta
from unittest.mock import patch

from django.contrib.admin.models import ADDITION, LogEntry
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone


def run(**kwargs):
    """Run the command, returning (stdout, stderr, exit_code)."""
    out, err = io.StringIO(), io.StringIO()
    kwargs.setdefault("no_backup", True)
    code = 0
    try:
        call_command("maintenance", stdout=out, stderr=err, **kwargs)
    except SystemExit:
        code = 1
    return out.getvalue(), err.getvalue(), code


@override_settings(SALON_NOTIFY_EMAILS=["salon@example.com"])
class MaintenanceTests(TestCase):
    def setUp(self):
        # Every test needs email to look configured, or the health check
        # fails and masks whatever the test was actually about.
        self.email_ok = patch(
            "common.email_config.active_config",
            **{
                "return_value.recipients": ["salon@example.com"],
                "return_value.is_configured": True,
            },
        )
        self.email_ok.start()
        self.addCleanup(self.email_ok.stop)

    # --- output discipline ------------------------------------------------

    def test_a_clean_run_says_nothing_at_all(self):
        """cron mails whatever a job prints. A nightly all-clear is how the
        address ends up filtered."""
        out, err, code = run()
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        self.assertEqual(err, "")

    def test_running_it_by_hand_can_show_the_detail(self):
        out, _, code = run(verbosity=2)
        self.assertEqual(code, 0)
        self.assertIn("sessions:", out)
        self.assertIn("all clear", out)

    # --- failure behaviour ------------------------------------------------

    def test_a_failure_exits_non_zero_and_explains(self):
        """The exit code is what makes cron send the mail."""
        with patch(
            "core.management.commands.maintenance.Command._clear_sessions",
            side_effect=RuntimeError("database is locked"),
        ):
            _, err, code = run()
        self.assertEqual(code, 1)
        self.assertIn("database is locked", err)

    def test_one_broken_step_does_not_stop_the_others(self):
        """A full disk must not also mean sessions stop being purged."""
        with patch(
            "core.management.commands.maintenance.Command._prune_admin_log",
            side_effect=RuntimeError("boom"),
        ):
            _, err, code = run()
        self.assertEqual(code, 1)
        # The steps either side of the broken one still ran and still report.
        self.assertIn("sessions:", err)
        self.assertIn("email:", err)

    def test_a_failed_run_reports_what_worked_too(self):
        """"backup ok, email broken" is a different morning from "everything
        broken", and the mail should say which."""
        with patch(
            "core.management.commands.maintenance.Command._check_email",
            side_effect=RuntimeError("App Password rejected"),
        ):
            _, err, _ = run()
        self.assertIn("App Password rejected", err)
        self.assertIn("purged", err)  # the sessions step, which succeeded

    # --- the work itself --------------------------------------------------

    def test_expired_sessions_are_purged_and_live_ones_are_not(self):
        """Nobody gets signed out by housekeeping."""
        Session.objects.create(
            session_key="expired1",
            session_data="x",
            expire_date=timezone.now() - timedelta(days=1),
        )
        Session.objects.create(
            session_key="live1",
            session_data="x",
            expire_date=timezone.now() + timedelta(days=7),
        )
        run()
        keys = set(Session.objects.values_list("session_key", flat=True))
        self.assertEqual(keys, {"live1"})

    def make_log_entry(self, days_old):
        user = User.objects.create_user(f"u{days_old}")
        entry = LogEntry.objects.create(
            user=user,
            content_type=ContentType.objects.get_for_model(User),
            object_id=str(user.pk),
            object_repr="x",
            action_flag=ADDITION,
        )
        # auto_now_add on action_time, so it has to be set after the fact.
        LogEntry.objects.filter(pk=entry.pk).update(
            action_time=timezone.now() - timedelta(days=days_old)
        )
        return entry

    def test_the_admin_log_is_pruned_to_the_retention_window(self):
        old = self.make_log_entry(400)
        recent = self.make_log_entry(10)
        run(keep_days=365)
        remaining = set(LogEntry.objects.values_list("pk", flat=True))
        self.assertNotIn(old.pk, remaining)
        self.assertIn(recent.pk, remaining)

    def test_keep_days_zero_keeps_everything(self):
        """It is an audit trail; somebody may want the lot."""
        old = self.make_log_entry(4000)
        run(keep_days=0)
        self.assertTrue(LogEntry.objects.filter(pk=old.pk).exists())

    def test_running_twice_changes_nothing_the_second_time(self):
        """It has to be safe to leave on a timer."""
        self.make_log_entry(400)
        run(keep_days=365)
        first = LogEntry.objects.count()
        _, _, code = run(keep_days=365)
        self.assertEqual(code, 0)
        self.assertEqual(LogEntry.objects.count(), first)

    # --- health checks ----------------------------------------------------

    def test_it_notices_when_nobody_would_be_told_about_a_booking(self):
        """The silent failure this command exists to catch: bookings save,
        notifications do not send, and it looks like a quiet week."""
        self.email_ok.stop()
        with patch(
            "common.email_config.active_config",
            **{"return_value.recipients": [], "return_value.is_configured": False},
        ):
            _, err, code = run()
        self.email_ok.start()
        self.assertEqual(code, 1)
        self.assertIn("nobody will be told", err)

    def test_it_notices_email_configured_but_unusable(self):
        self.email_ok.stop()
        with patch(
            "common.email_config.active_config",
            **{
                "return_value.recipients": ["salon@example.com"],
                "return_value.is_configured": False,
            },
        ):
            _, err, code = run()
        self.email_ok.start()
        self.assertEqual(code, 1)
        self.assertIn("not configured", err)
