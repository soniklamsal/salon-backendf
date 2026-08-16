"""Abstract bases shared by the content apps.

`common` is intentionally not in INSTALLED_APPS — every model here is abstract,
so it owns no tables and needs no app registry entry.
"""

from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SingletonModel(TimeStampedModel):
    """A section that exists exactly once on the page.

    Every `save()` collapses onto pk=1, so no amount of clicking "Add" in the
    admin can produce a second Hero. The admin classes in `common.admin` go
    further and route the changelist straight to that one row.
    """

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """Return the stored row, or an unsaved instance carrying the defaults.

        Deliberately does not create anything: this runs on the read path for
        every API request, and a GET should not write. An empty database
        therefore still serves a complete payload built from field defaults —
        which are the copy the page shipped with.
        """
        return cls.objects.first() or cls()


class OrderedModel(models.Model):
    """A repeated item whose position on the page is editable."""

    order = models.PositiveIntegerField(
        default=0,
        db_index=True,
        help_text="Lower numbers come first on the page.",
    )
    is_published = models.BooleanField(
        default=True,
        help_text="Unpublished items stay in the admin but vanish from the site.",
    )

    class Meta:
        abstract = True
        ordering = ["order", "pk"]


class PublishedManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_published=True)
