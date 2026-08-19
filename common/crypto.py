"""Encryption for the few secrets that have to live in the database.

The SMTP password is one. It is entered in the admin, so it cannot live in
`.env` with the others, and it is a working credential for a real Gmail
account -- one that can send mail as the salon to anybody.

What this protects against, precisely: a copy of the database. `manage.py
backup` writes `dumpdata` JSON, MySQL dumps get emailed around, and a hosting
panel will show you any table you ask for. In all of those the password would
otherwise be sitting in plain text.

What it does NOT protect against: somebody who has the database *and*
`DJANGO_SECRET_KEY`, because the key is derived from it. That is a real limit
and worth stating plainly rather than implying more. The two live in different
places -- one in the database, one in `.env` -- and separating them is the
entire benefit. Do not treat this as a reason to relax how either is handled.

Consequence worth knowing before it bites: rotating DJANGO_SECRET_KEY makes an
already-stored password undecryptable. Nothing crashes -- it reads back as
empty and mail stops sending until it is re-entered in the admin.
"""

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

logger = logging.getLogger("common")

# Marks a value as encrypted by this module. Without it there is no way to tell
# ciphertext from a plaintext password typed in before this existed, and the
# migration path for such a row is "read it as it is, re-encrypt on next save".
PREFIX = "enc:v1:"


def _fernet() -> Fernet:
    """A Fernet key derived from DJANGO_SECRET_KEY.

    Salted with a purpose string so this key is not the same one any other
    SECRET_KEY-derived helper would produce -- signing, sessions, password
    reset tokens. Reusing key material across purposes is how a weakness in
    one becomes a weakness in all of them.
    """
    digest = hashlib.sha256(f"salon.smtp.v1:{settings.SECRET_KEY}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str) -> str:
    """Ciphertext for `value`, or "" for an empty one.

    An empty password is a real state -- it means "not configured yet" -- and
    encrypting it would turn that into an opaque blob that reads as set.
    """
    if not value:
        return ""
    return PREFIX + _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    """Plaintext for `value`. Never raises.

    A value without the prefix is returned unchanged: it predates this module,
    and refusing to read it would lock the admin out of a password they can
    see in the database anyway.
    """
    if not value:
        return ""
    if not value.startswith(PREFIX):
        return value
    try:
        return _fernet().decrypt(value[len(PREFIX) :].encode()).decode()
    except (InvalidToken, ValueError):
        # Almost always a rotated SECRET_KEY. Loud in the log, empty to the
        # caller -- which surfaces as "mail stopped sending", not as a 500 on
        # whatever page happened to load the settings row.
        logger.error(
            "Could not decrypt a stored secret. If DJANGO_SECRET_KEY was "
            "changed, re-enter the SMTP password in the admin."
        )
        return ""
