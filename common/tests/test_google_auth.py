"""What `common.google_auth.verify_token` will and will not believe.

Replaces the Clerk `azp` tests. The threat is the same one those covered — a
token minted somewhere else being replayed at this API — but the defence has
moved: Clerk tokens were checked by signature plus an `azp` origin claim, and
these are checked by a shared secret plus `iss` and `aud`.
"""

from __future__ import annotations

import time

import jwt
from django.test import SimpleTestCase, override_settings

from common import google_auth

# At least 32 bytes: PyJWT warns below that for HS256 (RFC 7518 s.3.2), and
# the real secret is a 32-byte random value from `openssl rand -base64 32`.
SECRET = "test-secret-not-a-real-one-0123456789abcdef"

SETTINGS = dict(
    SALON_AUTH_SECRET=SECRET,
    SALON_AUTH_ISSUER="salon-frontend",
    SALON_AUTH_AUDIENCE="salon-api",
)


def make_token(secret=SECRET, **overrides):
    now = int(time.time())
    claims = {
        "sub": "1078451",
        "email": "customer@example.com",
        "email_verified": True,
        "name": "A Customer",
        "iss": "salon-frontend",
        "aud": "salon-api",
        "iat": now,
        "exp": now + 300,
    }
    claims.update(overrides)
    for key in [k for k, v in claims.items() if v is None]:
        del claims[key]
    return jwt.encode(claims, secret, algorithm="HS256")


@override_settings(**SETTINGS)
class VerifyTokenTests(SimpleTestCase):
    def test_a_well_formed_token_is_accepted(self):
        claims = google_auth.verify_token(make_token())
        self.assertEqual(claims["sub"], "1078451")
        self.assertEqual(claims["email"], "customer@example.com")

    def test_a_token_signed_with_another_secret_is_refused(self):
        """The whole point. Anyone can mint a JWT; only we can sign one."""
        other = "another-secret-entirely-0123456789abcdef"
        self.assertIsNone(google_auth.verify_token(make_token(secret=other)))

    def test_an_expired_token_is_refused(self):
        now = int(time.time())
        stale = make_token(iat=now - 3600, exp=now - 1800)
        self.assertIsNone(google_auth.verify_token(stale))

    def test_a_token_with_no_expiry_is_refused(self):
        """A token that never expires is a password, and is not what we issue."""
        self.assertIsNone(google_auth.verify_token(make_token(exp=None)))

    def test_a_token_for_a_different_audience_is_refused(self):
        """Stops a token minted for some other service sharing this secret."""
        self.assertIsNone(google_auth.verify_token(make_token(aud="other-api")))

    def test_a_token_from_a_different_issuer_is_refused(self):
        self.assertIsNone(google_auth.verify_token(make_token(iss="somebody-else")))

    def test_a_token_with_no_subject_is_refused(self):
        self.assertIsNone(google_auth.verify_token(make_token(sub=None)))

    def test_an_unverified_email_is_dropped_but_the_identity_stands(self):
        """The `sub` is still trustworthy; the address is not.

        A booking stamped with an unverified address would send the
        confirmation somewhere the signer does not control -- which is exactly
        what someone would forge. The account is still recognised.
        """
        claims = google_auth.verify_token(make_token(email_verified=False))
        self.assertEqual(claims["sub"], "1078451")
        self.assertNotIn("email", claims)

    def test_a_missing_email_verified_claim_is_treated_as_unverified(self):
        claims = google_auth.verify_token(make_token(email_verified=None))
        self.assertNotIn("email", claims)

    def test_garbage_is_refused_rather_than_raising(self):
        """Never raises -- a bad token means "guest", not a 500."""
        for bad in ["", "   ", "not.a.jwt", "a.b.c", None]:
            self.assertIsNone(google_auth.verify_token(bad))

    def test_the_none_algorithm_is_refused(self):
        """`alg: none` is the classic JWT forgery; PyJWT must not accept it."""
        forged = jwt.encode(
            {"sub": "attacker", "iss": "salon-frontend", "aud": "salon-api",
             "exp": int(time.time()) + 300},
            key="",
            algorithm="none",
        )
        self.assertIsNone(google_auth.verify_token(forged))


class NotConfiguredTests(SimpleTestCase):
    @override_settings(SALON_AUTH_SECRET="")
    def test_with_no_secret_verification_is_off(self):
        """Unconfigured means "no account", not "error".

        This is what lets the site run before the secret is set: bookings are
        recorded anonymously rather than every request failing.
        """
        self.assertFalse(google_auth.is_configured())
        self.assertIsNone(google_auth.verify_token(make_token()))

    @override_settings(**SETTINGS)
    def test_with_a_secret_it_reports_configured(self):
        self.assertTrue(google_auth.is_configured())


@override_settings(**SETTINGS)
class UserFromRequestTests(SimpleTestCase):
    class FakeRequest:
        def __init__(self, header):
            self.META = {"HTTP_AUTHORIZATION": header} if header else {}

    def test_it_reads_a_bearer_header(self):
        request = self.FakeRequest(f"Bearer {make_token()}")
        self.assertEqual(google_auth.user_from_request(request)["sub"], "1078451")

    def test_the_scheme_is_matched_case_insensitively(self):
        request = self.FakeRequest(f"bearer {make_token()}")
        self.assertIsNotNone(google_auth.user_from_request(request))

    def test_another_scheme_is_ignored(self):
        request = self.FakeRequest(f"Basic {make_token()}")
        self.assertIsNone(google_auth.user_from_request(request))

    def test_no_header_at_all(self):
        self.assertIsNone(google_auth.user_from_request(self.FakeRequest(None)))
