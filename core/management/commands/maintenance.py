"""Everything the site needs done to it on a schedule, in one command.

    python manage.py maintenance

One command and therefore **one cron entry**, which is the whole design. The
alternative is four entries for `clearsessions`, `backup`, log pruning and a
health check, and the failure mode of four entries on shared hosting is that
three of them get set up and the fourth is discovered missing a year later.

Meant to be run nightly and forgotten:

    0 3 * * * cd /home/ACCOUNT/salon && /home/ACCOUNT/venv/bin/python manage.py maintenance

Three properties make it safe to leave alone.

*   **Idempotent.** Running it twice does nothing worse than running it once.
    Nothing here depends on having run yesterday.
*   **No step can stop another.** Each runs inside its own try/except and
    reports. A backup that fails because the disk is full must not also mean
    expired sessions stop being purged.
*   **It is loud when it should be.** A failed step exits non-zero, and cron
    mails the output to the account owner. That mail goes through the host's
    own MTA, not through this application's SMTP, so it still arrives on the
    day the thing that broke *is* the application's email.

## What it does, and why each one is here

`clearsessions` -- Django never purges expired sessions; the docs say plainly
that it is the operator's job. `django_session` otherwise grows for the life
of the site. Only rows already past `expire_date` are touched, so no one is
signed out by this.

Admin log pruning -- `django_admin_log` records every change made in the
admin and also grows forever. It is an audit trail, so the default retention
is a year rather than a week, and `--keep-days 0` turns pruning off entirely
for anyone who wants to keep the lot.

Backup -- `manage.py backup` already exists and is good. What it lacked was
anything that ran it. The database and the payment screenshots are the two
things that cannot be reconstructed from the repository.

Health checks -- the failures that matter on this site are silent ones. A
booking saves whether or not the notification email goes out, so a revoked
Gmail App Password looks exactly like a quiet week. These checks turn that
into a line in a cron email.
"""

import logging

from django.contrib.admin.models import LogEntry
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger("core")


class Command(BaseCommand):
    help = "Nightly housekeeping: sessions, admin log, backup, health checks."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep-days",
            type=int,
            default=365,
            help=(
                "Days of admin history to keep. 0 disables pruning. "
                "Default 365 -- it is an audit trail, not a cache."
            ),
        )
        parser.add_argument(
            "--backup-keep",
            type=int,
            default=14,
            help="How many backups to retain. Default 14.",
        )
        parser.add_argument(
            "--backup-dir",
            default="",
            help="Where backups go. Defaults to the backup command's own default.",
        )
        parser.add_argument(
            "--no-backup",
            action="store_true",
            help="Skip the backup, e.g. when something else already takes one.",
        )

    # --- steps -------------------------------------------------------------

    def _clear_sessions(self):
        from django.contrib.sessions.models import Session

        before = Session.objects.count()
        call_command("clearsessions", verbosity=0)
        after = Session.objects.count()
        return f"purged {before - after} expired session(s), {after} remain"

    def _prune_admin_log(self, keep_days):
        if keep_days <= 0:
            return "pruning disabled (--keep-days 0)"
        cutoff = timezone.now() - timezone.timedelta(days=keep_days)
        # `delete()` on a filtered queryset, not a loop: this table can be
        # large and there are no signals or cascades on it worth firing.
        removed, _ = LogEntry.objects.filter(action_time__lt=cutoff).delete()
        return f"removed {removed} admin log entr{'y' if removed == 1 else 'ies'} older than {keep_days}d"

    def _backup(self, options):
        import io

        kwargs = {"keep": options["backup_keep"], "verbosity": 0}
        if options["backup_dir"]:
            kwargs["output_dir"] = options["backup_dir"]
        # The backup command writes its own progress to stdout regardless of
        # verbosity. Swallowed here so a successful night produces no cron
        # mail at all -- see `handle`.
        sink = io.StringIO()
        call_command("backup", stdout=sink, **kwargs)
        return f"backup written, keeping {options['backup_keep']}"

    def _check_email(self):
        """Configured, not proven.

        Deliberately does not send anything. A nightly test email is noise
        that gets filtered, and a filtered test email is worse than none --
        it looks like proof while proving nothing. This catches the case that
        actually happens: somebody rotates SECRET_KEY, the stored App
        Password no longer decrypts, and nobody finds out until a customer
        rings up asking why their booking was ignored.
        """
        from common.email_config import active_config

        config = active_config()
        if not config.recipients:
            raise RuntimeError(
                "No notification recipients configured -- bookings will be "
                "saved and nobody will be told. Set SALON_NOTIFY_EMAILS, or "
                "fill in Admin -> Site -> Email / SMTP settings."
            )
        if not config.is_configured:
            raise RuntimeError(
                "Email is not configured, so booking and enquiry "
                "notifications are not being sent. Check Admin -> Site -> "
                "Email / SMTP settings, or EMAIL_HOST_USER / "
                "EMAIL_HOST_PASSWORD in .env."
            )
        return f"configured, notifying {', '.join(config.recipients)}"

    # There is deliberately no database health check here.
    #
    # The obvious one -- "refuse if this is SQLite with DEBUG off" -- cannot
    # ever be true on the live host, because settings.py raises at import
    # time in exactly that state. It *is* true under the test runner, which
    # pins the suite to SQLite. So the check could only ever produce a false
    # alarm, and a monitor that cries wolf is worse than no monitor.
    #
    # The steps above already prove the database is reachable and writable:
    # purging sessions and pruning the admin log are both writes.

    # --- run ---------------------------------------------------------------

    def handle(self, *args, **options):
        steps = [
            ("sessions", lambda: self._clear_sessions()),
            ("admin log", lambda: self._prune_admin_log(options["keep_days"])),
        ]
        if not options["no_backup"]:
            steps.append(("backup", lambda: self._backup(options)))
        steps.append(("email", lambda: self._check_email()))

        # Silent on success, on purpose.
        #
        # cron mails the account owner whenever a job writes output. A command
        # that reports five cheerful lines every night trains whoever receives
        # them to filter the address, and then the one night it has something
        # to say is the night nobody reads it. So an ordinary run prints
        # nothing and a failure prints everything.
        #
        # `-v 2` prints the detail anyway, which is what to use when running
        # it by hand to see what it actually did.
        verbose = options["verbosity"] >= 2

        failures = []
        results = []
        for name, step in steps:
            try:
                detail = step()
            except Exception as exc:  # noqa: BLE001
                failures.append(name)
                # Logged as well as reported: the log is what survives once
                # the cron mail has been read and deleted.
                logger.error("maintenance: %s failed: %s", name, exc)
                results.append((name, f"FAILED -- {exc}", True))
            else:
                results.append((name, detail, False))
                if verbose:
                    self.stdout.write(f"  {name}: {detail}")

        if failures:
            # Everything that could still be done has been done by this point.
            # Now say what happened -- including the steps that succeeded,
            # because "backup ok, email broken" is a different morning from
            # "everything broken".
            for name, detail, failed in results:
                line = f"  {name}: {detail}"
                self.stderr.write(self.style.ERROR(line) if failed else line)
            # Non-zero exit is what makes cron send the mail.
            raise SystemExit(
                "maintenance finished with problems: " + ", ".join(failures)
            )

        if verbose:
            self.stdout.write(self.style.SUCCESS("maintenance: all clear"))
