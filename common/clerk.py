"""Verify a Clerk session token server-side.

The booking form sends Clerk's session JWT as `Authorization: Bearer <token>`.
This checks the signature against Clerk's published keys (JWKS) before anything
is stored, because the alternative — believing a `userId` the browser posted in
a form field — lets anyone claim to be anyone.

Configuration comes from `CLERK_JWKS_URL` (or `CLERK_ISSUER`, from which the
JWKS URL is derived). With neither set, verification is *off*: `verify_token`
returns None and the caller records an anonymous booking. That is deliberate —
the site has to keep working before the keys are added — but it means a booking
is only attributed to an account once Clerk is actually configured.
"""

from __future__ import annotations

import logging
import threading
import time

from django.conf import settings

logger = logging.getLogger(__name__)

# Clerk rotates signing keys. Cached so the common case is not an HTTP round
# trip per booking, refreshed when a token names a key we have not seen.
_JWKS_TTL_SECONDS = 3600
_jwks_cache: dict[str, object] = {"fetched_at": 0.0, "client": None}
_lock = threading.Lock()


def _jwks_url() -> str:
    url = getattr(settings, "CLERK_JWKS_URL", "") or ""
    if url:
        return url
    issuer = (getattr(settings, "CLERK_ISSUER", "") or "").rstrip("/")
    return f"{issuer}/.well-known/jwks.json" if issuer else ""


def is_configured() -> bool:
    return bool(_jwks_url())


def _get_client(force_refresh: bool = False):
    """Returns a PyJWKClient, or None when Clerk is not configured."""
    url = _jwks_url()
    if not url:
        return None

    from jwt import PyJWKClient

    with _lock:
        fresh = time.time() - float(_jwks_cache["fetched_at"]) < _JWKS_TTL_SECONDS
        if _jwks_cache["client"] is not None and fresh and not force_refresh:
            return _jwks_cache["client"]

        client = PyJWKClient(url, cache_keys=True)
        _jwks_cache["client"] = client
        _jwks_cache["fetched_at"] = time.time()
        return client


def _authorized_parties() -> list[str]:
    """Origins allowed to mint the session tokens this backend accepts.

    Comma-separated in `CLERK_AUTHORIZED_PARTIES`, e.g.
    `https://salon.example.com,http://localhost:3000`.

    Empty by default, which switches the check off. That is the same posture the
    rest of Clerk support here takes -- unconfigured means "do not enforce",
    so an existing deployment does not start rejecting its own customers the
    moment this ships. Set it in production, where it is worth having.
    """
    raw = getattr(settings, "CLERK_AUTHORIZED_PARTIES", "") or ""
    return [party.strip().rstrip("/") for party in raw.split(",") if party.strip()]


def _authorized_party_ok(claims: dict) -> bool:
    """Whether `azp` names an origin we accept.

    Clerk's session tokens carry `azp` -- the origin the token was minted for --
    and verifying it is what stops a token issued for some other site being
    replayed against this API. `aud` is not used for this: Clerk does not set it
    on session tokens, which is why `verify_aud` stays off above.

    A token with no `azp` at all is accepted. Clerk omits the claim in some
    template configurations, and refusing those would break sign-in for a
    deployment that has done nothing wrong -- the signature and issuer checks
    have already established the token is genuinely Clerk's.
    """
    allowed = _authorized_parties()
    if not allowed:
        return True

    azp = (claims.get("azp") or "").rstrip("/")
    if not azp:
        return True

    return azp in allowed


def verify_token(token: str) -> dict | None:
    """Return the token's claims, or None if it is missing, bad, or unverifiable.

    Never raises: a failed verification means "treat this as a guest", not
    "return a 500 to someone trying to book a haircut".
    """
    if not token or not is_configured():
        return None

    import jwt

    for attempt in (False, True):  # retry once with fresh keys after rotation
        client = _get_client(force_refresh=attempt)
        if client is None:
            return None
        try:
            signing_key = client.get_signing_key_from_jwt(token)
            options = {"verify_aud": False}
            issuer = (getattr(settings, "CLERK_ISSUER", "") or "").rstrip("/")
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=issuer or None,
                options=options,
                leeway=10,  # small clock skew between this box and Clerk
            )
            if not _authorized_party_ok(claims):
                logger.warning(
                    "Clerk token rejected: azp %r is not an authorized party",
                    claims.get("azp"),
                )
                return None
            return claims
        except Exception as exc:  # noqa: BLE001 - see docstring
            if attempt:
                logger.warning("Clerk token rejected: %s", exc)
                return None
    return None


def user_from_request(request) -> dict | None:
    """Claims for the signed-in Clerk user on this request, or None."""
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if not header.lower().startswith("bearer "):
        return None
    return verify_token(header[7:].strip())
