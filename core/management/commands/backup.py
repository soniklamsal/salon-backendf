"""Take a backup of the database and the private files.

    python manage.py backup
    python manage.py backup --output-dir /var/backups/salon --keep 14

Two things need backing up and only one of them is the database:

* the database — all the page content, every booking, every enquiry;
* `private-media/` — the payment screenshots, which are the *evidence* behind
  each approved booking and exist nowhere else. Public images are either in
  Cloudinary or reproducible by `seed_content`; these are not.

Deliberately not clever. It writes a plain `dumpdata` JSON and a zip of the
private files, both timestamped, and prunes old ones. That runs anywhere Django
runs, needs no `pg_dump` on the path, and restores with `loaddata`.

For a large Postgres database, `pg_dump` is the better tool and this is not
trying to replace it — but a backup that runs is worth more than a better one
that was never set up.
"""

import shutil
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

# Rebuilt from scratch on restore, and large. Sessions especially: keeping them
# would restore other people's logins along with the data.
EXCLUDED = ["contenttypes", "auth.permission", "sessions", "admin.logentry"]


class Command(BaseCommand):
    help = "Dump the database and archive private media into a timestamped backup."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            default=str(Path(settings.BASE_DIR) / "backups"),
            help="Where to write. Should be somewhere the app cannot serve.",
        )
        parser.add_argument(
            "--keep",
            type=int,
            default=7,
            help="How many backups to retain. 0 keeps everything.",
        )
        parser.add_argument(
            "--skip-media",
            action="store_true",
            help="Database only. The screenshots are usually the point.",
        )

    def handle(self, *args, **options):
        out_dir = Path(options["output_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        data_path = out_dir / f"db-{stamp}.json"

        self.stdout.write(f"Database -> {data_path}")
        with data_path.open("w", encoding="utf-8") as handle:
            call_command(
                "dumpdata",
                exclude=EXCLUDED,
                natural_foreign=True,
                natural_primary=True,
                indent=2,
                stdout=handle,
            )

        if not options["skip_media"]:
            private_root = Path(settings.PRIVATE_MEDIA_ROOT)
            if private_root.exists() and any(private_root.iterdir()):
                archive = out_dir / f"private-media-{stamp}"
                self.stdout.write(f"Private media -> {archive}.zip")
                shutil.make_archive(str(archive), "zip", root_dir=private_root)
            else:
                # Normal when Cloudinary holds them, or before the first
                # booking. Said out loud so it is not mistaken for success.
                self.stdout.write("Private media -> nothing stored locally")

        removed = self._prune(out_dir, options["keep"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Backup {stamp} written to {out_dir}"
                + (f" ({removed} old backup(s) removed)" if removed else "")
            )
        )
        self.stdout.write(
            "Restore with: manage.py migrate && manage.py loaddata "
            f"{data_path.name}"
        )

    def _prune(self, out_dir: Path, keep: int) -> int:
        if keep <= 0:
            return 0

        removed = 0
        # Grouped by prefix so pruning six database dumps does not also delete
        # a media archive that has no dump of its own.
        for prefix in ("db-", "private-media-"):
            files = sorted(
                (p for p in out_dir.iterdir() if p.name.startswith(prefix)),
                reverse=True,
            )
            for stale in files[keep:]:
                stale.unlink()
                removed += 1
        return removed
