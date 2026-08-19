from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from common.admin import SingletonAdmin
from common.admin_ajax import AdminAjaxMixin, admin_json_view
from common.email_config import active_config
from common.mail_test import send_test_message
from common.utils import resolve_image
from core.models import EmailSettings, NavLink, SiteSettings, SocialLink

#: The header's fixed logo box, mirroring `--nav-logo-*` in globals.css. Only
#: the preview below reads these — the site itself takes them from the
#: stylesheet — but they have to agree, or the preview stops being a preview.
LOGO_HEIGHT_PX = 96
LOGO_MAX_WIDTH_PX = 360


@admin.register(SiteSettings)
class SiteSettingsAdmin(SingletonAdmin):
    """The one form where the header is assembled, so it shows its own result.

    `navbar_preview` is a mock of the real bar rather than a thumbnail of the
    uploaded file, because the question being answered here is never "what did I
    upload" — it is "does that read next to the links". A mark can look fine on
    its own and be illegible at 96px in a nav row, and only one of those is what
    visitors see. `static/admin/navbar-preview.js` swaps in a newly chosen file
    before it is saved, so that answer arrives while there is still time to pick
    a different one.

    There is deliberately no size control. The logo is drawn at a fixed height
    the way every other site's is, so the header keeps the height the rest of
    the page is laid out against.
    """

    readonly_fields = ("navbar_preview",)

    class Media:
        js = ("admin/navbar-preview.js",)

    fieldsets = (
        (
            "Navbar preview",
            {
                "fields": ("navbar_preview",),
                "description": (
                    "How the header will look. Choose a logo below and it "
                    "updates straight away — no need to save first."
                ),
            },
        ),
        (
            "Brand",
            {
                "fields": ("logo", "logo_url", "brand_name", "badge_caption"),
                "description": (
                    "Upload a logo and the header, the mobile menu and the "
                    "circular badge all show it in place of the brand name. "
                    "Clear it and they go back to the brand name as text — "
                    "which is also the logo's label for screen readers, so "
                    "leave it filled in either way."
                ),
            },
        ),
        ("Search & sharing", {"fields": ("meta_title", "meta_description")}),
        ("Header call to action", {"fields": ("nav_cta_label", "nav_cta_href")}),
        ("Footer", {"fields": ("copyright_text",)}),
    )

    @admin.display(description="")
    def navbar_preview(self, obj):
        if obj is None or obj.pk is None:
            return mark_safe('<span class="salon-preview--empty">Save first</span>')

        logo = resolve_image(obj, "logo", "logo_url")
        links = NavLink.objects.filter(
            is_published=True, show_in_header=True
        ).order_by("order", "pk")

        # Both marks are rendered and one is hidden, so the JS can switch
        # between them the moment a logo is chosen or cleared -- it has no way
        # to build an <img> for a file the browser has not uploaded yet.
        return format_html(
            '<div class="salon-navbar" data-navbar-preview data-logo="{logo}">'
            '<div class="salon-navbar__bar">'
            '<span class="salon-navbar__mark">'
            '<img class="salon-navbar__logo" src="{logo}" alt=""'
            ' style="height:{height}px;max-width:{width}px;{logo_hidden}">'
            '<span class="salon-navbar__wordmark" style="{text_hidden}">{brand}</span>'
            "</span>"
            '<span class="salon-navbar__links">{links}</span>'
            '<span class="salon-navbar__cta">{cta}</span>'
            "</div>"
            "</div>",
            logo=logo,
            height=LOGO_HEIGHT_PX,
            width=LOGO_MAX_WIDTH_PX,
            logo_hidden="" if logo else "display:none",
            text_hidden="display:none" if logo else "",
            brand=obj.brand_name,
            links=format_html_join(
                "", '<span class="salon-navbar__link">{}</span>',
                ((link.label,) for link in links),
            ),
            cta=obj.nav_cta_label,
        )


@admin.register(NavLink)
class NavLinkAdmin(AdminAjaxMixin, admin.ModelAdmin):
    # `list_editable` stays exactly as it was — it is the path for anyone
    # without JavaScript, and the AJAX toggle keeps the database and the
    # checkbox in agreement, so a later "Save" is a no-op either way.
    ajax_toggle_fields = ("show_in_header", "show_in_footer", "is_published")

    list_display = ("label", "href", "show_in_header", "show_in_footer", "order", "is_published")
    list_editable = ("href", "show_in_header", "show_in_footer", "order", "is_published")
    list_filter = ("show_in_header", "show_in_footer", "is_published")
    search_fields = ("label", "href")
    ordering = ("order", "pk")


@admin.register(SocialLink)
class SocialLinkAdmin(AdminAjaxMixin, admin.ModelAdmin):
    ajax_toggle_fields = ("is_published",)

    list_display = ("platform", "url", "order", "is_published")
    list_editable = ("url", "order", "is_published")
    list_filter = ("platform", "is_published")
    ordering = ("order", "pk")


class EmailSettingsForm(forms.ModelForm):
    """Keeps the stored password out of the page it is edited on.

    Rendering it into a `value=` attribute would put a working Gmail
    credential into the HTML of every admin page load, into the browser's
    autofill, and into any proxy log along the way. So the field renders empty
    and an empty submission means "leave it alone" -- which also makes editing
    the sender name a one-field change rather than a re-type of the password.
    """

    password = forms.CharField(
        label="App password",
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text=EmailSettings._meta.get_field("password").help_text,
    )

    class Meta:
        model = EmailSettings
        fields = "__all__"

    def clean_password(self):
        submitted = (self.cleaned_data.get("password") or "").strip()
        if not submitted:
            # Unchanged. self.instance still holds the decrypted original.
            return self.instance.password if self.instance.pk else ""
        # Google displays an App Password as four groups of four and people
        # paste it that way; the spaces are presentation, and leaving them in
        # produces an auth failure that reads exactly like a wrong password.
        return submitted.replace(" ", "")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("is_enabled"):
            missing = [
                label
                for field, label in (("username", "Gmail address"), ("password", "App password"))
                if not cleaned.get(field)
            ]
            if missing:
                raise forms.ValidationError(
                    "Fill in the "
                    + " and ".join(missing)
                    + ' before switching "Send emails" on, or nothing will be sent.'
                )
        return cleaned


@admin.register(EmailSettings)
class EmailSettingsAdmin(AdminAjaxMixin, SingletonAdmin):
    """Where the salon sets up the Gmail account the site sends from.

    The status panel at the top is the part that earns its place. Every field
    here can look filled in and correct while mail silently fails -- a revoked
    App Password, 2-Step Verification switched off, a host blocking port 587 --
    and none of that is visible from the form. So the screen reports what
    happened the last time a real message was attempted, and offers a button
    to attempt one now.
    """

    form = EmailSettingsForm
    readonly_fields = ("status",)

    fieldsets = (
        (
            "Status",
            {
                "fields": ("status",),
                "description": mark_safe(
                    "Save this page, then use <b>Send test email</b> at the "
                    "bottom to check the settings actually work."
                ),
            },
        ),
        (
            "Gmail account",
            {
                "fields": ("is_enabled", "username", "password", "from_name"),
                "description": mark_safe(
                    "The password is <b>not</b> your Gmail password — Google "
                    "refuses those. Create a 16-character App Password at "
                    '<a href="https://myaccount.google.com/apppasswords" '
                    'target="_blank" rel="noopener">myaccount.google.com/apppasswords</a>'
                    " (it needs 2-Step Verification on the account first)."
                ),
            },
        ),
        (
            "Notifications",
            {
                "fields": ("notify_emails",),
                "description": (
                    "Who is told when a booking or an enquiry arrives. "
                    "Bookings and enquiries are saved either way — this only "
                    "controls the email."
                ),
            },
        ),
        (
            "Server (advanced)",
            {
                "fields": ("host", "port", "security"),
                "classes": ("collapse",),
                "description": mark_safe(
                    "<b>Nothing here needs filling in for Gmail.</b> Leave "
                    "the server and port blank and leave Security on "
                    "STARTTLS — those are already the right answers. The "
                    "asterisk on Security only means the dropdown must have "
                    "one of its options chosen, and it already does. These "
                    "fields exist so that moving to a different mail provider "
                    "later is an edit here rather than a code change."
                ),
            },
        ),
    )

    @admin.display(description="Current state")
    def status(self, obj):
        config = active_config()
        rows = []

        if not obj or not obj.pk:
            rows.append(("Not saved yet", "Fill in the account below and save.", "warn"))
        elif not obj.is_enabled:
            rows.append(
                (
                    "Emails are off",
                    "Bookings and enquiries are still saved; nothing is sent.",
                    "warn",
                )
            )
        elif not config.is_configured:
            rows.append(
                (
                    "Not sending",
                    "No address and password, so mail is written to the server "
                    "log instead of sent.",
                    "warn",
                )
            )
        else:
            rows.append(
                (
                    "Sending",
                    "Using {} via {}:{}.".format(
                        config.username, config.host, config.port
                    ),
                    "ok",
                )
            )

        rows.append(
            (
                "Settings come from",
                "this screen" if config.source == "admin" else "the .env file",
                "info",
            )
        )
        rows.append(
            (
                "Notifications go to",
                ", ".join(config.recipients) or "nobody — no address set",
                "info" if config.recipients else "warn",
            )
        )

        if obj and obj.pk and obj.last_test_at:
            when = timezone.localtime(obj.last_test_at).strftime("%d %b %Y, %H:%M")
            rows.append(
                (
                    "Last test",
                    "{} — {}".format(when, obj.last_test_detail or "sent"),
                    "ok" if obj.last_test_ok else "bad",
                )
            )
        else:
            rows.append(("Last test", "never run", "info"))

        # Tokens rather than hex, because this panel is read in both themes:
        # the amber and grey that used to be here were close to illegible on
        # the dark surface. CSS variables resolve fine inside a style attribute.
        colours = {
            "ok": "var(--salon-accent-text)",
            "warn": "var(--salon-warning-text)",
            "bad": "var(--salon-destructive)",
            "info": "var(--salon-muted)",
        }
        html = format_html_join(
            "",
            '<tr><th style="text-align:left;padding:4px 16px 4px 0;font-weight:600;'
            'white-space:nowrap">{}</th>'
            '<td style="padding:4px 0;color:{}">{}</td></tr>',
            ((label, colours[tone], value) for label, value, tone in rows),
        )
        # The wrapper is the AJAX swap target. Deliberately our own hook rather
        # than `.field-status .readonly`, which is Jazzmin's markup and would
        # make this break on an upgrade that restructured a fieldset.
        return format_html(
            '<div data-salon-panel="status">'
            '<table style="border-collapse:collapse">{}</table>'
            "</div>",
            html,
        )

    def get_urls(self):
        return [
            path(
                "send-test-email/",
                self.admin_site.admin_view(self.send_test_email_view),
                name="core_emailsettings_send_test",
            ),
            *super().get_urls(),
        ]

    def get_ajax_urls(self):
        return [
            path(
                "send-test-email/json/",
                self.send_test_email_json_view,
                name="core_emailsettings_send_test_json",
            ),
            *super().get_ajax_urls(),
        ]

    def _run_test_email(self, request):
        """Send one test message and record the outcome. Returns (level, text).

        Shared by the form-post view and the JSON one for the same reason
        `common/mail_test.py` is shared by the button and the management
        command: two ways of asking the same question must not be able to
        disagree about the answer.
        """
        obj = EmailSettings.objects.first()
        if obj is None:
            return messages.WARNING, "Save the settings first."

        config = active_config()
        target = config.recipients[0] if config.recipients else config.username
        if not target:
            return (
                messages.ERROR,
                "There is no address to send to. Fill in the Gmail address first.",
            )

        ok, detail = send_test_message(target)
        obj.last_test_at = timezone.now()
        obj.last_test_ok = ok
        obj.last_test_detail = detail
        obj.save(update_fields=["last_test_at", "last_test_ok", "last_test_detail"])

        if ok:
            return (
                messages.SUCCESS,
                "Test email sent to {}. Check the inbox (and spam).".format(target),
            )
        return messages.ERROR, "Could not send: {}".format(detail)

    def send_test_email_view(self, request):
        """Attempt one real message and record what happened.

        The no-JavaScript path, unchanged: a POST, then a redirect back here.
        A GET that sends is wrong, so this only acts on POST.
        """
        obj = EmailSettings.objects.first()
        redirect_to = reverse("admin:core_emailsettings_change", args=[obj.pk]) if obj else reverse("admin:index")

        if request.method != "POST":
            return HttpResponseRedirect(redirect_to)

        level, text = self._run_test_email(request)
        self.message_user(request, text, level)
        return HttpResponseRedirect(redirect_to)

    @admin_json_view
    def send_test_email_json_view(self, request, body):
        """The same send, answered in place.

        Sends can take up to EMAIL_TIMEOUT (10s) and used to freeze the page
        for all of it, to deliver one message and a refreshed table. Both come
        back here instead: the message through the decorator's drain, and the
        table as re-rendered HTML for the panel to swap in.
        """
        level, text = self._run_test_email(request)
        self.message_user(request, text, level)

        obj = EmailSettings.objects.first()
        return {"panels": {"status": self.status(obj)}}

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = {
            **(extra_context or {}),
            "send_test_url": reverse("admin:core_emailsettings_send_test"),
            "send_test_json_url": reverse("admin:core_emailsettings_send_test_json"),
        }
        return super().change_view(request, object_id, form_url, extra_context)

    change_form_template = "admin/core/emailsettings/change_form.html"
