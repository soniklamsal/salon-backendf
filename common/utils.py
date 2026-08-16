"""Helpers shared by serializers and admin."""

from django.conf import settings


def resolve_image(instance, file_attr="image", url_attr="image_url", request=None):
    """Return one usable image URL for a model that carries both fields.

    Every image on the site is expressed as an upload *plus* an optional
    external URL, so content can either be managed here or point at a bucket
    that already holds it (the Classes cards still live on Cloudinary). An
    upload wins when present, because uploading one is the explicit act of
    replacing whatever the URL pointed at.

    Returns an absolute URL when a request is available, so the Next.js app —
    which fetches from a different origin — gets something it can put straight
    into <Image src>. Falls back to PUBLIC_BASE_URL, then to the site-relative
    path.
    """
    file = getattr(instance, file_attr, None) if file_attr else None
    if file:
        url = file.url
        # Cloudinary storage already returns an absolute https URL; only a
        # local `/media/...` path needs an origin bolted on.
        if url.startswith(("http://", "https://")):
            return url
        if request is not None:
            return request.build_absolute_uri(url)
        base = getattr(settings, "PUBLIC_BASE_URL", "")
        return f"{base}{url}" if base else url

    return (getattr(instance, url_attr, "") if url_attr else "") or ""
