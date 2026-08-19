from django import forms
from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html

from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from bookings.models import (
    Appointment,
    Barber,
    BookingSection,
    ClerkProfile,
    ContactMessage,
    Service,
    label_time,
)
from common.admin import SingletonAdmin
from common.admin_ajax import AdminAjaxMixin
from sections.admin import ServiceAdmin as _SectionsServiceAdmin


@admin.register(BookingSection)
class BookingSectionAdmin(SingletonAdmin):
    fieldsets = (
        (
            "Step headings",
            {
                "fields": (
                    "service_heading",
                    "barber_heading",
                    "details_heading",
                    "payment_heading",
                ),
                "description": (
                    "The large heading above each step of the booking form on "
                    "/services. The steps and their order are fixed; this is "
                    "only what they are called."
                ),
            },
        ),
        (
            "Progress bar labels",
            {
                "fields": (
                    "service_step",
                    "barber_step",
                    "details_step",
                    "payment_step",
                ),
                "description": "The short labels in the numbered bar above the form.",
            },
        ),
        (
            "Opening hours",
            {
                "fields": ("opens_at", "closes_at", "slot_minutes"),
                "description": (
                    "Customers never see these. They build the list of times "
                    "you can choose from when you set a booking's visit time, "
                    "so a booking cannot be scheduled for the middle of the "
                    "night by a mistyped hour. Change them and the dropdown "
                    "changes; bookings already scheduled keep their time."
                ),
            },
        ),
        (
            "Payment (eSewa QR)",
            {
                "fields": ("esewa_qr", "deposit_percent", "esewa_note"),
                "description": (
                    "Upload the salon's eSewa QR here — this is what customers "
                    "scan on the last step to pay. They then upload a "
                    "screenshot of the transfer, which appears on the booking "
                    "in Appointments. Nothing is verified automatically, so "
                    "check the screenshot before confirming."
                ),
            },
        ),
        ("Finishing", {"fields": ("submit_label", "success_heading")}),
    )


class PrivateFileInput(forms.ClearableFileInput):
    """A file widget that does not ask the storage for a URL.

    Django's stock widget renders the current file as a link, which means
    calling `value.url` — and private storage raises there on purpose, so the
    change page for any booking with a screenshot would 500 before this.

    Uploading and clearing still work; the only thing removed is the link,
    which would have been an unauthorised direct URL anyway. The image itself
    is shown by `payment_preview` underneath, through the endpoint that checks
    who is asking.
    """

    template_name = "django/forms/widgets/file.html"

    def is_initial(self, value):
        # The stock implementation is `bool(value and value.url)`.
        return bool(value)

    def format_value(self, value):
        return getattr(value, "name", None) if self.is_initial(value) else None


def use_time_dropdown(form, field_name, blank_label):
    """Replace a TimeField's free text input with the salon's time slots.

    A plain time input accepts 03:14 as readily as 3pm, which is how a booking
    ends up scheduled for the middle of the night and a barber ends up starting
    work before dawn. The choices come from the opening hours on the Booking
    form singleton, so changing the hours changes every dropdown at once,
    without a deploy.
    """
    field = form.fields.get(field_name)
    if field is None:
        return

    # `str(datetime.time)` is "11:00:00", and that is what Django's Select
    # compares an option value against when deciding which one is picked.
    # Anything shorter renders with nothing selected on an existing row.
    slots = BookingSection.load().time_slots()
    choices = [("", blank_label)]
    choices += [(slot.strftime("%H:%M:%S"), label_time(slot)) for slot in slots]

    # A time already on the record that is not a slot — set before the hours
    # changed, or typed in when this was a free field. Kept as an option so
    # opening the page does not silently reset it to blank.
    current = form.initial.get(field_name) or getattr(
        form.instance, field_name, None
    )
    if current and current not in slots:
        choices.insert(
            1,
            (
                current.strftime("%H:%M:%S"),
                f"{label_time(current)} — outside opening hours",
            ),
        )

    field.widget = forms.Select(choices=choices)


class BarberAdminForm(forms.ModelForm):
    """Working hours are picked from the salon's slots, not typed."""

    class Meta:
        model = Barber
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        use_time_dropdown(self, "works_from", "— not set —")
        use_time_dropdown(self, "works_to", "— not set —")

    def clean(self):
        cleaned = super().clean()
        starts, ends = cleaned.get("works_from"), cleaned.get("works_to")
        if starts and ends and ends <= starts:
            # Caught here rather than left to read as a typo on the card, where
            # "7:00 pm – 10:00 am" looks deliberate and nobody questions it.
            self.add_error("works_to", "The end of the day must be after the start.")
        return cleaned


@admin.register(Barber)
class BarberAdmin(AdminAjaxMixin, admin.ModelAdmin):
    ajax_toggle_fields = ("is_available", "is_published")
    # `availability` reads the same field as the toggle beside it, so it has to
    # be re-rendered too or the row contradicts itself until a reload.
    ajax_refresh_cells = ("availability", "is_available", "is_published")

    form = BarberAdminForm
    list_display = (
        "name",
        "role",
        "thumbnail",
        "schedule",
        "availability",
        "is_available",
        "is_published",
        "order",
    )
    # Both toggles editable from the list: taking someone off for the day is a
    # one-click job, not a reason to open their page.
    list_editable = ("is_available", "is_published", "order")
    list_filter = ("is_available", "is_published")
    search_fields = ("name", "role", "bio")
    readonly_fields = ("thumbnail", "schedule")
    fieldsets = (
        ("Who", {"fields": ("name", "role", "bio")}),
        ("Photo", {"fields": ("photo", "thumbnail")}),
        (
            "When they work",
            {
                "fields": ("working_days", "works_from", "works_to", "schedule"),
                "description": (
                    "Shown on this barber's card in the booking flow. The times "
                    "come from the salon's opening hours — change those under "
                    "<b>Booking form</b> if the list is missing a time you need."
                ),
            },
        ),
        (
            "Availability",
            {
                "fields": ("is_available", "unavailable_note"),
                "description": (
                    "Untick <b>Available for bookings</b> while this barber is "
                    "away or fully booked: they stay on the site with a badge "
                    "saying so, and customers cannot select them.<br><br>"
                    "This is not the same as unpublishing. Unpublish someone "
                    "who has left — a customer looking for a barber who is "
                    "merely on holiday should still see that they exist."
                ),
            },
        ),
        ("Placement", {"fields": ("is_published", "order")}),
    )

    @admin.display(description="Reads as")
    def schedule(self, obj):
        return obj.schedule or "— not set —"

    @admin.display(description="Bookable")
    def availability(self, obj):
        if obj.is_available:
            return format_html('<span style="color:#1b5e20">✓ Available</span>')
        return format_html(
            '<span style="color:#c0392b">✕ {}</span>',
            obj.unavailable_note or "Not available",
        )

    @admin.display(description="Photo")
    def thumbnail(self, obj):
        if not obj.photo:
            return "— no photo —"
        return format_html(
            '<img src="{}" style="height:56px;width:56px;border-radius:50%;object-fit:cover">',
            obj.photo.url,
        )


class AppointmentAdminForm(forms.ModelForm):
    """Adds the visit-time dropdown to the stock appointment form."""

    class Meta:
        model = Appointment
        fields = "__all__"
        widgets = {"payment_screenshot": PrivateFileInput}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        use_time_dropdown(self, "scheduled_time", "— no time set —")


@admin.register(Appointment)
class AppointmentAdmin(AdminAjaxMixin, admin.ModelAdmin):
    # The two actions that may be run against a single row. An allowlist, not a
    # convenience: `delete_selected` is registered on every ModelAdmin, and
    # without this it would be reachable one row at a time from a button.
    ajax_row_actions = ("approve_bookings", "complete_bookings")
    # Everything the row shows that an approval changes -- including the
    # buttons themselves, so an approved row's "Approve" becomes "Mark
    # completed" without a reload.
    ajax_refresh_cells = ("order_id", "visit", "state", "row_actions")

    form = AppointmentAdminForm
    list_display = (
        "reference",
        "order_id",
        "name",
        "service",
        "barber",
        "visit",
        "paid",
        "state",
        "created_at",
        "row_actions",
    )
    # `scheduled_date` first: "who is in on Tuesday" is a question about when
    # people are actually coming, not when they asked to.
    list_filter = ("status", "scheduled_date", "service", "barber")
    # order_id and reference first: verifying someone at the counter means
    # typing the code they are holding.
    search_fields = (
        "order_id",
        "reference",
        "name",
        "email",
        "phone",
        "address",
        "notes",
    )
    date_hierarchy = "created_at"
    autocomplete_fields = ("service",)
    # Enquiries are records of what someone sent, not editable content.
    readonly_fields = (
        "created_at",
        "updated_at",
        "payment_preview",
        "clerk_user_id",
        "reference",
        "order_id",
        "approved_at",
        "completed_at",
    )
    fieldsets = (
        (
            "Who",
            {
                "fields": ("name", "email", "phone", "address", "clerk_user_id"),
                "description": (
                    "The account id is taken from the signed-in session and "
                    "verified server-side, so it cannot be faked by the form. "
                    "Empty means the booking was made without signing in."
                ),
            },
        ),
        (
            "What",
            {
                # No date or time here: the customer does not choose one. The
                # visit time is set under Handling below.
                "fields": (
                    "service",
                    "barber",
                    "notes",
                )
            },
        ),
        (
            "Payment",
            {
                "fields": ("payment_screenshot", "payment_preview"),
                "description": (
                    "The customer's own screenshot of their eSewa transfer. "
                    "Nothing is verified automatically — check it before "
                    "confirming."
                ),
            },
        ),
        (
            "Handling",
            {
                "fields": (
                    "scheduled_date",
                    "scheduled_time",
                    "status",
                    "reference",
                    "order_id",
                    "approved_at",
                    "completed_at",
                    "created_at",
                    "updated_at",
                ),
                "description": (
                    "<b>Set the date and time you want the customer to come "
                    "in.</b> They see it on their bookings page the moment you "
                    "approve, so it is the time they will turn up. Leave both "
                    "empty to accept whatever they asked for under "
                    "<i>What</i> — approving copies it across.<br><br>"
                    "Then use the actions on the list page to move the booking "
                    "along: <b>Approve</b> checks out the payment and issues "
                    "the order ID the customer shows at the salon; "
                    "<b>Mark completed</b> is for after the cut. The order ID "
                    "is generated once and never changes."
                ),
            },
        ),
    )

    @admin.display(description="")
    def row_actions(self, obj):
        """The one action this booking is actually waiting for, as a button.

        Approving used to mean a checkbox, a scroll, a dropdown, a Go button
        and a re-rendered page. The bulk path is still there and still the
        right tool for a morning's worth of bookings; this is for the one that
        just came in.

        Three details here are load-bearing rather than stylistic:

        * `type="button"`. The changelist body is inside `<form
          id="changelist-form">`, and a bare <button> defaults to submitting
          it -- so the omission would turn every click into a full page POST.
        * `disabled`, removed by admin/salon-ajax.js once it has bound its
          handler. With no JavaScript these read as unavailable rather than
          as live buttons that silently do nothing, and the working bulk
          actions are directly above them.
        * `data-salon-pk` on the wrapper, so the script never has to guess the
          row's identity from a link or a checkbox that may not be there.
        """
        buttons = {
            Appointment.Status.PENDING: ("approve_bookings", "approve", "Approve"),
            Appointment.Status.APPROVED: ("complete_bookings", "complete", "Mark done"),
        }
        choice = buttons.get(obj.status)
        if choice is None:
            # Completed and cancelled are finished. An empty cell would leave
            # the column looking ragged, so it says so.
            return format_html(
                '<span class="salon-rowactions__none">&mdash;</span>'
            )

        action, modifier, label = choice
        return format_html(
            '<div class="salon-rowactions" data-salon-pk="{}">'
            '<button type="button" class="salon-rowactions__btn '
            'salon-rowactions__btn--{}" data-salon-action="{}" disabled>{}</button>'
            "</div>",
            obj.pk,
            modifier,
            action,
            label,
        )

    @admin.display(description="Status", ordering="status")
    def state(self, obj):
        colours = {
            "pending": ("#8a6d00", "#fff6d8"),
            "approved": ("#1b5e20", "#e3f5e4"),
            "completed": ("#0d47a1", "#e3edfb"),
            "cancelled": ("#8a1c1c", "#fbe3e3"),
        }
        fg, bg = colours.get(obj.status, ("#333", "#eee"))
        return format_html(
            '<span style="background:{};color:{};padding:2px 10px;'
            'border-radius:999px;font-weight:600;font-size:11px">{}</span>',
            bg,
            fg,
            obj.get_status_display(),
        )

    @admin.display(description="Visit", ordering="scheduled_date")
    def visit(self, obj):
        """When the customer has been told to come in.

        Blank until someone sets it, which is the state worth spotting from
        the changelist — an approved booking with no time is a customer who
        has paid and has not been told when to turn up.
        """
        # `preferred_*` is only ever set on bookings made when the form still
        # asked; it is shown so those do not look timeless.
        date = obj.scheduled_date or obj.preferred_date
        time = obj.scheduled_time or obj.preferred_time
        if not date and not time:
            return format_html('<span style="color:#c0392b">— not set —</span>')

        when = " ".join(
            part
            for part in (
                date.strftime("%d %b") if date else "",
                time.strftime("%H:%M") if time else "",
            )
            if part
        )
        return format_html("<b>{}</b>", when)

    @admin.display(boolean=True, description="Proof")
    def paid(self, obj):
        return bool(obj.payment_screenshot)

    @admin.display(description="Uploaded proof")
    def payment_preview(self, obj):
        """The screenshot, via the authorising view rather than the file.

        `obj.payment_screenshot.url` used to work and deliberately does not any
        more — these are financial records and private storage raises rather
        than hand out a URL that skips the access check. Staff reach them
        through the same endpoint the customer does; the admin session is what
        authorises it there.
        """
        if not obj.payment_screenshot:
            return "— nothing uploaded —"
        url = reverse("payment-screenshot", kwargs={"reference": obj.reference})
        return format_html(
            '<a href="{0}" target="_blank" rel="noopener">'
            '<img src="{0}" style="max-height:340px;max-width:100%"></a>',
            url,
        )

    @admin.action(description="Approve — issue order ID")
    def approve_bookings(self, request, queryset):
        """Approve and issue order IDs.

        Looped rather than a bulk `update()`, because each order ID has to be
        allocated from the last one used — a bulk update cannot do that, and
        would leave every row in the selection with the same number.
        """
        issued = []
        timeless = []
        for booking in queryset.exclude(status=Appointment.Status.CANCELLED):
            issued.append(f"{booking.name}: {booking.approve()}")
            if not booking.scheduled_date and not booking.scheduled_time:
                timeless.append(booking.name)

        if not issued:
            self.message_user(request, "Nothing to approve (cancelled bookings skipped).")
            return

        self.message_user(
            request,
            format_html(
                "Approved {} booking(s). Order IDs — {}",
                len(issued),
                ", ".join(issued),
            ),
        )
        if timeless:
            # Approved, but the customer's page will say "we will call to
            # agree a time" — worth saying out loud rather than leaving
            # someone to notice the blank later.
            self.message_user(
                request,
                format_html(
                    "No visit time set for {} — open the booking and fill in "
                    "the Handling date and time, or call them.",
                    ", ".join(timeless),
                ),
                level=messages.WARNING,
            )

    @admin.action(description="Mark completed — the cut happened")
    def complete_bookings(self, request, queryset):
        done = 0
        for booking in queryset.filter(status=Appointment.Status.APPROVED):
            booking.complete()
            done += 1
        skipped = queryset.count() - done
        message = f"{done} booking(s) completed."
        if skipped:
            message += f" {skipped} skipped — approve them first."
        self.message_user(request, message)

    actions = ["approve_bookings", "complete_bookings"]


@admin.register(ContactMessage)
class ContactMessageAdmin(AdminAjaxMixin, admin.ModelAdmin):
    ajax_toggle_fields = ("is_handled",)

    list_display = ("name", "email", "subject", "is_handled", "created_at")
    list_editable = ("is_handled",)
    list_filter = ("is_handled",)
    search_fields = ("name", "email", "subject", "message")
    date_hierarchy = "created_at"
    readonly_fields = (
        "name",
        "email",
        "subject",
        "message",
        "sent_by",
        "created_at",
        "updated_at",
    )
    fields = ("name", "email", "subject", "message", "sent_by", "is_handled", "created_at")

    def has_add_permission(self, request):
        return False

    @admin.display(description="Sent by")
    def sent_by(self, obj):
        """Which account sent this, as a person would ask it.

        The raw Clerk id means nothing to staff, so it is resolved through the
        mirrored profile to the email they signed up with. An enquiry with no
        account behind it says so plainly rather than showing an empty field --
        that state is real (the form is offered to signed-in visitors, but the
        endpoint still accepts a message without a token) and staff should be
        able to tell the two apart.
        """
        if not obj.clerk_user_id:
            return "Not signed in"

        profile = (
            ClerkProfile.objects.filter(clerk_user_id=obj.clerk_user_id)
            .select_related("user")
            .first()
        )
        if profile is None:
            # Signed in, but `sync_clerk_users` has not mirrored them yet.
            return f"Account {obj.clerk_user_id[-8:]}"
        return profile.user.email or profile.user.username


@admin.register(Service)
class ServiceProxyAdmin(_SectionsServiceAdmin):
    """Same form as the real ServiceAdmin, listed under Enquiries.

    Subclassed rather than re-declared so the fieldsets, the photo/icon split
    and the help text stay in one place — editing either entry edits the same
    row.
    """

    def get_model_perms(self, request):
        # The parent hides itself from the index; this proxy is the entry that
        # should show, so the normal ModelAdmin behaviour is restored here.
        return admin.ModelAdmin.get_model_perms(self, request)


# --- Signed-up accounts, under Authentication and Authorization -------------


class ClerkProfileInline(admin.StackedInline):
    """Everything Clerk knows, shown on the user it belongs to.

    Read-only throughout: Clerk owns these records, and a value edited here
    would be silently overwritten by the next `sync_clerk_users` run. Editing
    belongs in the Clerk dashboard.
    """

    model = ClerkProfile
    can_delete = False
    extra = 0
    verbose_name_plural = "Clerk account"
    readonly_fields = (
        "clerk_user_id",
        "provider_labels",
        "avatar",
        "phone",
        "email_verified",
        "banned",
        "clerk_created_at",
        "last_sign_in_at",
        "last_synced_at",
        "image_url",
    )
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Signed in with")
    def provider_labels(self, obj):
        return obj.provider_labels or "—"

    @admin.display(description="Avatar")
    def avatar(self, obj):
        if not obj.image_url:
            return "— none —"
        return format_html(
            '<img src="{}" style="height:72px;width:72px;border-radius:50%;object-fit:cover">',
            obj.image_url,
        )


class ClerkUserAdmin(BaseUserAdmin):
    """Django's user admin, plus who signed up through Clerk and how."""

    inlines = [*BaseUserAdmin.inlines, ClerkProfileInline]
    list_display = (
        "username",
        "email",
        "full_name",
        "signed_in_with",
        "signed_up",
        "last_seen",
        "is_staff",
    )
    list_filter = (*BaseUserAdmin.list_filter, "clerk_profile__providers")
    search_fields = (
        "username",
        "email",
        "first_name",
        "last_name",
        "clerk_profile__clerk_user_id",
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("clerk_profile")

    @admin.display(description="Name", ordering="first_name")
    def full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip() or "—"

    @admin.display(description="Signed in with")
    def signed_in_with(self, obj):
        profile = getattr(obj, "clerk_profile", None)
        if profile is None:
            # Staff accounts created with createsuperuser have no Clerk record.
            return format_html('<span style="color:#888">Django login</span>')
        label = profile.provider_labels or "—"
        colour = "#2e7d32" if profile.signed_in_with_google else "#555"
        return format_html('<b style="color:{}">{}</b>', colour, label)

    @admin.display(description="Signed up", ordering="clerk_profile__clerk_created_at")
    def signed_up(self, obj):
        profile = getattr(obj, "clerk_profile", None)
        return profile.clerk_created_at if profile else None

    @admin.display(description="Last sign-in", ordering="clerk_profile__last_sign_in_at")
    def last_seen(self, obj):
        profile = getattr(obj, "clerk_profile", None)
        return profile.last_sign_in_at if profile else None


# Replace Django's registration so Users keeps its place in the sidebar under
# Authentication and Authorization, rather than adding a second list elsewhere.
admin.site.unregister(User)
admin.site.register(User, ClerkUserAdmin)
