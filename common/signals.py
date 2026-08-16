"""Cache invalidation for the published content endpoints.

Every model the read-only endpoints draw from bumps the content version when
it changes, so an edit in the admin is live on the next request rather than
whenever a timeout happens to lapse.

Membership is decided by app, with an explicit exception list, rather than by
naming each model. A new section model is added to `sections` every time the
site grows a band, and one that had to be remembered here would simply be
forgotten -- the failure being a stale site that nobody connects back to this
file. Opting the whole app in and naming the exclusions instead means the
default for anything new is correct.
"""

import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from common.cache import bump_content_version

logger = logging.getLogger(__name__)

#: `sections` and `core` are content in their entirety. `bookings` is not --
#: it also holds the things customers create, which are far and away the most
#: frequent writes on the site and appear on none of the cached endpoints.
#: Letting those through would flush the cache on every booking and leave it
#: cold exactly when the site is busiest.
CONTENT_APPS = {"sections", "core"}

#: The `bookings` models that *are* read by /booking-config/, /services/ and
#: /barbers/, so a staff edit to them still invalidates.
CONTENT_MODELS = {
    ("bookings", "bookingsection"),
    ("bookings", "barber"),
    ("bookings", "service"),
}


def _is_content(sender):
    meta = sender._meta
    return (
        meta.app_label in CONTENT_APPS
        or (meta.app_label, meta.model_name) in CONTENT_MODELS
    )


@receiver(post_save)
@receiver(post_delete)
def invalidate_content_cache(sender, **kwargs):
    # Fires for every model in the project, so it must stay cheap and must
    # never raise -- a failure here would otherwise break the save that
    # triggered it, turning a caching optimisation into lost admin edits.
    try:
        if _is_content(sender):
            bump_content_version()
    except Exception:
        logger.exception("Could not invalidate the content cache")
