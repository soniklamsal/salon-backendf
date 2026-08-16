"""The `azp` check on Clerk session tokens.

`azp` is the origin Clerk minted the token for. Verifying it is what stops a
token issued for some other site — a different Clerk app on the same instance,
or a developer's localhost build pointed at production — being replayed against
this API by anyone who gets hold of it.

The behaviour worth pinning down is the *default*: unconfigured means the check
does not run. Getting that wrong would not fail loudly, it would reject real
customers on every deployment that has not set the new variable yet.
"""

from django.test import SimpleTestCase, override_settings

from common.clerk import _authorized_parties, _authorized_party_ok


class AuthorizedPartiesTests(SimpleTestCase):
    @override_settings(CLERK_AUTHORIZED_PARTIES="")
    def test_unset_accepts_any_party(self):
        # The pre-existing posture. A deployment that upgrades without setting
        # the variable must keep working exactly as before.
        self.assertTrue(_authorized_party_ok({"azp": "https://anything.example"}))

    @override_settings(CLERK_AUTHORIZED_PARTIES="https://salon.example.com")
    def test_matching_party_accepted(self):
        self.assertTrue(_authorized_party_ok({"azp": "https://salon.example.com"}))

    @override_settings(CLERK_AUTHORIZED_PARTIES="https://salon.example.com")
    def test_foreign_party_rejected(self):
        self.assertFalse(_authorized_party_ok({"azp": "https://attacker.example"}))

    @override_settings(CLERK_AUTHORIZED_PARTIES="https://salon.example.com")
    def test_missing_claim_accepted(self):
        # Clerk omits `azp` under some token-template configurations. The
        # signature and issuer have already proved the token is Clerk's, so
        # refusing it here would break sign-in for a deployment doing nothing
        # wrong.
        self.assertTrue(_authorized_party_ok({}))
        self.assertTrue(_authorized_party_ok({"azp": ""}))

    @override_settings(
        CLERK_AUTHORIZED_PARTIES="https://salon.example.com, http://localhost:3000"
    )
    def test_several_parties_and_whitespace(self):
        self.assertTrue(_authorized_party_ok({"azp": "http://localhost:3000"}))
        self.assertTrue(_authorized_party_ok({"azp": "https://salon.example.com"}))
        self.assertEqual(
            _authorized_parties(),
            ["https://salon.example.com", "http://localhost:3000"],
        )

    @override_settings(CLERK_AUTHORIZED_PARTIES="https://salon.example.com/")
    def test_trailing_slash_does_not_decide_the_match(self):
        # Whether the origin is written with a trailing slash is a typo-level
        # detail, not an authorisation decision.
        self.assertTrue(_authorized_party_ok({"azp": "https://salon.example.com"}))
        self.assertTrue(_authorized_party_ok({"azp": "https://salon.example.com/"}))
