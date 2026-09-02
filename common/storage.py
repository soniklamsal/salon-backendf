"""Storage for files that must not be world-readable.

Everything else on this site is page content — hero art, service photos, barber
headshots — and belongs on a public CDN URL. Payment screenshots are not that.
They are financial records showing a customer's name and an eSewa transfer, and
before this existed they sat in MEDIA_ROOT, which the web server hands to
anyone who asks for the path.

Two backends, one contract:

* Cloudinary configured -> uploaded as `type=authenticated`. Cloudinary refuses
  to deliver those over a plain URL; only a URL signed with the API secret
  works, and the secret never leaves the server.
* Otherwise -> the local filesystem, rooted at PRIVATE_MEDIA_ROOT, which is
  deliberately outside MEDIA_ROOT so that neither WhiteNoise nor the
  `static()` helper in config/urls.py will serve it.

In both cases `url()` returns a path to the authorising view in `api.views`
rather than a directly fetchable location. The view checks who is asking and
only then produces the real bytes. That way the access rule lives in one place
and does not depend on which storage happens to be active.
"""

import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.signals import setting_changed
from django.dispatch import receiver
from django.utils.functional import LazyObject, empty


class PrivateFileSystemStorage(FileSystemStorage):
    """Local fallback. Writes outside MEDIA_ROOT, and refuses to build a URL.

    `url()` raising is deliberate: a private file has no unauthenticated URL,
    and returning something plausible would let a caller leak one by accident.
    The view streams these files instead.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("base_url", None)
        super().__init__(**kwargs)

    # Read from settings on every access rather than captured in __init__.
    # FileSystemStorage caches `location` as a cached_property and only
    # invalidates it for MEDIA_ROOT, so a storage built once at import time
    # would ignore PRIVATE_MEDIA_ROOT changing — which silently sent every
    # test's uploads into the real project folder instead of its temp dir.
    @property
    def base_location(self):
        return settings.PRIVATE_MEDIA_ROOT

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    def url(self, name):
        raise NotImplementedError(
            "Private files have no public URL. Use common.storage.signed_url()."
        )


def _cloudinary_storage_class():
    from cloudinary_storage.storage import MediaCloudinaryStorage

    class PrivateCloudinaryStorage(MediaCloudinaryStorage):
        """Uploads with `type=authenticated` so plain URLs are refused."""

        def _upload(self, name, content):
            import os

            import cloudinary.uploader

            options = {
                "use_filename": True,
                "resource_type": self._get_resource_type(name),
                "tags": self.TAG,
                "type": "authenticated",
            }
            folder = os.path.dirname(name)
            if folder:
                options["folder"] = folder
            return cloudinary.uploader.upload(content, **options)

        def delete(self, name):
            import cloudinary.uploader

            response = cloudinary.uploader.destroy(
                name,
                invalidate=True,
                type="authenticated",
                resource_type=self._get_resource_type(name),
            )
            return response["result"] == "ok"

        def url(self, name):
            raise NotImplementedError(
                "Private files have no public URL. Use common.storage.signed_url()."
            )

    return PrivateCloudinaryStorage


class PrivateMediaStorage(LazyObject):
    """Picks the backend at first use, not at import time.

    Lazy because Django imports models before settings are fully resolved in
    some entry points, and because the choice depends on whether Cloudinary
    credentials happen to be present.
    """

    def _setup(self):
        if getattr(settings, "USE_CLOUDINARY", False):
            self._wrapped = _cloudinary_storage_class()()
        else:
            self._wrapped = PrivateFileSystemStorage()


private_media_storage = PrivateMediaStorage()


@receiver(setting_changed)
def _reset_private_storage(*, setting, **kwargs):
    """Re-resolve the backend when the settings it depends on change.

    A LazyObject resolves once and keeps the answer, so without this an
    `override_settings(USE_CLOUDINARY=False)` in a test would be ignored and
    the test would upload to the real Cloudinary account. Django does exactly
    this for its own `default_storage`.
    """
    if setting in {"USE_CLOUDINARY", "CLOUDINARY_STORAGE", "STORAGES"}:
        private_media_storage._wrapped = empty


def private_storage():
    """Callable form, for `FileField(storage=...)`.

    A callable keeps the choice out of the migration: Django records the
    reference to this function, so switching Cloudinary on or off later does
    not require a schema migration.
    """
    return private_media_storage


def screenshot_token(reference: str) -> str:
    """A short-lived capability token for one booking's screenshot.

    Needed because a browser will not attach an `Authorization` header to an
    `<img src>`. The customer's session token proves who they are when the
    booking list is fetched; this carries that decision into the image request
    that follows, without putting the session token in a URL.

    Signed with SECRET_KEY and bound to a single reference, so it cannot be
    edited into a token for somebody else's booking, and it expires. It is a
    capability — whoever holds it can view that one image until it does — which
    is the same trade every signed download URL makes, and the reason the
    lifetime is short.
    """
    from django.core import signing

    return signing.dumps({"ref": reference}, salt=_SCREENSHOT_SALT)


def reference_from_token(token: str, max_age: int = 3600) -> str:
    """The reference a token authorises, or "" if it is bad or expired."""
    from django.core import signing

    try:
        payload = signing.loads(token, salt=_SCREENSHOT_SALT, max_age=max_age)
    except signing.BadSignature:
        return ""
    return payload.get("ref", "") if isinstance(payload, dict) else ""


_SCREENSHOT_SALT = "bookings.payment_screenshot"


def signed_url(name: str, expires_in: int = 300) -> str:
    """A time-limited Cloudinary URL for a private file, or "" locally.

    Only used when Cloudinary is active. The local backend has no equivalent —
    the view streams those bytes itself instead of redirecting.
    """
    if not name or not getattr(settings, "USE_CLOUDINARY", False):
        return ""

    import time

    import cloudinary.utils

    url, _ = cloudinary.utils.cloudinary_url(
        name,
        type="authenticated",
        resource_type="image",
        sign_url=True,
        # Cloudinary enforces this server-side; a copied link stops working
        # once it passes, which matters for something a customer might paste
        # into a chat window.
        auth_token={
            "key": settings.CLOUDINARY_AUTH_TOKEN_KEY,
            "duration": expires_in,
            "start_time": int(time.time()),
        }
        if getattr(settings, "CLOUDINARY_AUTH_TOKEN_KEY", "")
        else None,
    )
    return url


# --- Video -----------------------------------------------------------------
# Cloudinary treats video as a different resource type from images: uploading a
# clip through the image endpoint is rejected, and the delivery URL is built
# under /video/upload/ rather than /image/upload/. The project's default
# storage is the image one, so a FileField holding video has to say so.


class VideoMediaStorage(LazyObject):
    """Cloudinary's video backend when configured, local disk otherwise.

    Lazy for the same reasons as PrivateMediaStorage above: the choice depends
    on whether credentials are present, and models are imported before that is
    settled in some entry points.
    """

    def _setup(self):
        if getattr(settings, "USE_CLOUDINARY", False):
            from cloudinary_storage.storage import VideoMediaCloudinaryStorage

            self._wrapped = VideoMediaCloudinaryStorage()
        else:
            self._wrapped = FileSystemStorage()


video_media_storage = VideoMediaStorage()


@receiver(setting_changed)
def _reset_video_storage(*, setting, **kwargs):
    """Re-resolve when the settings it depends on change. See above."""
    if setting in {"USE_CLOUDINARY", "CLOUDINARY_STORAGE", "STORAGES"}:
        video_media_storage._wrapped = empty


def video_storage():
    """Callable form, for `FileField(storage=...)`.

    A callable keeps the choice out of the migration, so turning Cloudinary on
    or off later needs no schema change.
    """
    return video_media_storage
