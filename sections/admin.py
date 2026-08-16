from django.contrib import admin
from django.utils.html import format_html, format_html_join

from common.admin import ColorInput, ImagePreviewMixin, SingletonAdmin
from sections.models import (
    AboutColumn,
    AboutColumnItem,
    AboutSection,
    AboutStat,
    AsSeenOnSection,
    ClassCard,
    ClassesSection,
    ContactColumn,
    FollowUsSection,
    FooterSection,
    GalleryImage,
    GallerySection,
    HeroSection,
    MotivationLine,
    MotivationSection,
    OurStorySection,
    Service,
    TeamMember,
    WhoWeAreSection,
)


@admin.register(HeroSection)
class HeroSectionAdmin(ImagePreviewMixin, SingletonAdmin):
    # Only the photo that actually matters is previewed. The backdrop and the
    # cape mark are optional extras and live in a collapsed section below.
    preview_fields = [("stylist_image", "stylist_image_url")]
    readonly_fields = ("preview", "swatches")
    fieldsets = (
        ("Copy", {"fields": ("eyebrow", "headline_line_1", "headline_line_2", "body")}),
        (
            "Buttons",
            {
                "fields": (
                    ("primary_cta_label", "primary_cta_href"),
                    ("secondary_cta_label", "secondary_cta_href"),
                )
            },
        ),
        (
            "Main photo",
            {
                "fields": ("preview", "stylist_image", "stylist_image_alt"),
                "description": (
                    "The person on the right-hand side of the hero. This is the "
                    "only image the hero needs — upload one here and you are "
                    "done. A cut-out on a transparent background (PNG) sits "
                    "best; a normal photo works too."
                ),
            },
        ),
        (
            "Colours",
            {
                "fields": (
                    "swatches",
                    "background_color",
                    "heading_color",
                    "body_color",
                    "eyebrow_color",
                    ("primary_button_bg", "primary_button_text"),
                    "secondary_button_color",
                ),
                "description": (
                    "Any CSS colour works. Each field's help text carries its "
                    "own default in brackets — paste that value back to undo a "
                    "change."
                ),
            },
        ),
        (
            "Optional extras",
            {
                "classes": ("collapse",),
                "fields": (
                    "stylist_image_url",
                    ("background_image", "background_image_url"),
                    ("watermark_image", "watermark_image_url"),
                ),
                "description": (
                    "None of this is required. <br>"
                    "<b>Main photo URL</b> — only if the photo lives on another "
                    "site instead of being uploaded above. <br>"
                    "<b>Background image</b> — a texture behind the whole hero. "
                    "Empty means a plain black band, which is how it looks "
                    "now. <br>"
                    "<b>Watermark</b> — the small logo printed on the cape in "
                    "the photo."
                ),
            },
        ),
    )


    # Every colour column gets the picker + hex pair.
    formfield_overrides = {}

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name in {name for name, _ in self.COLOUR_FIELDS}:
            kwargs["widget"] = ColorInput
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    COLOUR_FIELDS = (
        ("background_color", "Background"),
        ("heading_color", "Headline"),
        ("body_color", "Body copy"),
        ("eyebrow_color", "Eyebrow"),
        ("primary_button_bg", "Button 1 fill"),
        ("primary_button_text", "Button 1 text"),
        ("secondary_button_color", "Button 2"),
    )

    @admin.display(description="In use now")
    def swatches(self, obj):
        """Renders the stored colours, so a typo shows up before saving twice."""
        if obj is None or obj.pk is None:
            return "Save first"
        return format_html_join(
            "",
            '<div style="display:inline-block;margin:0 14px 8px 0;text-align:center">'
            '<div style="width:46px;height:46px;border-radius:6px;border:1px solid #999;'
            'background:{}"></div>'
            '<div style="font-size:11px;margin-top:4px">{}</div>'
            '<div style="font-size:10px;color:#666">{}</div></div>',
            ((getattr(obj, f), label, getattr(obj, f)) for f, label in self.COLOUR_FIELDS),
        )


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    """The real Service admin — registered, but hidden from the index.

    It has to stay registered: `AppointmentAdmin.autocomplete_fields` resolves
    the admin of the *related* model, and unregistering this one fails
    admin.E039. `get_model_perms` returning {} is the supported way to keep the
    registration and its URLs while dropping the entry from the app list; the
    visible entry is the `bookings.Service` proxy, under Enquiries.
    """

    def get_model_perms(self, request):
        return {}

    list_display = ("label", "icon", "price_from", "order", "is_published")
    list_editable = ("icon", "price_from", "order", "is_published")
    list_filter = ("icon", "is_published")
    search_fields = ("label", "description")
    ordering = ("order", "pk")
    fieldsets = (
        ("Service", {"fields": ("label", "description", "price_from", "href")}),
        (
            "Photo",
            {
                "fields": ("image", "image_url"),
                "description": (
                    "Shown on the card in the booking form's first step. "
                    "Upload a file, or paste a URL below it — an upload wins "
                    "when both are set. This is NOT the icon: the drawn glyph "
                    "in the landing page's Service Menu row is set separately."
                ),
            },
        ),
        (
            "Icon",
            {
                "fields": ("icon", "icon_image"),
                "description": (
                    "The line drawing in the Service Menu row on the landing "
                    "page. Only the five glyphs from the design exist; upload "
                    "an image to override the choice."
                ),
            },
        ),
        ("Placement", {"fields": (("order", "is_published"),)}),
    )


class MotivationLineInline(admin.TabularInline):
    model = MotivationLine
    extra = 1
    fields = ("text", "order", "is_published")
    ordering = ("order", "pk")


@admin.register(MotivationSection)
class MotivationSectionAdmin(SingletonAdmin):
    inlines = [MotivationLineInline]
    fields = ("is_published",)


class GalleryImageInline(admin.TabularInline):
    model = GalleryImage
    extra = 0
    fields = ("alt", "image", "image_url", "order", "is_published")
    ordering = ("order", "pk")


@admin.register(GallerySection)
class GallerySectionAdmin(SingletonAdmin):
    inlines = [GalleryImageInline]
    fields = ("heading", "body", ("cta_label", "cta_href"), "is_published")


class ClassCardInline(admin.TabularInline):
    model = ClassCard
    extra = 0
    fields = ("name", "slug", "href", "image", "image_url", "order", "is_published")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("order", "pk")


@admin.register(ClassesSection)
class ClassesSectionAdmin(SingletonAdmin):
    inlines = [ClassCardInline]
    fields = (("heading_top", "heading_bottom"), "marquee_phrase")


@admin.register(ClassCard)
class ClassCardAdmin(ImagePreviewMixin, admin.ModelAdmin):
    list_display = ("__str__", "href", "order", "is_published")
    list_editable = ("href", "order", "is_published")
    list_filter = ("is_published",)
    search_fields = ("name", "slug")
    ordering = ("order", "pk")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("preview",)
    fields = (
        "section",
        "name",
        "slug",
        "href",
        "preview",
        ("image", "image_url"),
        ("order", "is_published"),
    )


@admin.register(OurStorySection)
class OurStorySectionAdmin(ImagePreviewMixin, SingletonAdmin):
    readonly_fields = ("preview",)
    fields = (
        "heading",
        "body",
        ("cta_label", "cta_href"),
        "preview",
        ("image", "image_url"),
        "image_alt",
    )


@admin.register(AsSeenOnSection)
class AsSeenOnSectionAdmin(SingletonAdmin):
    fields = ("heading", "quote", "attribution", ("cta_label", "cta_href"))


@admin.register(FollowUsSection)
class FollowUsSectionAdmin(SingletonAdmin):
    fields = ("heading", "body")


@admin.register(ContactColumn)
class ContactColumnAdmin(admin.ModelAdmin):
    list_display = ("heading", "icon", "order", "is_published")
    list_editable = ("icon", "order", "is_published")
    ordering = ("order", "pk")
    fields = ("heading", "icon", "body", ("order", "is_published"))


@admin.register(FooterSection)
class FooterSectionAdmin(SingletonAdmin):
    fieldsets = (
        (
            "Animated headline",
            {
                "fields": ("heading_line1", "heading_line2", "heading_line3"),
                "description": (
                    "The three big lines at the top of the footer. Each one "
                    "slides in from a different side as you scroll, which is "
                    "why they are three fields and not one — the break is a "
                    "design decision, not a wrap."
                ),
            },
        ),
        ("Contact block", {"fields": ("contact_heading", "contact_body", "email", "phone")}),
        ("Call to action", {"fields": ("cta_label", "cta_href")}),
    )


@admin.register(WhoWeAreSection)
class WhoWeAreSectionAdmin(SingletonAdmin):
    fieldsets = (
        (
            "Animated heading",
            {
                "fields": ("heading_line_1", "heading_line_2"),
                "description": (
                    "Two lines because each slides in from a different side as "
                    "you scroll, resolving letter by letter."
                ),
            },
        ),
        ("Copy", {"fields": ("lead", "body")}),
        ("Call to action", {"fields": ("cta_label", "cta_href")}),
        ("Placement", {"fields": ("is_published",)}),
    )


# --- About Us --------------------------------------------------------------


class AboutStatInline(admin.TabularInline):
    model = AboutStat
    extra = 0
    fields = ("value", "label", "order", "is_published")
    ordering = ("order", "pk")


class TeamMemberInline(admin.TabularInline):
    model = TeamMember
    extra = 0
    fields = (
        "name",
        "role",
        "image",
        "image_url",
        "facebook_url",
        "twitter_url",
        "youtube_url",
        "order",
        "is_published",
    )
    ordering = ("order", "pk")


class AboutColumnInline(admin.TabularInline):
    """Headings, prose, and a read-only look at the bullets.

    A column is either prose (`body`) or a bullet list (`items`), so for the
    bullet columns `body` is legitimately blank -- which read as missing data
    until the bullets were shown here too. Django admin does not nest an inline
    inside an inline, so they are printed rather than edited: the pencil at the
    end of the row opens the column, where AboutColumnItemInline edits them.
    """

    model = AboutColumn
    extra = 0
    fields = ("heading", "body", "bullets", "order", "is_published")
    readonly_fields = ("bullets",)
    ordering = ("order", "pk")
    show_change_link = True

    def get_queryset(self, request):
        # One query for every column's bullets rather than one per row.
        return super().get_queryset(request).prefetch_related("items")

    @admin.display(description="Bullets (edit via the pencil)")
    def bullets(self, obj):
        # Unsaved rows added with "Add another" have no pk to follow yet.
        if obj.pk is None:
            return "Save the column first, then add bullets."
        items = list(obj.items.all())
        if not items:
            return "— none — this column uses the Body box instead."
        return format_html_join(
            "", "<div>• {}</div>", ((item.text,) for item in items)
        )


@admin.register(AboutSection)
class AboutSectionAdmin(ImagePreviewMixin, SingletonAdmin):
    preview_fields = [("hero_bg_image", "hero_bg_image_url")]
    readonly_fields = ("preview",)
    inlines = [AboutColumnInline, AboutStatInline, TeamMemberInline]
    fieldsets = (
        (
            "Intro",
            {
                "fields": (
                    "eyebrow",
                    ("heading_line_1", "heading_line_2"),
                    "intro_body",
                ),
                "description": (
                    "Write {years} anywhere in this copy and it is replaced by "
                    "how long the salon has been open, worked out from the year "
                    "below. That way the number never goes stale."
                ),
            },
        ),
        ("Open since", {"fields": ("established_year",)}),
        (
            "Scroll hero",
            {
                "fields": (
                    "hero_title",
                    "hero_date",
                    "hero_scroll_prompt",
                    "hero_video",
                    "hero_video_url",
                    "preview",
                    "hero_bg_image",
                    "hero_bg_image_url",
                ),
                "description": (
                    "Three separate slots. The background image fills the "
                    "screen on arrival and fades out as the visitor scrolls, "
                    "and also stands in for the video while it loads. The "
                    "video is the clip that expands."
                ),
            },
        ),
        ("Team heading", {"fields": ("team_heading", "team_body")}),
        (
            "Closing call to action",
            {
                "fields": (
                    ("cta_heading_lead", "cta_heading_accent"),
                    "cta_body",
                    ("cta_primary_label", "cta_primary_href"),
                    ("cta_secondary_label", "cta_secondary_href"),
                )
            },
        ),
        ("Instagram strip", {"fields": ("instagram_handle",)}),
    )


class AboutColumnItemInline(admin.TabularInline):
    model = AboutColumnItem
    extra = 0
    fields = ("text", "order", "is_published")
    ordering = ("order", "pk")


@admin.register(AboutColumn)
class AboutColumnAdmin(admin.ModelAdmin):
    inlines = [AboutColumnItemInline]
    list_display = ("heading", "bullet_count", "order", "is_published")
    list_editable = ("order", "is_published")
    fields = ("section", "heading", "body", "order", "is_published")

    @admin.display(description="Bullets")
    def bullet_count(self, obj):
        return obj.items.count()


@admin.register(AboutColumnItem)
class AboutColumnItemAdmin(admin.ModelAdmin):
    """Every bullet on the About page, in one editable list.

    The bullets are also reachable through their column, but only by knowing to
    open it first. This gives them a sidebar entry of their own so the wording
    on the live page can be found and changed without that hop.
    """

    # `column` leads so it is the link to the parent, which frees `text` to be
    # edited in place -- Django forbids list_editable on the linked column.
    list_display = ("column", "text", "order", "is_published")
    list_display_links = ("column",)
    list_editable = ("text", "order", "is_published")
    list_filter = ("column", "is_published")
    search_fields = ("text",)
    ordering = ("column", "order", "pk")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("column")
