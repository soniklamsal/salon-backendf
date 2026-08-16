"""Site-wide content: the things that are not any one band of the page.

Field defaults throughout these apps are the copy the site currently ships
with. That is not decoration — `SingletonModel.load()` falls back to an unsaved
instance, so an empty database still serves the exact page that exists today.
"""

from django.db import models

from common.models import OrderedModel, SingletonModel


class SiteSettings(SingletonModel):
    brand_name = models.CharField(
        max_length=60,
        default="SALON",
        help_text="The wordmark in the header, the mobile menu and the badge.",
    )
    badge_caption = models.CharField(
        max_length=120,
        default="We Don't Keep Our Beauty Secrets",
        help_text="Set around the circular badge in Follow Us and the footer.",
    )

    meta_title = models.CharField(
        max_length=200,
        default="Salon — Always Make Room for a Little Beauty in Your Life",
        help_text="Browser tab title and the default social-share title.",
    )
    meta_description = models.TextField(
        default=(
            "Premium hair, beauty and spa treatments in Kathmandu, Nepal. Book "
            "an appointment or browse the service menu."
        )
    )

    nav_cta_label = models.CharField(max_length=60, default="Book Now")
    nav_cta_href = models.CharField(max_length=200, default="/services")

    copyright_text = models.CharField(
        max_length=200, default="2026 Salon All rights reserved"
    )

    # The eSewa QR and its note used to live here. They moved to
    # `bookings.BookingSection`, which is the form they appear on — see
    # bookings/migrations for the data migration that carried them across.

    class Meta:
        verbose_name = "Site settings"
        verbose_name_plural = "Site settings"

    def __str__(self):
        return "Site settings"


class NavLink(OrderedModel):
    """One entry in the primary nav. Header and footer draw from this one list.

    The footer currently shows the same four links as the header, so a single
    model with two visibility flags keeps them in step by default while still
    allowing them to diverge.
    """

    label = models.CharField(max_length=60)
    href = models.CharField(
        max_length=200,
        help_text="Site-relative path, e.g. /about-us — or a full external URL.",
    )
    show_in_header = models.BooleanField(default=True)
    show_in_footer = models.BooleanField(default=True)

    class Meta(OrderedModel.Meta):
        verbose_name = "Navigation link"
        verbose_name_plural = "Navigation links"

    def __str__(self):
        return f"{self.label} → {self.href}"


class SocialLink(OrderedModel):
    class Platform(models.TextChoices):
        FACEBOOK = "facebook", "Facebook"
        INSTAGRAM = "instagram", "Instagram"
        TIKTOK = "tiktok", "TikTok"
        YOUTUBE = "youtube", "YouTube"
        X = "x", "X / Twitter"

    platform = models.CharField(
        max_length=20,
        choices=Platform.choices,
        default=Platform.FACEBOOK,
        help_text=(
            "Picks the icon. Facebook and Instagram have drawn icons on the "
            "site; other platforms fall back to a label."
        ),
    )
    url = models.URLField()
    label = models.CharField(
        max_length=80,
        blank=True,
        help_text="Accessible link label. Defaults to “Salon on <platform>”.",
    )

    class Meta(OrderedModel.Meta):
        verbose_name = "Social link"
        verbose_name_plural = "Social links"

    def __str__(self):
        return self.get_platform_display()

    @property
    def accessible_label(self) -> str:
        return self.label or f"Salon on {self.get_platform_display()}"
