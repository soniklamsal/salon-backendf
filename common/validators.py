"""Upload validation.

The booking endpoint takes a file from anyone, with no account and no session.
Django's `ImageField` already proves the bytes are a decodable image, which
stops a renamed `.exe`, but it says nothing about size — and "is it an image"
is the cheap question. A 900-byte PNG can declare itself 64000x64000 and cost
gigabytes of RAM the moment anything opens it.
"""

import re

from django.conf import settings
from django.core.exceptions import ValidationError

# Deliberately permissive. The salon is in Kathmandu but takes bookings from
# people abroad, and a phone field that rejects a real customer's real number
# costs a booking — which is a worse outcome than storing a slightly odd
# string. This catches a typo and a pasted sentence, nothing more.
_PHONE_CHARS = re.compile(r"^[0-9+\-().\s]+$")


def validate_phone(value):
    """Reject anything that is obviously not a phone number."""
    if not value:
        return

    if not _PHONE_CHARS.match(value):
        raise ValidationError(
            "A phone number can only contain digits and + - ( ) . and spaces."
        )

    digits = re.sub(r"\D", "", value)
    if not 7 <= len(digits) <= 15:
        # 15 is the E.164 maximum; 7 is shorter than any national number in
        # use, so both ends are a typo rather than a valid edge case.
        raise ValidationError("That does not look like a complete phone number.")


def validate_upload(file):
    """Reject files that are too large on disk or too large decompressed."""
    max_bytes = getattr(settings, "MAX_UPLOAD_BYTES", 8 * 1024 * 1024)
    size = getattr(file, "size", None)
    if size is not None and size > max_bytes:
        raise ValidationError(
            "That file is %(actual)s MB. The limit is %(limit)s MB.",
            params={
                "actual": f"{size / 1024 / 1024:.1f}",
                "limit": max_bytes // 1024 // 1024,
            },
        )

    # Pillow reads only the header here, so this stays cheap. `image` is set by
    # Django's ImageField during its own validation; when it is absent the
    # field has not run yet and there is nothing to check.
    image = getattr(file, "image", None)
    if image is not None:
        max_pixels = getattr(settings, "MAX_UPLOAD_PIXELS", 50_000_000)
        width, height = image.size
        if width * height > max_pixels:
            raise ValidationError(
                "That image is %(w)sx%(h)s, which is too large to process.",
                params={"w": width, "h": height},
            )


# Cloudinary's own validate_video needs python-magic, which needs libmagic --
# not present here and unlikely on shared cPanel hosting. An extension check
# needs no dependency and catches the realistic mistake, which is picking the
# wrong file rather than disguising one.
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".m4v", ".ogv", ".avi", ".mkv"}


def validate_video_upload(file):
    """Reject anything that is obviously not a video, by extension."""
    import os

    from django.core.exceptions import ValidationError

    extension = os.path.splitext(file.name)[1].lower()
    if extension not in VIDEO_EXTENSIONS:
        raise ValidationError(
            f"{extension or 'That file'} is not a video. Use one of: "
            + ", ".join(sorted(VIDEO_EXTENSIONS))
            + "."
        )
