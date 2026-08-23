"""Site-wide content: the things that are not any one band of the page.

Field defaults throughout these apps are the copy the site currently ships
with. That is not decoration — `SingletonModel.load()` falls back to an unsaved
instance, so an empty database still serves the exact page that exists today.
"""

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import NoReverseMatch, reverse

from common.fields import EncryptedCharField
from common.models import IMAGE_URL_HELP, OrderedModel, SingletonModel, TimeStampedModel


class SiteSettings(SingletonModel):
    # First, because it takes the wordmark's place rather than sitting beside
    # it: upload a logo and the header and mobile menu draw the image; leave it
    # empty and they draw `brand_name` as text. There is no switch to set — the
    # presence of a file is the switch.
    logo = models.ImageField(
        upload_to="brand/",
        blank=True,
        help_text=(
            "Shown in the header and the mobile menu instead of the brand "
            "name. Leave empty to show the brand name as text. "
            "It is scaled to a fixed height — 96px on a computer, 64px on a "
            "phone — with its proportions kept and a 360px cap on how wide it "
            "may spread. Nothing here needs sizing: upload a mark that reads "
            "at that height, with a transparent background, and it will sit "
            "correctly against the dark bar."
        ),
    )
    logo_url = models.CharField(max_length=500, blank=True, help_text=IMAGE_URL_HELP)

    brand_name = models.CharField(
        max_length=60,
        default="SALON",
        help_text=(
            "The wordmark. Shown in the header and the mobile menu only when "
            "no logo is uploaded above — but the badge always uses it, and it "
            "names the logo for screen readers, so keep it filled in either "
            "way."
        ),
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
        max_length=200, default="© 2026 AJ Salon. All rights reserved."
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

class EmailSettings(SingletonModel):
    """The SMTP account the site sends from, editable in the admin.

    Everything else on this site is edited from an admin screen, and there was
    no reason for the one setting the owner actually needs to change to be the
    exception -- editing `.env` means a file, a server and a restart.

    Values here override the `EMAIL_*` entries in `.env`. That direction is
    deliberate: `.env` is what a fresh clone and the test suite run on, and the
    admin is what the salon uses. Leave a field blank and the `.env` value (or
    its default) is used, so filling in only a username and password is a
    complete Gmail setup.
    """

    class Security(models.TextChoices):
        # The labels are what the admin form shows; nobody running a salon
        # should have to know which of these Gmail wants.
        STARTTLS = "starttls", "STARTTLS — port 587 (Gmail)"
        SSL = "ssl", "SSL/TLS — port 465"
        NONE = "none", "None — unencrypted"

    is_enabled = models.BooleanField(
        default=False,
        verbose_name="Send emails",
        help_text=(
            "Off means nothing is sent — bookings and enquiries are still "
            "saved and still appear below in the admin. Turn this on once the "
            "address and password are filled in and the test email arrives."
        ),
    )

    username = models.CharField(
        max_length=254,
        blank=True,
        verbose_name="Gmail address",
        help_text="The account mail is sent from, e.g. yoursalon@gmail.com.",
    )
    # Long enough for the ciphertext, which is several times the 16 characters
    # that go in. See common.fields.EncryptedCharField.
    password = EncryptedCharField(
        max_length=500,
        blank=True,
        verbose_name="App password",
        help_text=(
            "NOT your Gmail password — Google refuses those. Create a 16-"
            "character App Password at myaccount.google.com/apppasswords "
            "(needs 2-Step Verification on the account first). Spaces are "
            "ignored, so paste it exactly as Google shows it. Stored "
            "encrypted; leave blank to keep the one already saved."
        ),
    )

    from_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Sender name",
        help_text=(
            'Shown as the sender, e.g. "Salon Kathmandu". The address is '
            "always the Gmail account above — Google rewrites it otherwise."
        ),
    )

    notify_emails = models.TextField(
        blank=True,
        verbose_name="Send notifications to",
        help_text=(
            "Who is told when a booking or an enquiry arrives. One address "
            "per line, or separated by commas. Leave blank to use the Gmail "
            "address above."
        ),
    )

    # None of these three need touching for Gmail, which is why they sit in a
    # collapsed fieldset. They exist so that moving to a different provider is
    # a form edit rather than a code change.
    host = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="SMTP server",
        help_text="Optional. Leave blank for Gmail (smtp.gmail.com).",
    )
    port = models.PositiveIntegerField(
        null=True,
        blank=True,
        # 0 is what an empty number box submits in some browsers, and as a port
        # it means "let the OS choose" — which for an SMTP client is a
        # connection to nowhere. Rejecting it keeps "unset" spelled one way.
        validators=[MinValueValidator(1), MaxValueValidator(65535)],
        help_text=(
            "Optional. Leave blank and the port follows the encryption "
            "setting below — 587 for STARTTLS, 465 for SSL."
        ),
    )
    security = models.CharField(
        max_length=10,
        choices=Security.choices,
        default=Security.STARTTLS,
        help_text=(
            "Already set correctly for Gmail (STARTTLS). Only change it for a "
            "provider that asks for something else."
        ),
    )

    # Written by the admin's "Send test email" button, so the screen can show
    # whether the settings have ever actually worked rather than only whether
    # they look complete.
    last_test_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_test_ok = models.BooleanField(default=False, editable=False)
    last_test_detail = models.TextField(blank=True, editable=False)

    class Meta:
        verbose_name = "Email / SMTP settings"
        verbose_name_plural = "Email / SMTP settings"

    def __str__(self):
        return "Email / SMTP settings"

    @property
    def is_ready(self) -> bool:
        """Enough filled in to attempt a send."""
        return bool(self.is_enabled and self.username and self.password)

    def recipients(self) -> list[str]:
        """Who notifications go to, falling back to the sending account."""
        # splitlines() rather than a split on a newline: a browser posts a
        # textarea with CRLF endings, and a stray carriage return left on an
        # address is accepted by SMTP and then silently undeliverable.
        parts = []
        for line in self.notify_emails.splitlines():
            parts.extend(line.split(','))
        addresses = [part.strip() for part in parts if part.strip()]
        if addresses:
            return addresses
        return [self.username] if self.username else []

    def from_email(self) -> str:
        """The From header, with a display name when one is set."""
        if not self.username:
            return ""
        return f"{self.from_name} <{self.username}>" if self.from_name else self.username


class AdminNotification(TimeStampedModel):
    """One thing that arrived and that a member of staff has not looked at yet.

    The bell in the admin navbar reads this table. It exists because the two
    places a submission used to announce itself -- an email, and a number on
    the dashboard -- both fail the same way: the email is in an inbox nobody
    has open, and the dashboard number only moves when the page is reloaded.
    A row here is the thing a staff member is told about while they are
    already looking at the admin.

    Deliberately not a log. Only what somebody might still need to act on gets
    a row, the row carries a copy of what to show rather than a join to fetch
    it, and `prune` keeps the table from growing without bound. Anything
    wanting a full history should read the source tables, which have one.

    **Read state is per user.** `read_by` rather than an `is_read` flag: with
    a flag, the first person to open the bell clears it for everybody else,
    and a salon with an owner and a manager would have exactly one of them
    ever see a booking.
    """

    class Kind(models.TextChoices):
        BOOKING = "booking", "Booking"
        ENQUIRY = "enquiry", "Enquiry"

    kind = models.CharField(max_length=20, choices=Kind.choices)

    # A copy, not a join. The bell renders from this table alone -- one query
    # for a dropdown that is polled every half minute -- and a booking whose
    # customer later edits their name should not silently rewrite the alert
    # that was already sent about it.
    title = models.CharField(max_length=200)
    summary = models.CharField(max_length=255, blank=True)

    # Where clicking it goes, stored as the three parts of an admin change
    # URL rather than the URL itself: a reverse() at render time still
    # resolves correctly if the admin is ever remounted on another prefix.
    target_app_label = models.CharField(max_length=100)
    target_model = models.CharField(max_length=100)
    target_object_id = models.CharField(max_length=64)

    read_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="read_admin_notifications",
        blank=True,
    )

    class Meta:
        verbose_name = "Admin notification"
        verbose_name_plural = "Admin notifications"
        # Newest first is the only order the bell ever asks for.
        ordering = ("-created_at", "-pk")
        indexes = [models.Index(fields=["-created_at"])]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.title}"

    def admin_url(self) -> str:
        """Link to the row this is about, or "" if it cannot be built.

        Returns "" for a target that has since been deleted as well as for one
        whose admin was never registered, and the caller renders the entry
        without a link rather than dropping it -- "a booking came in and has
        since been deleted" is still worth being able to see.
        """
        try:
            return reverse(
                f"admin:{self.target_app_label}_{self.target_model}_change",
                args=[self.target_object_id],
            )
        except NoReverseMatch:
            return ""

    @classmethod
    def unread_for(cls, user):
        """Everything `user` has not opened yet, newest first."""
        return cls.objects.exclude(read_by=user)

    @classmethod
    def prune(cls, keep: int = 200) -> None:
        """Drop the oldest rows beyond `keep`.

        Called after each insert. Without it this table is the one thing in
        the database that only ever grows, on a site whose whole point is to
        receive submissions -- and nobody scrolls to the four-hundredth entry
        in a notification bell.

        A slice cannot be deleted directly in SQL, hence the pk lookup.
        """
        stale = cls.objects.values_list("pk", flat=True)[keep:]
        pks = list(stale)
        if pks:
            cls.objects.filter(pk__in=pks).delete()
