"""A content cache for the published, read-only endpoints.

The site is read-mostly: the salon edits copy in the admin occasionally and
visitors read it constantly. `/homepage/` alone rebuilds thirteen serializers
from their own queries on every request, and the answer is identical between
edits, so it is rebuilt for nothing nearly every time.

Invalidation is by version, not by expiry. A cached payload is stored under a
key carrying a version number, and saving anything the endpoints read bumps
that number (see `common.signals`), which strands every old key at once. That
matters more than the caching does: a timeout alone would mean an edit in the
admin does not reach the site until it lapses, and staff would reasonably call
that broken. Bumping means the next request after a save is already correct.

The keys also carry the request origin. Image URLs are absolute and built with
`request.build_absolute_uri`, so a payload made for one host is wrong for
another -- without the origin in the key, a request to 127.0.0.1 could be
served URLs pointing at localhost, or worse, at a staging host.
"""

import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)

#: Never expires on its own -- it is the anchor the payload keys hang off, and
#: losing it silently would strand every warm entry at once.
VERSION_KEY = "salon:content:version"


def content_version():
    """The current version, seeding it on first use."""
    version = cache.get(VERSION_KEY)
    if version is None:
        version = 1
        # `None` is "cache forever"; the payloads below carry the real timeout.
        cache.set(VERSION_KEY, version, None)
    return version


def bump_content_version():
    """Strand every cached payload, so the next request rebuilds.

    `incr` is atomic where the backend supports it, which matters when two
    admins save at once. It raises ValueError if the key has expired or was
    evicted, and the answer then is simply to start again -- a fresh version is
    just as good at stranding the old keys.
    """
    try:
        cache.incr(VERSION_KEY)
    except ValueError:
        cache.set(VERSION_KEY, 1, None)


def _origin(request):
    """Scheme and host, which is all `build_absolute_uri` varies on."""
    if request is None:
        return "-"
    return f"{request.scheme}://{request.get_host()}"


def cached_payload(name, request, build):
    """Return the payload for `name`, building it only on a miss.

    `build` is a zero-argument callable so nothing is computed on a hit.

    A failure to read or write the cache must never cost the response: this is
    an optimisation, and a site that 500s because Redis blinked is worse than a
    slow one. Both sides fall through to building the payload directly.
    """
    try:
        key = f"salon:content:{content_version()}:{name}:{_origin(request)}"
    except Exception:
        logger.exception("Content cache unreachable; serving %s uncached", name)
        return build()

    try:
        hit = cache.get(key)
        if hit is not None:
            return hit
    except Exception:
        logger.exception("Content cache read failed for %s; rebuilding", name)
        return build()

    payload = build()

    try:
        cache.set(key, payload)
    except Exception:
        logger.exception("Content cache write failed for %s", name)

    return payload
