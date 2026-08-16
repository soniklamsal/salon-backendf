"""Move payment screenshots out of the world-readable media folder.

Screenshots uploaded before `payment_screenshot` moved to private storage are
still sitting in MEDIA_ROOT, which the web server hands to anyone who asks for
the path. The database column already points at the right relative name — only
the bytes are in the wrong place — so this is a file move, not a data
migration, and it is why it lives here rather than in `migrations/`.

Safe to run more than once: a file already moved is skipped.

    python manage.py secure_screenshots --dry-run
    python manage.py secure_screenshots
"""

import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from bookings.models import Appointment


class Command(BaseCommand):
    help = "Move existing payment screenshots from media/ into private storage."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would move without touching anything.",
        )
        parser.add_argument(
            "--keep-original",
            action="store_true",
            help=(
                "Copy instead of move. Leaves the public copy in place, which "
                "is the exposure this command exists to close — for testing."
            ),
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        keep = options["keep_original"]

        public_root = Path(settings.MEDIA_ROOT)
        private_root = Path(settings.PRIVATE_MEDIA_ROOT)

        moved = skipped = missing = 0

        for booking in Appointment.objects.exclude(payment_screenshot=""):
            name = booking.payment_screenshot.name
            source = public_root / name
            target = private_root / name

            if target.exists():
                skipped += 1
                continue

            if not source.exists():
                # Either already moved and cleaned up, or uploaded straight to
                # Cloudinary. Neither is a problem; both are worth reporting.
                missing += 1
                self.stdout.write(f"  ?  {booking.reference}: no local file at {name}")
                continue

            self.stdout.write(f"  ->  {booking.reference}: {name}")
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                if keep:
                    shutil.copy2(source, target)
                else:
                    shutil.move(str(source), str(target))
            moved += 1

        verb = "would move" if dry_run else "moved"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} {moved}, already private {skipped}, no local file {missing}"
            )
        )
        if moved and not dry_run and keep:
            self.stdout.write(
                self.style.WARNING(
                    "--keep-original left the public copies in place; they are "
                    "still readable by anyone with the URL."
                )
            )
