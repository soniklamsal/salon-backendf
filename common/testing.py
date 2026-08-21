"""Test helpers and the test runner.

Not imported by anything that runs in production.
"""

import shutil
import tempfile

from django.test import override_settings
from django.test.runner import DiscoverRunner


class SalonTestRunner(DiscoverRunner):
    """Runs the suite against throwaway local storage, never Cloudinary.

    Two separate problems, and for a while only the first was solved.

    **Never the live account.** Once real Cloudinary credentials are in
    `.env`, the default storage is Cloudinary — and every test that saves a
    file would upload it to the live account, over the network, on the salon's
    quota. Tests would then fail on a plane and leave junk behind when they
    passed. So the run is pinned to local storage, and the Cloudinary paths are
    covered by tests that assert against a mocked client instead.

    **And never the project's own media folder.** Pinning storage was not
    enough on its own: `MEDIA_ROOT` still pointed at `backend/media/`, so a
    test that saved an upload wrote it into the working tree and left it
    there. That is exactly what happened — a run of the clip-upload tests left
    thirteen 18-byte `clip*.mp4` files sitting in `media/classes/video/`,
    indistinguishable at a glance from real content somebody had uploaded.

    So both media roots are redirected into a temporary directory that is
    deleted when the run ends. A test can now save whatever it likes.
    """

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)

        # One directory for the whole run rather than one per test: individual
        # tests that need isolation from each other already override
        # PRIVATE_MEDIA_ROOT themselves.
        self._media_dir = tempfile.mkdtemp(prefix="salon-test-media-")

        self._storage_override = override_settings(
            USE_CLOUDINARY=False,
            MEDIA_ROOT=self._media_dir,
            PRIVATE_MEDIA_ROOT=self._media_dir,
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
        # ignore_errors because a Windows antivirus scan can still hold a
        # handle open here, and failing the whole run over leftover temp files
        # would be worse than leaving them for the OS to clear.
        shutil.rmtree(self._media_dir, ignore_errors=True)
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
