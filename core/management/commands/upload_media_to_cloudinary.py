"""Move files already on local disk into Cloudinary.

    python manage.py upload_media_to_cloudinary --dry-run
    python manage.py upload_media_to_cloudinary

Switching Cloudinary on changes where the storage *looks*, not where the files
are. Everything uploaded before the switch is still on local disk, and every
row pointing at one of those files goes from "an image" to "a broken image" the
moment the credentials are added. This carries them across.

Each file is re-saved through its own field's storage, so a public image goes
to a public Cloudinary URL and a payment screenshot goes there as
`type=authenticated` — the field decides, not this command. Cloudinary returns
the public id it actually stored under and the database column is updated to
match, rather than assuming a naming rule.

Safe to re-run: a field whose file is no longer on local disk has already been
moved, and is skipped. The local copy is left alone so this is reversible —
delete `media/` yourself once the site is confirmed working.
"""

from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import models


class Command(BaseCommand):
    help = "Upload existing local media files to Cloudinary and repoint the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List what would move without uploading anything.",
        )

    def handle(self, *args, **options):
        if not getattr(settings, "USE_CLOUDINARY", False):
            raise CommandError(
                "Cloudinary is not configured — set CLOUDINARY_CLOUD_NAME, "
                "CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET in .env first. "
                "Without them the storage is the local disk and there is "
                "nothing to move to."
            )

        dry_run = options["dry_run"]
        moved = skipped = missing = failed = 0

        for model in apps.get_models():
            # A proxy shares its table with the concrete model, so walking both
            # would upload every file twice and leave a duplicate on Cloudinary.
            # `bookings.Service` proxies `sections.Service` for the admin menu.
            if model._meta.proxy:
                continue

            file_fields = [
                f
                for f in model._meta.get_fields()
                if isinstance(f, models.FileField)
            ]
            if not file_fields:
                continue

            for instance in model._default_manager.all().iterator():
                for field in file_fields:
                    file = getattr(instance, field.name)
                    if not file:
                        continue

                    source = self._local_path(field, file.name)
                    if source is None or not source.exists():
                        # Already on Cloudinary, or the row points at a file
                        # that was never there. Either way, nothing to move.
                        missing += 1
                        continue

                    label = f"{model._meta.label}.{field.name} #{instance.pk}"
                    self.stdout.write(f"  ->  {label}: {file.name}")

                    if dry_run:
                        moved += 1
                        continue

                    try:
                        with source.open("rb") as handle:
                            # Through the field's own storage, so a private
                            # field stays private.
                            new_name = file.storage.save(
                                file.name, File(handle, name=source.name)
                            )
                    except Exception as exc:  # noqa: BLE001 - reported, not raised
                        failed += 1
                        self.stderr.write(
                            self.style.ERROR(f"      failed: {type(exc).__name__}: {exc}")
                        )
                        continue

                    if new_name != file.name:
                        # Cloudinary decides the public id; trust it over any
                        # guess about how the name maps.
                        setattr(instance, field.name, new_name)
                        instance.save(update_fields=[field.name])
                    moved += 1

        verb = "would upload" if dry_run else "uploaded"
        summary = f"{verb} {moved}, no local file {missing}"
        if skipped:
            summary += f", skipped {skipped}"
        if failed:
            summary += f", FAILED {failed}"

        style = self.style.ERROR if failed else self.style.SUCCESS
        self.stdout.write(style(summary))

        if moved and not dry_run and not failed:
            self.stdout.write(
                "Local copies were left in place. Check the site renders, then "
                "delete media/ and private-media/ yourself."
            )

    def _local_path(self, field, name: str) -> Path | None:
        """Where this file would be on disk, given which storage it uses.

        Private fields were rooted at PRIVATE_MEDIA_ROOT and public ones at
        MEDIA_ROOT, so the two cannot share one guess.
        """
        from common.storage import PrivateMediaStorage

        if isinstance(field.storage, PrivateMediaStorage):
            root = Path(settings.PRIVATE_MEDIA_ROOT)
        else:
            root = Path(settings.MEDIA_ROOT)
        return root / name
