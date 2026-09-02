"""Verify the session token the frontend mints for a Google-signed-in customer.

The browser and this API are on different origins (Next on Vercel, Django on
Render), so a session cookie is never attached to an API call. The frontend
therefore hands the browser a short-lived bearer token and this verifies it
before anything is stored, because the alternative -- believing a user id the
browser posted in a form field -- lets anyone claim to be anyone.

Why this token and not Google's own `id_token`
----------------------------------------------
Google's ID token is the wrong shape for the job: it expires one hour after
sign-in, while the site's session lasts weeks. Sending it straight through
would mean a customer who left a tab open over lunch silently stops being
recognised -- their booking saves anonymously and their status page empties.
Keeping it alive needs Google refresh-token rotation, and Google only issues a
refresh token on the *first* consent, so the repair path is itself unreliable.

Instead the frontend verifies Google once at sign-in, then mints its own token
per API call from the session it already holds (see `app/api/auth/backend-token`
in the frontend). That token is signed HS256 with a secret shared only between
the two servers. It carries the Google `sub` as its own `sub`, so the identity
is still Google's -- only the envelope is ours.

Configuration is `SALON_AUTH_SECRET`. With it unset, verification is *off*:
`verify_token` returns None and the caller records an anonymous booking. That is
deliberate -- the site has to keep working before the secret is added -- but it
means a booking is only attributed to an account once auth is really configured.
"""

from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

# The frontend mints these five minutes at a time. Allowing a little more than
# that here costs nothing and absorbs clock skew between two hosts we do not
# control the clocks of.
_LEEWAY_SECONDS = 30


def _secret() -> str:
    return getattr(settings, "SALON_AUTH_SECRET", "") or ""


def is_configured() -> bool:
    return bool(_secret())


def verify_token(token: str) -> dict | None:
    """Return the token's claims, or None if it is missing, bad, or unverifiable.

    Never raises: a failed verification means "treat this as a guest", not
    "return a 500 to someone trying to book a haircut".
    """
    secret = _secret()
    if not token or not secret:
        return None

    import jwt

    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            # Both are checked, and both raise on mismatch. `aud` is what stops
            # a token minted for some other service that happens to share the
            # secret being replayed at this one; `iss` names who may mint.
            audience=getattr(settings, "SALON_AUTH_AUDIENCE", "") or None,
            issuer=getattr(settings, "SALON_AUTH_ISSUER", "") or None,
            leeway=_LEEWAY_SECONDS,
            options={
                # `exp` is the whole point of a five-minute token, so a token
                # without one is not acceptable -- PyJWT does not require the
                # claim to be present unless told to.
                "require": ["exp", "sub"],
                "verify_exp": True,
                "verify_aud": bool(getattr(settings, "SALON_AUTH_AUDIENCE", "")),
                "verify_iss": bool(getattr(settings, "SALON_AUTH_ISSUER", "")),
            },
        )
    except Exception as exc:  # noqa: BLE001 - see docstring
        logger.warning("Session token rejected: %s", exc)
        return None

    if not claims.get("sub"):
        return None

    # The `sub` is Google's and is trusted; the email rides along for the
    # admin's benefit and is only trusted when Google says it is verified.
    # An unverified address must not be stamped on a booking as the customer's
    # own -- that is the claim someone would forge to receive another person's
    # confirmation mail.
    if not claims.get("email_verified"):
        claims.pop("email", None)

    return claims


def user_from_request(request) -> dict | None:
    """Claims for the signed-in customer on this request, or None."""
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if not header.lower().startswith("bearer "):
        return None
    return verify_token(header[7:].strip())
