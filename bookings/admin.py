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
    GoogleProfile,
    ContactMessage,
    Service,
    TimeSlot,
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


class TimeSlotInline(admin.TabularInline):
    """Manage time slots directly from the Barber admin page."""
    
    model = TimeSlot
    extra = 1
    fields = ('date', 'start_time', 'end_time', 'is_booked', 'order', 'is_published')
    ordering = ['date', 'start_time', 'order']
    verbose_name = "Time Slot"
    verbose_name_plural = "Time Slots (Create bookable time slots here)"
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Show upcoming slots first, then past
        from django.utils import timezone
        return qs.filter(date__gte=timezone.now().date()).order_by('date', 'start_time', 'order')


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
    inlines = [TimeSlotInline]  # Add time slots inline
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


@admin.register(TimeSlot)
class TimeSlotAdmin(admin.ModelAdmin):
    """Standalone admin for managing all time slots across all barbers."""
    
    list_display = ('barber', 'date', 'time_range', 'booking_status', 'is_booked', 'is_published', 'order')
    list_filter = ('barber', 'date', 'is_booked', 'is_published')
    search_fields = ('barber__name',)
    list_editable = ('is_booked', 'is_published', 'order')
    date_hierarchy = 'date'
    ordering = ['date', 'start_time']
    
    fieldsets = (
        ('Time Slot Details', {
            'fields': ('barber', 'date', 'start_time', 'end_time')
        }),
        ('Availability', {
            'fields': ('is_booked',),
            'description': 'Check "Is booked" to mark this slot as unavailable for customer booking.'
        }),
        ('Placement', {
            'fields': ('is_published', 'order')
        }),
    )
    
    @admin.display(description="Time Range")
    def time_range(self, obj):
        return obj.time_label
    
    @admin.display(description="Status")
    def booking_status(self, obj):
        if obj.is_booked:
            return format_html('<span style="color:#c0392b;font-weight:bold">● Booked</span>')
        return format_html('<span style="color:#1b5e20;font-weight:bold">● Available</span>')
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Show upcoming slots first
        from django.utils import timezone
        return qs.filter(date__gte=timezone.now().date())


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
        "google_user_id",
        "reference",
        "order_id",
        "selected_time_display",
        "approved_at",
        "completed_at",
    )
    fieldsets = (
        (
            "Who",
            {
                "fields": ("name", "email", "phone", "address", "google_user_id"),
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
                # Customer's selection including their chosen time slot
                "fields": (
                    "service",
                    "barber",
                    "selected_time_display",
                    "notes",
                ),
                "description": (
                    "The customer's booking request. The time slot they selected "
                    "is shown here for your reference."
                ),
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
                    "status",
                    "reference",
                    "order_id",
                    "approved_at",
                    "completed_at",
                    "created_at",
                    "updated_at",
                ),
                "description": (
                    "Use the actions on the list page to move the booking "
                    "along: <b>Approve</b> checks out the payment and issues "
                    "the order ID the customer shows at the salon; "
                    "<b>Mark completed</b> is for after the cut. The order ID "
                    "is generated once and never changes.<br><br>"
                    "The customer will come at the time slot they selected "
                    "above. They can see this on their bookings page after approval."
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
        # Show the selected time slot if available
        if obj.time_slot:
            return format_html(
                "<b>{}</b>",
                f"{obj.time_slot.date.strftime('%d %b')} {obj.time_slot.time_label}"
            )
        
        # Fallback to old scheduled/preferred fields for legacy bookings
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
    
    @admin.display(description="Time slot selected by customer")
    def selected_time_display(self, obj):
        """Show the customer's selected time slot in readable format."""
        if not obj.time_slot:
            return format_html('<span style="color:#888">— no time slot selected —</span>')
        
        ts = obj.time_slot
        return format_html(
            '<div style="padding:10px;background:#f0f7ff;border-left:4px solid #2196F3;border-radius:4px">'
            '<div style="font-weight:bold;font-size:14px;color:#1976D2;margin-bottom:4px">'
            '{}</div>'
            '<div style="color:#555;font-size:13px">{}</div>'
            '</div>',
            ts.date.strftime('%A, %B %d, %Y'),  # e.g., "Monday, September 01, 2026"
            ts.time_label  # e.g., "4:00 pm – 5:00 pm"
        )

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
        no_time_slot = []
        
        for booking in queryset.exclude(status=Appointment.Status.CANCELLED):
            issued.append(f"{booking.name}: {booking.approve()}")
            # Warn if no time slot was selected (old bookings or edge cases)
            if not booking.time_slot:
                no_time_slot.append(booking.name)

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
        
        if no_time_slot:
            # Rare case: booking without a selected time slot
            self.message_user(
                request,
                format_html(
                    "No time slot selected for {} — this may be an old booking "
                    "made before time slot selection was available.",
                    ", ".join(no_time_slot),
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

        The raw Google id means nothing to staff, so it is resolved through
        the mirrored profile to the email they signed up with. An enquiry with
        no account behind it says so plainly rather than showing an empty field
        -- that state is real (the form is offered to signed-in visitors, but
        the endpoint still accepts a message without a token) and staff should
        be able to tell the two apart.
        """
        if not obj.google_user_id:
            return "Not signed in"

        profile = (
            GoogleProfile.objects.filter(google_user_id=obj.google_user_id)
            .select_related("user")
            .first()
        )
        if profile is None:
            # Signed in on a token whose account was never mirrored — only
            # possible if the mirror lost a race and both branches failed.
            return f"Account {obj.google_user_id[-8:]}"
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


class GoogleProfileInline(admin.StackedInline):
    """What Google told us about this customer, shown on the user it belongs to.

    Read-only throughout: Google owns these records, and a value edited here
    would be overwritten the next time that customer signs in and books.

    Thinner than the Clerk inline it replaces, and necessarily so. Clerk had a
    back-end API this project could call to list every account with its
    provider, phone and ban state; Google has no equivalent. Everything here
    comes from the claims in a session token, so what is not in a token is not
    a column.
    """

    model = GoogleProfile
    can_delete = False
    extra = 0
    verbose_name_plural = "Google account"
    readonly_fields = (
        "google_user_id",
        "avatar",
        "email_verified",
        "last_seen_at",
        "image_url",
    )
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Avatar")
    def avatar(self, obj):
        if not obj.image_url:
            return "— none —"
        return format_html(
            '<img src="{}" style="height:72px;width:72px;border-radius:50%;object-fit:cover">',
            obj.image_url,
        )


class GoogleUserAdmin(BaseUserAdmin):
    """Django's user admin, plus who signed in with Google."""

    inlines = [*BaseUserAdmin.inlines, GoogleProfileInline]
    list_display = (
        "username",
        "email",
        "full_name",
        "signed_in_with",
        "signed_up",
        "last_seen",
        "is_staff",
    )
    # Filtering on the presence of a profile is the useful cut now that there
    # is only ever one provider: it separates customers from staff accounts.
    list_filter = (*BaseUserAdmin.list_filter, "google_profile__email_verified")
    search_fields = (
        "username",
        "email",
        "first_name",
        "last_name",
        "google_profile__google_user_id",
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("google_profile")

    @admin.display(description="Name", ordering="first_name")
    def full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip() or "—"

    @admin.display(description="Signed in with")
    def signed_in_with(self, obj):
        profile = getattr(obj, "google_profile", None)
        if profile is None:
            # Staff accounts made with createsuperuser have no Google record.
            return format_html('<span style="color:#888">Django login</span>')
        return format_html('<b style="color:#2e7d32">Google</b>')

    @admin.display(description="Signed up", ordering="google_profile__created_at")
    def signed_up(self, obj):
        profile = getattr(obj, "google_profile", None)
        return profile.created_at if profile else None

    @admin.display(description="Last seen", ordering="google_profile__last_seen_at")
    def last_seen(self, obj):
        profile = getattr(obj, "google_profile", None)
        return profile.last_seen_at if profile else None


# Replace Django's registration so Users keeps its place in the sidebar under
# Authentication and Authorization, rather than adding a second list elsewhere.
admin.site.unregister(User)
admin.site.register(User, GoogleUserAdmin)
