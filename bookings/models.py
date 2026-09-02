"""Inbound enquiries.

The landing page has two calls to action — "Book Now" and "Contact Us" — that
currently link to routes which do not exist. These are the models those routes
will post to, and they are the only writable part of the API.
"""

import secrets
from datetime import time as dt_time

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from common.models import OrderedModel, SingletonModel, TimeStampedModel
from common.storage import private_storage
from common.validators import validate_phone, validate_upload
from sections.models import Service as SectionsService


class BookingSection(SingletonModel):
    """Copy for the four steps of the booking flow on /services.

    The steps themselves are structural — service, barber, details, payment, in
    that order — so only their wording lives here. Renaming a step does not
    reorder or remove it.
    """

    # The /services page's own title, above the form. Used to live on
    # sections.ServiceMenuSection, which was the landing page's Service Menu
    # band; that band is gone, so the copy moved to the page that still needs it.
    page_heading = models.CharField(max_length=120, default="Book your seat")
    page_intro = models.TextField(
        default=(
            "Pick a service and a stylist, tell us when suits you, and we will "
            "confirm by phone."
        )
    )

    service_heading = models.CharField(max_length=120, default="Choose your service")
    barber_heading = models.CharField(max_length=120, default="Choose your barber")
    details_heading = models.CharField(max_length=120, default="Your details")
    payment_heading = models.CharField(max_length=120, default="Pay with eSewa")

    # The short labels in the progress bar above the form. Kept separate from
    # the headings because the bar has room for one word, not five.
    service_step = models.CharField(max_length=40, default="Service")
    barber_step = models.CharField(max_length=40, default="Barber")
    details_step = models.CharField(max_length=40, default="Details")
    payment_step = models.CharField(max_length=40, default="Payment")

    submit_label = models.CharField(max_length=60, default="Submit booking")
    success_heading = models.CharField(
        max_length=120, default="Booking request sent"
    )

    # The payment step. This is not a payment integration: the customer scans
    # the QR, pays in their own eSewa app, and uploads a screenshot that a
    # human checks in the admin. Nothing here talks to eSewa or verifies a
    # transfer, so the wording below should not promise that it does.
    esewa_qr = models.ImageField(
        upload_to="payment/",
        blank=True,
        help_text=(
            "The salon's own eSewa QR code. Shown on the last step of the "
            "booking form. Leave empty and that step explains how to pay "
            "instead of showing a broken image."
        ),
    )
    esewa_note = models.CharField(
        max_length=200,
        default="Scan with eSewa, pay, then upload your payment screenshot below.",
        help_text="Instruction shown beside the QR.",
    )
    deposit_percent = models.PositiveSmallIntegerField(
        default=100,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text=(
            "How much of the service price to collect up front, as a "
            "percentage. 100 means the customer pays the full price to book; "
            "30 means they pay a 30% deposit and the rest at the salon. The "
            "amount is worked out from the price of whichever service they "
            "picked, so it is never typed by hand."
        ),
    )

    # --- Opening hours -----------------------------------------------------
    # These do not appear on the site. They exist to build the dropdown of
    # visit times in the admin, so a booking cannot be scheduled for 3am by a
    # slip of the keyboard — which is what a free time input allows.
    opens_at = models.TimeField(
        default=dt_time(9, 0),
        help_text="First appointment of the day. The earliest time you can pick.",
    )
    closes_at = models.TimeField(
        default=dt_time(19, 0),
        help_text="Last appointment of the day. The latest time you can pick.",
    )
    slot_minutes = models.PositiveSmallIntegerField(
        default=30,
        choices=[(15, "Every 15 minutes"), (30, "Every half hour"), (60, "Every hour")],
        help_text="How far apart the times in the dropdown are.",
    )

    class Meta:
        verbose_name = "Booking form"
        verbose_name_plural = "Booking form"

    def __str__(self):
        return "Booking form"

    def time_slots(self) -> list[dt_time]:
        """Every bookable time, from opening to closing inclusive.

        Inclusive of `closes_at` because it is described as the last
        appointment, not the moment the door is locked.
        """
        step = self.slot_minutes or 30
        start = self.opens_at or dt_time(9, 0)
        end = self.closes_at or dt_time(19, 0)

        first = start.hour * 60 + start.minute
        last = end.hour * 60 + end.minute
        if last < first:
            # Closing before opening is a typo, and generating nothing would
            # leave staff with an empty dropdown and no clue why.
            return [start]

        return [
            dt_time(minute // 60, minute % 60)
            for minute in range(first, last + 1, step)
        ]


def label_time(value: dt_time) -> str:
    """A time as a person says it: "9:30 am", "12:00 noon", "12:00 midnight"."""
    if value.minute == 0 and value.hour == 12:
        return "12:00 noon"
    if value.minute == 0 and value.hour == 0:
        return "12:00 midnight"
    hour = value.hour % 12 or 12
    suffix = "am" if value.hour < 12 else "pm"
    return f"{hour}:{value.minute:02d} {suffix}"


class Barber(OrderedModel, TimeStampedModel):
    """Someone the customer can pick in step 2 of the booking flow.

    `photo` is the point of the model — the flow shows a face before it asks
    for any details. A barber with no photo still renders; the card falls back
    to their initials, so adding the row and uploading the picture can happen
    at different times.
    """

    name = models.CharField(max_length=120)
    role = models.CharField(
        max_length=120,
        blank=True,
        help_text='Shown under the name, e.g. "Senior stylist".',
    )
    photo = models.ImageField(upload_to="barbers/", blank=True)
    bio = models.TextField(blank=True)

    # When this barber works. Displayed on their card in the booking flow so a
    # customer picks someone who is actually in that day. Deliberately not
    # enforced: there is no slot booking here, and a half-built availability
    # check that silently rejects a valid request is worse than none.
    working_days = models.CharField(
        max_length=120,
        blank=True,
        help_text='Free text, e.g. "Sun – Fri" or "Weekends only". Leave empty to hide.',
    )
    works_from = models.TimeField(
        null=True, blank=True, help_text="Start of their day. Pick from the list."
    )
    works_to = models.TimeField(
        null=True, blank=True, help_text="End of their day. Pick from the list."
    )

    # Separate from `is_published`, and the difference matters:
    #
    #   is_published = False -> the barber is not on the site at all. For
    #                           someone who has left, or is not ready to show.
    #   is_available = False -> on the site, on the card, clearly marked as
    #                           not bookable. For a holiday, a sick day, or a
    #                           week that is already full.
    #
    # Unpublishing someone who is merely away hides the fact that they exist,
    # and a customer looking for their usual barber concludes they have gone.
    is_available = models.BooleanField(
        default=True,
        verbose_name="Available for bookings",
        help_text=(
            "Untick while this barber is away or fully booked. They stay on "
            "the site with an 'unavailable' badge and cannot be selected. To "
            "remove them from the site entirely, untick Is published instead."
        ),
    )
    unavailable_note = models.CharField(
        max_length=120,
        blank=True,
        help_text=(
            'Shown on the card when unavailable, e.g. "Back on 20 August". '
            "Leave empty for a plain 'Not available' badge."
        ),
    )

    class Meta(OrderedModel.Meta):
        verbose_name = "Barber"
        verbose_name_plural = "Barbers"

    def __str__(self):
        return self.name

    @property
    def initials(self) -> str:
        return "".join(part[0] for part in self.name.split()[:2]).upper()

    @property
    def schedule(self) -> str:
        """One line for the card: "Sun – Fri · 10:00 am – 7:00 pm".

        Every part is optional, so days-only, hours-only and a single open or
        close time all read correctly rather than leaving a stray separator.
        """
        parts = []
        if self.working_days:
            parts.append(self.working_days)

        # `label_time` rather than a local formatter, so a barber's hours and
        # the booking dropdown say "12:00 noon" the same way.
        if self.works_from and self.works_to:
            parts.append(f"{label_time(self.works_from)} – {label_time(self.works_to)}")
        elif self.works_from:
            parts.append(f"from {label_time(self.works_from)}")
        elif self.works_to:
            parts.append(f"until {label_time(self.works_to)}")

        return " · ".join(parts)

    @property
    def availability_label(self) -> str:
        """The badge text on the card, so the wording lives in one place."""
        if self.is_available:
            return "Available"
        return self.unavailable_note or "Not available"


class TimeSlot(OrderedModel, TimeStampedModel):
    """A bookable time slot for a barber.
    
    Created manually in the admin for each barber. Can be marked as booked
    or unbooked, allowing the salon to control availability.
    """
    
    barber = models.ForeignKey(
        Barber,
        on_delete=models.CASCADE,
        related_name='time_slots',
        help_text="Which barber this time slot is for"
    )
    date = models.DateField(
        help_text="Which day this slot is available (YYYY-MM-DD)"
    )
    start_time = models.TimeField(
        help_text="Start time of this slot (e.g., 10:00)"
    )
    end_time = models.TimeField(
        help_text="End time of this slot (e.g., 11:00)"
    )
    is_booked = models.BooleanField(
        default=False,
        help_text="Check to mark this slot as booked (unavailable for customers)"
    )
    
    class Meta(OrderedModel.Meta):
        verbose_name = "Time Slot"
        verbose_name_plural = "Time Slots"
        ordering = ['barber', 'date', 'start_time', 'order']
        # Prevent duplicate slots for same barber at same time
        constraints = [
            models.UniqueConstraint(
                fields=['barber', 'date', 'start_time', 'end_time'],
                name='unique_barber_date_time_slot'
            )
        ]
    
    def __str__(self):
        status = "Booked" if self.is_booked else "Available"
        return f"{self.barber.name} - {self.date} {self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')} ({status})"
    
    @property
    def time_label(self) -> str:
        """Format time range for display, e.g., '10:00 AM - 11:00 AM'"""
        return f"{label_time(self.start_time)} – {label_time(self.end_time)}"


class Appointment(TimeStampedModel):
    class Status(models.TextChoices):
        """The life of a booking, in order.

        PENDING   - sent by the customer, payment not checked yet
        APPROVED  - the salon checked the payment screenshot and issued an
                    order ID; this is the point the seat is actually held
        COMPLETED - the cut happened
        CANCELLED - it did not, for any reason
        """

        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    name = models.CharField(max_length=120)
    # Optional: the booking form asks for name, address and description only.
    # Kept on the model because the older "Book Now" enquiry collected them and
    # existing rows still carry them.
    email = models.EmailField(blank=True)
    # Validated only here, not on GoogleProfile: that one is copied from
    # Google, which owns it, and rejecting a value they already accepted would
    # break the sync rather than protect anything.
    phone = models.CharField(max_length=40, blank=True, validators=[validate_phone])
    address = models.CharField(max_length=255, blank=True)

    service = models.ForeignKey(
        "sections.Service",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="appointments",
        help_text="Kept if the service is later deleted, so the record survives.",
    )
    barber = models.ForeignKey(
        "bookings.Barber",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="appointments",
        help_text="Kept if the barber later leaves, so the record survives.",
    )
    
    # Link to the specific time slot this appointment is for
    time_slot = models.ForeignKey(
        "bookings.TimeSlot",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="appointments",
        help_text="The time slot selected for this appointment"
    )
    
    # Retired. The booking form used to ask the customer when they would like
    # to come; it no longer does, because the salon decides the time. Kept
    # because older rows still carry what was asked, and `approve()` promotes
    # that to the scheduled time so those bookings do not lose it. Nothing
    # writes to these any more and they are not in the admin form.
    preferred_date = models.DateField(null=True, blank=True)
    preferred_time = models.TimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    # When the salon has actually told the customer to come. This is the pair
    # the customer's status page shows once the booking is approved, and the
    # only times on this model that mean "be here then".
    #
    # Left blank, `approve()` copies the preferred pair across — the common
    # case is that the requested slot is fine, and making staff retype it to
    # confirm it would mean most bookings get approved with no time at all.
    scheduled_date = models.DateField(
        null=True,
        blank=True,
        help_text=(
            "The date you want the customer to come in. Leave empty to accept "
            "the date they asked for."
        ),
    )
    scheduled_time = models.TimeField(
        null=True,
        blank=True,
        help_text=(
            "The time you want them to come in. Leave empty to accept the "
            "time they asked for. The customer sees this as soon as you "
            "approve the booking."
        ),
    )

    # What the customer uploaded as proof of the eSewa transfer. Not a payment
    # integration: nothing here is verified, it is a picture a human checks in
    # the admin before confirming the booking.
    # Private storage, not MEDIA_ROOT: this is a financial record, and anything
    # under MEDIA_ROOT is handed out by the web server to whoever asks for the
    # path. Reachable only through the authorising view — see
    # `api.views.payment_screenshot` and `common/storage.py`.
    payment_screenshot = models.ImageField(
        upload_to="payments/%Y/%m/",
        blank=True,
        storage=private_storage,
        validators=[validate_upload],
    )

    # Who booked, taken from a verified Google session — never from the form.
    # Empty means the booking was made before sign-in was switched on, or by
    # someone whose token failed verification.
    google_user_id = models.CharField(
        max_length=64,
        blank=True,
        # No db_index: `appt_google_created_idx` below leads with this column,
        # so a standalone index on it duplicates work the composite already
        # does. Bookings are the only frequent write on this site, which makes
        # this the table where a spare index actually costs something.
        help_text="Google account id. Set automatically; not editable by the customer.",
    )

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )

    # Given to the customer the moment they submit, so they have something to
    # quote while the booking is still pending. Not the order ID: this only
    # identifies the request, it does not mean the seat is held.
    reference = models.CharField(
        max_length=16,
        unique=True,
        blank=True,
        # No db_index: `unique=True` already builds one, on every backend.
        help_text="Shown to the customer on submit. Generated automatically.",
    )

    # Issued when the booking is approved, never before. This is what the
    # customer shows at the salon and what staff search for to verify them.
    order_id = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        # No db_index: `unique=True` already builds one.
        help_text="Created automatically on approval. Blank until then.",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            # The admin's default view and its status tabs.
            models.Index(fields=["status", "-created_at"], name="appt_status_created_idx"),
            # "Who is in on Tuesday" — the one date question staff actually ask.
            models.Index(fields=["preferred_date"], name="appt_preferred_date_idx"),
            # my-bookings, which filters on the verified Google id then orders.
            models.Index(
                fields=["google_user_id", "-created_at"], name="appt_google_created_idx"
            ),
        ]

    def __str__(self):
        return f"{self.order_id or self.reference or self.pk} — {self.name}"

    def save(self, *args, **kwargs):
        """Allocate a reference on first save, retrying a genuine collision.

        The uniqueness check has to be the database's, not a prior `exists()`:
        two submissions arriving together both pass an `exists()` check and the
        loser then raises IntegrityError at INSERT — a 500 for someone trying
        to book a haircut. Here the INSERT *is* the check, and losing it just
        means drawing another code.
        """
        if self.reference:
            return super().save(*args, **kwargs)

        for attempt in range(10):
            self.reference = self._make_reference()
            try:
                # Savepoint, so a failed INSERT does not poison an outer
                # transaction and make every retry fail too.
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                # Only a reference collision is worth retrying; anything else
                # would fail identically ten times over.
                clashed = Appointment.objects.filter(reference=self.reference).exists()
                if attempt == 9 or not clashed:
                    raise

    @staticmethod
    def _make_reference() -> str:
        """A short code the customer can read out over the phone.

        Crockford-style alphabet: no I, O, 1 or 0, because a reference is
        going to be spoken and re-typed and those are the pairs people get
        wrong.
        """
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        return "SLN-" + "".join(secrets.choice(alphabet) for _ in range(6))

    def approve(self) -> str:
        """Mark approved and issue the order ID. Idempotent.

        Order IDs are sequential per year, so staff can tell roughly when an
        order was placed from the number itself. Sequential means the next one
        has to be read and written without anyone else doing the same in
        between — two admins clicking Approve at the same moment previously
        both computed the same number and the second save died on the unique
        constraint.

        `select_for_update` over the year's rows is what serialises that. On
        SQLite it is a no-op, but SQLite already serialises every write.
        """
        with transaction.atomic():
            # Customer selected their time slot during booking - no need to copy
            # preferred dates anymore since the time_slot field contains their choice
            
            if not self.order_id:
                year = timezone.now().year
                prefix = f"ORD-{year}-"
                taken = (
                    Appointment.objects.select_for_update()
                    .filter(order_id__startswith=prefix)
                    .order_by("-order_id")
                    .values_list("order_id", flat=True)
                    .first()
                )
                nxt = int(taken.rsplit("-", 1)[1]) + 1 if taken else 1
                self.order_id = f"{prefix}{nxt:04d}"
            if self.status != self.Status.APPROVED:
                self.status = self.Status.APPROVED
                self.approved_at = timezone.now()
            self.save()
        return self.order_id

    def complete(self) -> None:
        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at", "updated_at"])


class ContactMessage(TimeStampedModel):
    name = models.CharField(max_length=120)
    email = models.EmailField()
    subject = models.CharField(max_length=200, blank=True)
    message = models.TextField()
    is_handled = models.BooleanField(default=False)

    # Who sent it, taken from a verified Google session -- never from the form.
    # The website only offers the message form to a signed-in visitor, so this
    # is normally set; it stays blank-able because the endpoint still accepts an
    # enquiry without a token. Refusing one because sign-in blinked, or because
    # a tab sat open until the session expired, would lose a real customer --
    # the same trade `Appointment.google_user_id` makes.
    google_user_id = models.CharField(
        max_length=64,
        blank=True,
        help_text="Google account id. Set automatically; not editable by the sender.",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name}: {self.subject or self.message[:40]}"


class Service(SectionsService):
    """Proxy so the bookable services appear under Enquiries in the admin.

    Django groups the admin index by app, and the real model lives in
    `sections` because that is where the page-content models are. A proxy adds
    no table and no column — it is the same rows, listed under the app the
    booking flow belongs to.

    The original stays registered (hidden from the sidebar via Jazzmin's
    `hide_models`) because `AppointmentAdmin.autocomplete_fields` resolves the
    admin of the *related* model, `sections.Service`. Unregistering it would
    break that lookup with admin.E039.
    """

    class Meta:
        proxy = True
        ordering = ["order", "pk"]
        verbose_name = "Service"
        verbose_name_plural = "Services"


class GoogleProfile(TimeStampedModel):
    """A customer who has signed in with Google, mirrored into Django's Users.

    Google is the source of truth — accounts are created there, and this table
    exists so the admin can answer "who has signed up" without leaving Django.
    It is attached to an `auth.User` row so the accounts appear under
    Authentication and Authorization -> Users, which is where someone would
    look for them.

    Those mirrored users have an unusable password set: they authenticate
    through Google, never through Django's login form, and a real password on
    them would be a second way in that nobody is watching.

    Written from the claims of a verified session token whenever a booking or
    an enquiry arrives — there is nothing to poll. This is the difference from
    the Clerk arrangement it replaces: Clerk had a back-end API that could list
    every account, so a `sync_clerk_users` command kept a fuller copy in step.
    Google has no equivalent "list my users" call, so the fields here are
    exactly what a sign-in tells us and no more. Rather than keep columns that
    could only ever be null, they are gone.
    """

    user = models.OneToOneField(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="google_profile",
    )
    # `unique=True` carries the index; MySQL collapsed the pair but
    # PostgreSQL would have built both.
    google_user_id = models.CharField(max_length=64, unique=True)

    image_url = models.URLField(max_length=500, blank=True)
    email_verified = models.BooleanField(default=False)

    # Touched each time a verified request arrives, so the admin can sort by
    # who is actually still using the site.
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_seen_at", "-created_at"]
        verbose_name = "Google account"
        verbose_name_plural = "Google accounts"

    def __str__(self):
        return self.user.email or self.user.username or self.google_user_id
