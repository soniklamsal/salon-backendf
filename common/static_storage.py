"""Static files storage that hashes for cache-busting but does not 500 the
whole page over a single unresolved reference.

Why this exists
---------------
The admin theme (django-jazzmin) renders, in `admin/base.html`:

    data-theme-base="{% static 'vendor/bootswatch' %}"

`vendor/bootswatch` is a *directory*, not a file. A hashed-files manifest only
lists files, so under the strict `ManifestStaticFilesStorage` that `{% static %}`
call raises `ValueError: Missing staticfiles manifest entry for 'vendor/bootswatch'`
-- and because it is in the base template, every admin page 500s.

It never showed up before deploy for two reasons: `DEBUG=True` skips the
manifest lookup entirely, and the test suite runs with no collected manifest,
so the lookup is a no-op there too. It only appears with `DEBUG=False` and a
real `collectstatic` behind it -- i.e. only in production.

`manifest_strict = False` is Django's built-in answer: a name the manifest does
not know falls back to its un-hashed path (here `/static/vendor/bootswatch`,
which is only used as a base string by the theme JS) instead of raising. Every
real file is still served under its hashed name, so cache-busting is untouched.
"""

from whitenoise.storage import CompressedManifestStaticFilesStorage


class ForgivingManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """Compressed, hashed, WhiteNoise-served -- but tolerant of a name the
    manifest has no entry for, rather than raising and taking the page down."""

    manifest_strict = False
