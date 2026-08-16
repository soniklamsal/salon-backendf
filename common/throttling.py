"""Rate limits for the two authenticated read endpoints.

`ScopedRateThrottle` reads its scope from a `throttle_scope` attribute on the
view, which a function-based `@api_view` has no way to carry -- DRF's decorator
copies only a fixed set of attributes onto the class it builds. So the scope is
fixed on the throttle instead, which is the same thing DRF's own
`AnonRateThrottle` does.

Keyed by IP rather than by account. Neither endpoint requires a Django session
-- `my_bookings` identifies the caller by a verified Clerk claim and
`payment_screenshot` accepts a signed token -- so `request.user` is not the
thing to count, and an unauthenticated caller is exactly who these are for.

The rates are deliberately loose. They exist to stop somebody hammering an
endpoint for free, not to ration normal use: a customer with a dozen bookings
loads a dozen screenshots on one visit to /status, and refreshing a few times
must never lock them out of their own payment records. Several customers behind
one NAT share an IP here too, which is the case that would break first.
"""

from rest_framework.throttling import SimpleRateThrottle


class _IPRateThrottle(SimpleRateThrottle):
    """Counts per client IP, whatever the caller is authenticated as."""

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class MyBookingsThrottle(_IPRateThrottle):
    scope = "my-bookings"


class ScreenshotThrottle(_IPRateThrottle):
    """Higher than the list above it: /status fetches one image per booking, so
    a single page view costs as many requests as the customer has bookings."""

    scope = "screenshot"
