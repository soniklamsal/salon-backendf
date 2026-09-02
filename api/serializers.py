"""Read serializers for the landing page, plus the two write serializers.

Every section serializer is shaped for the React component that renders it, not
for the table behind it — buttons come through as `{label, href}`, images as one
resolved URL, and multi-line copy as an array of lines.
"""

from django.db.models import Prefetch
from rest_framework import serializers
from rest_framework.reverse import reverse

from bookings.models import Appointment, Barber, BookingSection, ContactMessage, TimeSlot
from common.serializers import CamelCaseModelSerializer, ImageURLField, LinkField
from common.storage import screenshot_token
from common.validators import validate_phone, validate_upload
from core.models import NavLink, SiteSettings, SocialLink
from sections.models import (
    AboutColumn,
    AboutColumnItem,
    AboutSection,
    AboutStat,
    AsSeenOnSection,
    ClassCard,
    ClassesSection,
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


# --- Site ------------------------------------------------------------------


class SiteSettingsSerializer(CamelCaseModelSerializer):
    nav_cta = LinkField("nav_cta_label", "nav_cta_href")
    # "" when neither the upload nor the override is set, which is what the
    # header reads as "no logo, draw the wordmark instead".
    logo = ImageURLField("logo", "logo_url")

    class Meta:
        model = SiteSettings
        fields = [
            "logo",
            "brand_name",
            "badge_caption",
            "meta_title",
            "meta_description",
            "nav_cta",
            "copyright_text",
        ]


class NavLinkSerializer(CamelCaseModelSerializer):
    class Meta:
        model = NavLink
        fields = ["id", "label", "href", "show_in_header", "show_in_footer", "order"]


class SocialLinkSerializer(CamelCaseModelSerializer):
    label = serializers.CharField(source="accessible_label", read_only=True)

    class Meta:
        model = SocialLink
        fields = ["id", "platform", "url", "label", "order"]


# --- Sections --------------------------------------------------------------


class HeroSerializer(CamelCaseModelSerializer):
    primary_cta = LinkField("primary_cta_label", "primary_cta_href")
    secondary_cta = LinkField("secondary_cta_label", "secondary_cta_href")
    background_image = ImageURLField("background_image", "background_image_url")
    stylist_image = ImageURLField("stylist_image", "stylist_image_url")
    watermark_image = ImageURLField("watermark_image", "watermark_image_url")

    class Meta:
        model = HeroSection
        fields = [
            "eyebrow",
            "headline_line_1",
            "headline_line_2",
            "body",
            "primary_cta",
            "secondary_cta",
            "background_image",
            "stylist_image",
            "stylist_image_alt",
            "watermark_image",
            "background_color",
            "heading_color",
            "body_color",
            "eyebrow_color",
            "primary_button_bg",
            "primary_button_text",
            "secondary_button_color",
        ]


class ServiceSerializer(CamelCaseModelSerializer):
    icon_image = ImageURLField("icon_image", None)
    image = ImageURLField("image", "image_url")

    class Meta:
        model = Service
        fields = [
            "id",
            "label",
            "icon",
            "icon_image",
            "image",
            "href",
            "description",
            "price_from",
            "order",
        ]


class WhoWeAreSerializer(CamelCaseModelSerializer):
    cta = LinkField("cta_label", "cta_href")

    class Meta:
        model = WhoWeAreSection
        fields = [
            "heading_line_1",
            "heading_line_2",
            "lead",
            "body",
            "cta",
            "is_published",
        ]


class MotivationSerializer(CamelCaseModelSerializer):
    lines = serializers.SerializerMethodField()

    class Meta:
        model = MotivationSection
        fields = ["is_published", "lines"]

    def get_lines(self, obj):
        return list(
            MotivationLine.objects.filter(is_published=True).values_list("text", flat=True)
        )


class GalleryImageSerializer(CamelCaseModelSerializer):
    image = ImageURLField("image", "image_url")

    class Meta:
        model = GalleryImage
        fields = ["id", "image", "alt", "order"]


class GallerySerializer(CamelCaseModelSerializer):
    cta = LinkField("cta_label", "cta_href")
    lines = serializers.ListField(child=serializers.CharField(), read_only=True)
    images = serializers.SerializerMethodField()

    class Meta:
        model = GallerySection
        fields = ["heading", "lines", "cta", "images", "is_published"]

    def get_images(self, obj):
        queryset = GalleryImage.objects.filter(is_published=True)
        return GalleryImageSerializer(queryset, many=True, context=self.context).data


class ClassCardSerializer(CamelCaseModelSerializer):
    image = ImageURLField("image", "image_url")
    # `{}` rather than null for a card with no clip, so the frontend branches
    # on one shape instead of two. See ClassCard.video.
    video = serializers.SerializerMethodField()

    class Meta:
        model = ClassCard
        fields = ["id", "slug", "name", "href", "image", "video", "order"]

    def get_video(self, obj) -> dict:
        return obj.video()


class ClassesSerializer(CamelCaseModelSerializer):
    cards = serializers.SerializerMethodField()

    class Meta:
        model = ClassesSection
        fields = ["heading_top", "heading_bottom", "marquee_phrase", "cards"]

    def get_cards(self, obj):
        queryset = ClassCard.objects.filter(is_published=True)
        return ClassCardSerializer(queryset, many=True, context=self.context).data


class OurStorySerializer(CamelCaseModelSerializer):
    cta = LinkField("cta_label", "cta_href")
    image = ImageURLField("image", "image_url")

    class Meta:
        model = OurStorySection
        fields = ["heading", "body", "cta", "image", "image_alt"]


class AsSeenOnSerializer(CamelCaseModelSerializer):
    cta = LinkField("cta_label", "cta_href")

    class Meta:
        model = AsSeenOnSection
        fields = ["heading", "quote", "attribution", "cta"]


class FollowUsSerializer(CamelCaseModelSerializer):
    class Meta:
        model = FollowUsSection
        fields = ["heading", "body"]


class FooterSerializer(CamelCaseModelSerializer):
    cta = LinkField("cta_label", "cta_href")

    class Meta:
        model = FooterSection
        fields = [
            "heading_line1",
            "heading_line2",
            "heading_line3",
            "contact_heading",
            "contact_body",
            "email",
            "phone",
            "cta",
        ]


# --- Enquiries (write) -----------------------------------------------------


class BookingCopySerializer(CamelCaseModelSerializer):
    """The wording of the booking form's four steps, editable in the admin."""

    class Meta:
        model = BookingSection
        fields = [
            "service_heading",
            "barber_heading",
            "details_heading",
            "payment_heading",
            "service_step",
            "barber_step",
            "details_step",
            "payment_step",
            "page_heading",
            "page_intro",
            "submit_label",
            "success_heading",
        ]


class BarberSerializer(CamelCaseModelSerializer):
    """Step 2 of the booking flow — a face before any details are asked for."""

    photo = ImageURLField("photo")

    class Meta:
        model = Barber
        fields = [
            "id",
            "name",
            "role",
            "photo",
            "bio",
            "initials",
            "schedule",
            # Unavailable barbers are still sent. The card shows them with a
            # badge and refuses to be selected, because hiding someone who is
            # merely on holiday reads to a regular customer as "they've left".
            "is_available",
            "availability_label",
            "order",
        ]


class TimeSlotSerializer(CamelCaseModelSerializer):
    """Serializer for time slots - shows availability for booking."""
    
    time_label = serializers.CharField(read_only=True)
    
    class Meta:
        model = TimeSlot
        fields = [
            'id',
            'date',
            'start_time',
            'end_time',
            'time_label',
            'is_booked',
            'order',
        ]


class AppointmentCreateSerializer(serializers.ModelSerializer):
    # No date or time is accepted here, deliberately. The salon decides when a
    # customer comes in and sets it in the admin's Handling section; the
    # customer is told on approval. Accepting a requested slot would put a time
    # on the record that nobody has agreed to, and the status page would then
    # have to explain which of the two times to believe.
    #
    # Required: a booking is a request to hold a chair, and the salon has no
    # way to tell a real one from a prank without proof of payment. The model
    # column stays `blank=True` so a staff member can still add a booking by
    # phone in the admin — this rule is about the public form only.
    # The public form asks for all of these, so the API requires all of them.
    # Every matching model column stays `blank=True`, which is not an oversight:
    # a staff member taking a booking over the phone in the admin has a name and
    # nothing else, and forcing them to invent an address to save the row would
    # be worse than an incomplete record. The rule belongs to the public
    # endpoint, not to the table.
    #
    # Email is the exception — plenty of customers here do not have one, and
    # refusing the booking over it would cost the salon the appointment.
    address = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=255,
        error_messages={
            "required": "Please tell us your address.",
            "blank": "Please tell us your address.",
        },
    )
    phone = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=40,
        error_messages={
            "required": "Please give us a phone number.",
            "blank": "Please give us a phone number.",
        },
    )
    notes = serializers.CharField(
        required=True,
        allow_blank=False,
        error_messages={
            "required": "Please tell us what you would like done.",
            "blank": "Please tell us what you would like done.",
        },
    )
    # Read-only: the customer does not type this. It is taken from the account
    # they signed up with, via the verified Clerk token, and the form shows it
    # as a non-editable field. Accepting one from the body would let a caller
    # attach any address they liked to a booking made from their own account.
    email = serializers.EmailField(read_only=True)

    paymentScreenshot = serializers.ImageField(
        source="payment_screenshot",
        required=True,
        allow_null=False,
        # Write-only because the file now lives in private storage, which
        # refuses to produce a URL — echoing the field back in the 201 would
        # raise on every successful booking. The customer does not need it
        # either: they reach it through /bookings/<reference>/screenshot/.
        write_only=True,
        # Repeated from the model field on purpose. A model field's validators
        # only run on `full_clean()`, which ModelSerializer does not call — so
        # the model's copy guards the admin and this one guards the API.
        validators=[validate_upload],
        error_messages={
            "required": "Please upload a screenshot of your payment.",
            "invalid_image": "That file is not an image we can read.",
        },
    )

    class Meta:
        model = Appointment
        fields = [
            "id",
            "name",
            "email",
            "phone",
            "address",
            "service",
            "barber",
            "time_slot",  # Add time_slot field
            "notes",
            "paymentScreenshot",
            # Read-only: assigned by the model, echoed back so the customer
            # sees the code they will be asked to quote.
            "reference",
            "status",
        ]
        read_only_fields = ["reference", "status"]

    def validate_name(self, value):
        return self._required_text(value, "Please tell us your name.")

    def validate_address(self, value):
        return self._required_text(value, "Please tell us your address.")

    def validate_notes(self, value):
        return self._required_text(value, "Please tell us what you would like done.")

    @staticmethod
    def _required_text(value: str, message: str) -> str:
        # `allow_blank=False` rejects "" but happily accepts "   ", which is
        # the same empty field as far as the salon is concerned. Trimmed on the
        # way in so the stored record is not padded either.
        cleaned = (value or "").strip()
        if not cleaned:
            raise serializers.ValidationError(message)
        return cleaned

    def validate_service(self, value):
        if value is not None and not value.is_published:
            raise serializers.ValidationError("That service is not currently offered.")
        return value

    def validate_phone(self, value):
        cleaned = self._required_text(value, "Please give us a phone number.")
        # Same reason as the model's copy: a ModelSerializer does not call
        # full_clean(), so the model validator guards the admin and this one
        # guards the API.
        validate_phone(cleaned)
        return cleaned

    def validate_barber(self, value):
        # The counterpart to validate_service, which existed while this did
        # not: the browser only ever offers published, available barbers, but
        # the endpoint is public and nothing stopped a caller naming one who
        # has left or is away.
        if value is None:
            return value
        if not value.is_published:
            raise serializers.ValidationError("That barber is not taking bookings.")
        if not value.is_available:
            raise serializers.ValidationError(
                f"{value.name} is not available at the moment. "
                "Please choose another barber."
            )
        return value


class ContactMessageCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactMessage
        fields = ["id", "name", "email", "subject", "message"]
        read_only_fields = ["id"]


class MyBookingSerializer(CamelCaseModelSerializer):
    """One of the signed-in customer's own bookings, with the order detail.

    Read-only and deliberately narrow: it is served to the person who made the
    booking, so it carries what they need to recognise and quote it, and
    nothing about anyone else.
    """

    service = serializers.CharField(source="service.label", default="", read_only=True)
    barber = serializers.CharField(source="barber.name", default="", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    
    # Selected time slot information
    selected_time_slot = serializers.SerializerMethodField()
    
    # Not the file's own URL — it no longer has a reachable one. This points at
    # the view that checks the caller owns the booking before producing it.
    payment_screenshot = serializers.SerializerMethodField()
    
    def get_selected_time_slot(self, obj):
        """Return the customer's selected time slot info."""
        if not obj.time_slot:
            return None
        
        ts = obj.time_slot
        return {
            "date": ts.date.isoformat() if ts.date else None,
            "timeLabel": ts.time_label,  # camelCase for frontend
            "startTime": ts.start_time.isoformat() if ts.start_time else None,
            "endTime": ts.end_time.isoformat() if ts.end_time else None,
        }

    def get_payment_screenshot(self, obj) -> str:
        """The authorising endpoint, carrying a signed token.

        This serializer is only ever reached through `my_bookings`, which has
        already matched the booking against a verified Clerk session — so
        minting the token here is handing it to someone who has just proved
        the booking is theirs. The token is what lets the `<img>` that follows
        load it, since a browser sends no Authorization header for those.
        """
        if not obj.payment_screenshot:
            return ""
        url = reverse(
            "payment-screenshot",
            kwargs={"reference": obj.reference},
            request=self.context.get("request"),
        )
        return f"{url}?token={screenshot_token(obj.reference)}"

    class Meta:
        model = Appointment
        fields = [
            "id",
            "reference",
            "order_id",
            "status",
            "status_label",
            "service",
            "barber",
            "name",
            "address",
            "notes",
            "payment_screenshot",
            # Customer's selected time slot
            "selected_time_slot",
            # The one and only time on this record: what the salon set in the
            # admin. Null until the booking is approved (or can be set by admin)
            "scheduled_date",
            "scheduled_time",
            "approved_at",
            "completed_at",
            "created_at",
        ]


# --- About Us --------------------------------------------------------------
# The About page is its own payload rather than another key on /homepage/: the
# landing page never renders any of it, and making every visit to "/" carry a
# team grid it will not draw is waste on a page that is already the heaviest.


def _years_since(year: int) -> int:
    """Whole years from `year` to today, floored at zero."""
    from datetime import date

    return max(date.today().year - year, 0)


def _fill_years(text: str, established_year: int) -> str:
    """Replace the `{years}` token with the salon's age.

    The page used to compute this in JSX. Keeping it a token means the copy
    stays editable in the admin without the number going stale every January.
    Unknown braces are left alone -- this is deliberately not `str.format`,
    which would raise on any other brace in the prose.
    """
    return text.replace("{years}", str(_years_since(established_year)))


class AboutColumnItemSerializer(CamelCaseModelSerializer):
    class Meta:
        model = AboutColumnItem
        fields = ["id", "text", "order"]


class AboutColumnSerializer(CamelCaseModelSerializer):
    items = serializers.SerializerMethodField()

    class Meta:
        model = AboutColumn
        fields = ["id", "heading", "body", "items", "order"]

    def get_items(self, obj):
        # `.all()`, not `.filter(...)`. The parent prefetches this relation with
        # the published filter already applied (see `AboutSerializer.get_columns`),
        # and `.all()` is the only call that reads that cache -- any filter on a
        # prefetched manager issues a fresh query instead, which made the
        # prefetch pure overhead *and* left one query per column behind it.
        return AboutColumnItemSerializer(
            obj.items.all(), many=True, context=self.context
        ).data


class AboutStatSerializer(CamelCaseModelSerializer):
    value = serializers.SerializerMethodField()

    class Meta:
        model = AboutStat
        fields = ["id", "value", "label", "order"]

    def get_value(self, obj):
        return _fill_years(obj.value, self.context.get("established_year", 2018))


class TeamMemberSerializer(CamelCaseModelSerializer):
    image = ImageURLField("image", "image_url")
    social = serializers.SerializerMethodField()

    class Meta:
        model = TeamMember
        fields = ["id", "name", "role", "image", "social", "order"]

    def get_social(self, obj):
        """Only the links that were filled in.

        The component renders one icon per key present, so omitting a blank
        field here is what hides the icon -- no empty anchors pointing at "#".
        """
        links = {
            "facebook": obj.facebook_url,
            "twitter": obj.twitter_url,
            "youtube": obj.youtube_url,
        }
        return {key: url for key, url in links.items() if url}


class AboutSerializer(CamelCaseModelSerializer):
    hero_image = ImageURLField("hero_image", "hero_image_url")
    intro_body = serializers.SerializerMethodField()
    columns = serializers.SerializerMethodField()
    stats = serializers.SerializerMethodField()
    team = serializers.SerializerMethodField()
    cta_primary = LinkField("cta_primary_label", "cta_primary_href")
    cta_secondary = LinkField("cta_secondary_label", "cta_secondary_href")

    class Meta:
        model = AboutSection
        fields = [
            "hero_title",
            "hero_date",
            "hero_scroll_prompt",
            "hero_image",
            "eyebrow",
            "heading_line_1",
            "heading_line_2",
            "intro_body",
            "columns",
            "stats",
            "team_heading",
            "team_body",
            "team",
            "cta_heading_lead",
            "cta_heading_accent",
            "cta_body",
            "cta_primary",
            "cta_secondary",
            "instagram_handle",
        ]

    def _child_context(self, obj):
        return {**self.context, "established_year": obj.established_year}

    def get_intro_body(self, obj):
        return _fill_years(obj.intro_body, obj.established_year)

    def get_columns(self, obj):
        queryset = AboutColumn.objects.filter(is_published=True).prefetch_related(
            # The filter has to live inside the Prefetch, not in the child
            # serializer: a `.filter()` on the prefetched manager cannot use the
            # cache this fills, so the two together did the work twice and then
            # some. Filtering here means `items.all()` downstream is both correct
            # and free.
            Prefetch(
                "items",
                queryset=AboutColumnItem.objects.filter(is_published=True),
            )
        )
        return AboutColumnSerializer(
            queryset, many=True, context=self._child_context(obj)
        ).data

    def get_stats(self, obj):
        queryset = AboutStat.objects.filter(is_published=True)
        return AboutStatSerializer(
            queryset, many=True, context=self._child_context(obj)
        ).data

    def get_team(self, obj):
        queryset = TeamMember.objects.filter(is_published=True)
        return TeamMemberSerializer(
            queryset, many=True, context=self._child_context(obj)
        ).data
