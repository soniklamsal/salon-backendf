"""Test helpers and the test runner.

Not imported by anything that runs in production.
"""

from django.test import override_settings
from django.test.runner import DiscoverRunner


class SalonTestRunner(DiscoverRunner):
    """Runs the suite against local storage, never Cloudinary.

    Once real Cloudinary credentials are in `.env`, the default storage is
    Cloudinary — and every test that saves a file would upload it to the live
    account, over the network, on the salon's quota. Tests would then fail on a
    plane and leave junk behind when they passed.

    So the run is pinned to local storage. The Cloudinary paths are covered
    separately by tests that assert against a mocked client rather than by
    talking to the real one.
    """

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)

        self._storage_override = override_settings(
            USE_CLOUDINARY=False,
            STORAGES={
                "default": {
                    "BACKEND": "django.core.files.storage.FileSystemStorage"
                },
                "staticfiles": {
                    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
                },
            },
        )
        self._storage_override.enable()

    def teardown_test_environment(self, **kwargs):
        self._storage_override.disable()
        super().teardown_test_environment(**kwargs)

# Production serves static files through WhiteNoise's manifest storage, which
# refuses to resolve a file that `collectstatic` has not hashed — a deliberate
# fail-loud, since a missing asset in production is a broken page. Under test
# nothing has been collected, so every admin page would 500 on Jazzmin's CSS.
#
# Applied to test cases that render admin templates, rather than weakened in
# settings.py, so the production behaviour stays exactly as deployed.
admin_static_storage = override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
