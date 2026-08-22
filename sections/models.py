"""One model per band of the landing page, in the order they appear.

Hero → Who We Are → Motivation → Classes → Our Story → As Seen On →
Follow Us → Contact → Footer.

Two conventions run through the whole file:

* Images come in pairs — an `ImageField` upload and an `image_url` override.
  `common.utils.resolve_image` picks the upload when there is one, so content
  can live here or stay on the bucket it is already on (the Classes cards are
  still on the demo's Cloudinary).
* Every default is the copy currently hardcoded in the React components. An
  empty database therefore renders today's page rather than an empty one.
"""

from django.db import models

from common.models import IMAGE_URL_HELP, OrderedModel, SingletonModel
from common.storage import video_storage
from common.validators import validate_video_upload

def color_help(what: str, default: str) -> str:
    """Help text for a colour field, carrying its own default in brackets.

    The default is spelled out because a colour field is the one kind of
    setting you cannot recover by looking at it: once someone types over
    "#0a0a0a" there is nothing on the page telling them what it used to be.
    Paste the bracketed value back to undo.
    """
    return f"{what} Default is ({default}) — paste that back to restore it."


class HeroSection(SingletonModel):
    """Figma "Landing Page Salon" 3:202 — the full-viewport opening band."""

    eyebrow = models.CharField(max_length=120, default="Welcome To Choppers")
    # The design breaks the headline explicitly after "For A", so the two lines
    # are separate fields rather than one string split on a newline.
    headline_line_1 = models.CharField(max_length=120, default="Best Hair Salon For A")
    headline_line_2 = models.CharField(max_length=120, default="Professional Look")
    body = models.TextField(
        default=(
            "Choppers offers high performance customized facials to provide you "
            "with visible results."
        )
    )

    primary_cta_label = models.CharField(max_length=60, default="Book Now")
    primary_cta_href = models.CharField(max_length=200, default="/services")
    secondary_cta_label = models.CharField(max_length=60, default="All Services")
    secondary_cta_href = models.CharField(max_length=200, default="/services")

    background_image = models.ImageField(upload_to="hero/", blank=True)
    # Empty by default: the band is solid black without it. The Figma comp
    # (3:203) has a scratched-plaster photo here and the file is still in
    # public/images/hero-texture.jpg — paste that path back in, or upload
    # anything else, to bring a backdrop back.
    background_image_url = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text=IMAGE_URL_HELP,
    )

    stylist_image = models.ImageField(upload_to="hero/", blank=True)
    stylist_image_url = models.CharField(
        max_length=500,
        blank=True,
        default="/images/hero-stylist.png",
        help_text=IMAGE_URL_HELP,
    )
    stylist_image_alt = models.CharField(
        max_length=200,
        default="A barber trimming the hair of a smiling client in a black cape",
    )

    watermark_image = models.ImageField(upload_to="hero/", blank=True)
    watermark_image_url = models.CharField(
        max_length=500,
        blank=True,
        default="/images/choppers-mark.png",
        help_text=IMAGE_URL_HELP,
    )

    # --- Colours -----------------------------------------------------------
    # Editable because a salon may rebrand without a developer. Applied as
    # inline styles on the rendered hero, so they override the stylesheet
    # rather than fighting it. Any CSS colour works ("#c7ff3d", "black",
    # "rgb(10 10 10)"); hex is what the help text quotes.
    background_color = models.CharField(
        max_length=32,
        default="#0a0a0a",
        help_text=color_help("Behind the whole hero band.", "#0a0a0a"),
    )
    heading_color = models.CharField(
        max_length=32,
        default="#ffffff",
        help_text=color_help("The big two-line headline.", "#ffffff"),
    )
    body_color = models.CharField(
        max_length=32,
        default="#9a9a9a",
        help_text=color_help("The paragraph under the headline.", "#9a9a9a"),
    )
    eyebrow_color = models.CharField(
        max_length=32,
        default="#fbb034",
        help_text=color_help("The small line above the headline.", "#fbb034"),
    )
    primary_button_bg = models.CharField(
        max_length=32,
        default="#c7ff3d",
        help_text=color_help("Fill of the first button.", "#c7ff3d"),
    )
    primary_button_text = models.CharField(
        max_length=32,
        default="#000000",
        help_text=color_help("Text on the first button.", "#000000"),
    )
    secondary_button_color = models.CharField(
        max_length=32,
        default="#c7ff3d",
        help_text=color_help(
            "Outline and text of the second button; it fills with this on hover.",
            "#c7ff3d",
        ),
    )

    class Meta:
        verbose_name = "Hero"
        verbose_name_plural = "Hero"

    def __str__(self):
        return "Hero"


class Service(OrderedModel):
    """One bookable service.

    The landing page's Service Menu band was removed, so `icon`/`icon_image`
    now have no renderer — they are kept because the drawn glyphs still exist
    and a future band may want them. What the booking flow reads is `image`,
    `description` and `price_from`.
    """

    class Icon(models.TextChoices):
        HAIR = "hair", "Hair"
        MAKEUP = "makeup", "Makeup"
        MANICURE_PEDICURE = "manicure-pedicure", "Manicure & pedicure"
        SKINCARE = "skincare", "Skincare"
        FACIAL = "facial", "Facial"

    label = models.CharField(max_length=80)
    icon = models.CharField(max_length=40, choices=Icon.choices, default=Icon.HAIR)
    icon_image = models.ImageField(
        upload_to="services/",
        blank=True,
        help_text="Optional. Overrides the built-in icon above.",
    )

    # A photograph, as opposed to `icon`/`icon_image` above. The Service Menu
    # band on the landing page is a row of drawn icons and uses those; the
    # booking flow shows this picture on the card instead, because choosing
    # what to book is easier from a photo of the result than from a glyph.
    image = models.ImageField(upload_to="services/", blank=True)
    image_url = models.CharField(
        max_length=500, blank=True, help_text=IMAGE_URL_HELP
    )
    href = models.CharField(max_length=200, blank=True)
    description = models.TextField(
        blank=True, help_text="Not shown on the landing page; for a services page."
    )
    price_from = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional. Shown as a “from” price where the design has one.",
    )

    class Meta(OrderedModel.Meta):
        verbose_name = "Service"
        verbose_name_plural = "Services"

    def __str__(self):
        return self.label


class WhoWeAreSection(SingletonModel):
    """Ported from the gsap demo's `WhoWeAreSection` + `AboutUsSection`.

    Two of the demo's bands rolled into one, because they are one idea: a big
    two-line heading that resolves letter by letter on scroll, a large lead
    paragraph under it, then a smaller paragraph and a button set against the
    right edge.

    The heading is two fields for the same reason the footer's is three — each
    line slides in from a different side, so where the break falls is a design
    decision rather than a wrap.
    """

    heading_line_1 = models.CharField(max_length=40, default="WHO")
    heading_line_2 = models.CharField(max_length=40, default="WE ARE")
    lead = models.TextField(
        default=(
            "A Kathmandu salon built on craft — every cut shaped to the person "
            "in the chair, not to a catalogue."
        ),
        help_text="The large paragraph under the heading.",
    )
    body = models.TextField(
        default=(
            "Our stylists train year-round on cuts, colour and care, so the "
            "chair you sit in is the same standard every visit."
        ),
        help_text="The smaller paragraph set against the right edge.",
    )
    cta_label = models.CharField(max_length=60, default="About us")
    cta_href = models.CharField(max_length=200, default="/about-us")
    is_published = models.BooleanField(
        default=True, help_text="Untick to drop the whole band from the page."
    )

    class Meta:
        verbose_name = "Who we are"
        verbose_name_plural = "Who we are"

    def __str__(self):
        return "Who we are"


class MotivationSection(SingletonModel):
    """The three sheared lines that drift on scroll (ported from devis-gym)."""

    is_published = models.BooleanField(
        default=True, help_text="Untick to drop the whole band from the page."
    )

    class Meta:
        verbose_name = "Motivation lines"
        verbose_name_plural = "Motivation lines"

    def __str__(self):
        return "Motivation lines"


class MotivationLine(OrderedModel):
    section = models.ForeignKey(
        MotivationSection, related_name="lines", on_delete=models.CASCADE
    )
    text = models.CharField(max_length=120)

    class Meta(OrderedModel.Meta):
        verbose_name = "Motivation line"
        verbose_name_plural = "Motivation lines"

    def __str__(self):
        return self.text


class GallerySection(SingletonModel):
    """The scroll-driven image grid that tears open down the middle.

    Ported from a GSAP demo, where it showed Dribbble shots. The copy and the
    six images are both editable, and the defaults below are now the salon's
    rather than the demo's — the component never needed touching.
    """

    heading = models.CharField(max_length=120, default="Our Speciality")
    body = models.TextField(
        default=(
            "Capturing elegance and artistry,\n"
            "witness the transformations that\n"
            "define our craft."
        ),
        help_text=(
            "Line breaks are kept from tablet up and collapse to spaces on a "
            "phone, where the measure is too narrow to break by hand."
        ),
    )
    cta_label = models.CharField(max_length=60, default="View Services")
    cta_href = models.CharField(max_length=200, default="/services")
    is_published = models.BooleanField(
        default=True, help_text="Untick to drop the whole band from the page."
    )

    class Meta:
        verbose_name = "Gallery grid"
        verbose_name_plural = "Gallery grid"

    def __str__(self):
        return "Gallery grid"

    @property
    def lines(self) -> list[str]:
        return [line.strip() for line in self.body.splitlines() if line.strip()]


class GalleryImage(OrderedModel):
    """One card in the gallery grid.

    The animation reads the cards in pairs — the left one drifts left, the
    right one mirrors it — so an odd count leaves a card with no partner. It
    still renders; it just does not travel.
    """

    section = models.ForeignKey(
        GallerySection, related_name="images", on_delete=models.CASCADE
    )
    image = models.ImageField(upload_to="gallery/", blank=True)
    image_url = models.CharField(max_length=500, blank=True, help_text=IMAGE_URL_HELP)
    alt = models.CharField(
        max_length=200,
        help_text="Describe the picture for screen readers and failed loads.",
    )

    class Meta(OrderedModel.Meta):
        verbose_name = "Gallery image"
        verbose_name_plural = "Gallery images"

    def __str__(self):
        return self.alt or f"Gallery image {self.pk}"


class ClassesSection(SingletonModel):
    """Two-line heading, scroll-driven marquee, and the card grid below it.

    The model name is the devis-gym demo's ("Classes"); the band is now the
    salon's shots from the chair, and every card links to /services rather than
    standing for a service itself. Renaming the model would mean a migration
    across ClassCard's FK and the API's `classes` key for no behaviour change,
    so the name stays and this note explains it.
    """

    heading_top = models.CharField(max_length=120, default="Moments Captured")
    heading_bottom = models.CharField(max_length=120, default="In The Chair")
    marquee_phrase = models.CharField(
        max_length=300,
        default=(
            "FRESH CUTS • SHARP FADES • CLEAN LINES • EVERY CHAIR • "
            "EVERY DAY • REAL MOMENTS"
        ),
        help_text="Repeated across the strip. Separate items with • .",
    )

    class Meta:
        verbose_name = "Classes"
        verbose_name_plural = "Classes"

    def __str__(self):
        return "Classes"


def _cloudinary_poster(url: str) -> str:
    """A still from a Cloudinary video, by asking Cloudinary for it as an image.

    Cloudinary renders a frame of any video it holds if the delivery URL asks
    for a picture format, so swapping the extension for `.jpg` on a
    `/video/upload/` address gives a poster frame with nothing extra to upload
    and nothing extra to store.

    Returns "" for anything that is not such a URL -- a direct .mp4 on someone
    else's server has no equivalent trick, and guessing one would produce a
    broken `poster` attribute rather than no poster at all.
    """
    if "res.cloudinary.com" not in url or "/video/upload/" not in url:
        return ""

    head, _, tail = url.rpartition("/")
    if not head:
        return ""
    # A Cloudinary public id may carry no extension at all, in which case the
    # suffix is appended rather than swapped.
    stem = tail.rsplit(".", 1)[0] if "." in tail else tail
    return f"{head}/{stem}.jpg" if stem else ""


class ClassCard(OrderedModel):
    """One card in the Classes grid.

    `name` may contain a newline; the design breaks long names over two lines
    and the component renders it with `whitespace-pre-line`.
    """

    section = models.ForeignKey(
        ClassesSection, related_name="cards", on_delete=models.CASCADE
    )
    slug = models.SlugField(max_length=80, unique=True)
    name = models.CharField(
        max_length=80,
        help_text="A line break here becomes a line break on the card.",
    )
    href = models.CharField(max_length=200)
    image = models.ImageField(upload_to="classes/", blank=True)
    image_url = models.CharField(
        max_length=500,
        blank=True,
        help_text="Used when no file is uploaded. The seeded cards point at Cloudinary.",
    )

    # --- Video ---
    # A clip plays in place of the still, with the still as its poster frame.
    # The image stays required in practice for that reason: it is what fills
    # the card for the second before the video has enough buffered to start,
    # and what a visitor with data-saver on sees instead of the clip.
    #
    # A clip is a URL and nothing else. There is deliberately no upload here.
    #
    # There used to be: a FileField writing to classes/video/, and a Cloudflare
    # Stream id beside it. Both are gone. Uploading meant a second storage
    # service to configure before the field did anything, and it put video
    # files in the backend that the salon then had to think about -- which is
    # not what a link needs. Pasting an address costs nothing to set up, works
    # with any host, and leaves this project storing no video at all.
    video_url = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="Video URL",
        help_text=(
            "The address of a clip hosted somewhere else -- a Cloudflare or "
            "Cloudinary video URL, or any direct .mp4 or .m3u8 link. While "
            "this is filled in it replaces the photo on this card."
        ),
    )

    class Meta(OrderedModel.Meta):
        verbose_name = "Class card"
        verbose_name_plural = "Class cards"

    def __str__(self):
        return self.name.replace("\n", " ")

    def video(self) -> dict:
        """What the API hands the frontend for this card's clip, or {}.

        One source: the pasted address. Nothing is stored by this project, so
        there is nothing else to check.

        A card is a photo or a clip and never both, so a clip has no photo
        behind it while it buffers -- which is why a thumbnail is derived
        where one can be had.
        """
        if not self.video_url:
            return {}
        return {
            "uid": "",
            "src": self.video_url,
            "thumbnail": _cloudinary_poster(self.video_url),
        }


class OurStorySection(SingletonModel):
    """Figma 97:1098 — photo collage on the left, copy and CTA on the right."""

    heading = models.CharField(max_length=120, default="Our Story")
    body = models.TextField(
        default=(
            "We started as a small beauty salon in Kathmandu, Nepal. Our vision "
            "was to create a premium salon experience where beauty meets "
            "excellence. We believe in using only the finest products and "
            "techniques to help our clients look and feel their absolute best. "
            "Our team of expert stylists and beauty professionals are "
            "passionate about transforming your look and boosting your "
            "confidence with every visit."
        )
    )
    cta_label = models.CharField(max_length=60, default="Learn More")
    cta_href = models.CharField(max_length=200, default="/about-us")

    image = models.ImageField(upload_to="story/", blank=True)
    image_url = models.CharField(
        max_length=500,
        blank=True,
        default="/images/salon-artist.webp",
        help_text=IMAGE_URL_HELP,
    )
    image_alt = models.CharField(
        max_length=200, default="Stylist holding a set of makeup brushes"
    )

    class Meta:
        verbose_name = "Our story"
        verbose_name_plural = "Our story"

    def __str__(self):
        return "Our story"


class AsSeenOnSection(SingletonModel):
    """Figma 97:1159 — the wave band carrying a pull quote."""

    heading = models.CharField(max_length=120, default="As seen On")
    quote = models.TextField(
        default="The place with its constant excellence, soul, and style",
        help_text="Rendered inside typographic quotes; do not type your own.",
    )
    attribution = models.CharField(
        max_length=120, blank=True, help_text="Optional. Shown under the quote."
    )
    cta_label = models.CharField(max_length=60, default="Learn More")
    cta_href = models.CharField(max_length=200, default="/about-us")

    class Meta:
        verbose_name = "As seen on"
        verbose_name_plural = "As seen on"

    def __str__(self):
        return "As seen on"


class FollowUsSection(SingletonModel):
    """Figma 97:1108 — the badge, the vertical social labels and the copy."""

    heading = models.CharField(max_length=120, default="Follow Us")
    body = models.TextField(
        default="Don’t miss promotions, follow us for the latest news"
    )

    class Meta:
        verbose_name = "Follow us"
        verbose_name_plural = "Follow us"

    def __str__(self):
        return "Follow us"


class FooterSection(SingletonModel):
    """The footer's own copy. Its link list comes from core.NavLink.

    The three `heading_line*` fields are the footer's scroll-animated headline,
    ported from the gsap demo's `TimeToRoarSection`. They are three separate
    fields rather than one because each line animates independently — line 1
    and 3 slide right-to-left, line 2 slides the other way — so where the break
    falls is a design decision, not a wrap.
    """

    # "TIME TO SHINE" — the demo this was ported from ended on "TIME TO
    # ROAR!", which belongs to a gym. Shine is the same shape and the same
    # send-off, in the register a salon actually speaks in.
    heading_line1 = models.CharField(max_length=40, default="TIME")
    heading_line2 = models.CharField(max_length=40, default="TO")
    heading_line3 = models.CharField(max_length=40, default="SHINE")

    contact_heading = models.CharField(max_length=120, default="Contact Us")
    contact_body = models.TextField(
        default="Don’t miss promotions, follow us for the latest news"
    )

    email = models.EmailField(default="info@beautysalon.com")
    phone = models.CharField(max_length=40, default="070 9485 7568")
    cta_label = models.CharField(max_length=60, default="Book a seat")
    cta_href = models.CharField(max_length=200, default="/services")

    class Meta:
        verbose_name = "Footer"
        verbose_name_plural = "Footer"

    def __str__(self):
        return "Footer"


# --- About Us page ---------------------------------------------------------
# Everything below belongs to /about-us rather than the landing page. It
# follows the same conventions as the bands above: defaults are the copy the
# React page shipped with, so an empty database renders today's page.


class AboutSection(SingletonModel):
    """The About Us page: scroll hero, intro, team heading, closing CTA.

    The four columns, the stat tiles and the team grid are separate models
    below, because each is a list the admin should be able to reorder.

    `established_year` exists because the page did the arithmetic in JSX --
    `new Date().getFullYear() - 2018`. Moving that copy into the database would
    have frozen it at whatever the year was on the day it was typed, so the
    serializer substitutes `{years}` wherever it appears in the prose instead.
    """

    established_year = models.PositiveIntegerField(
        default=2018,
        help_text=(
            "Used to work out how long the salon has been open. Write {years} "
            "in any text below and it is replaced by that number."
        ),
    )

    # --- Simple video hero ---
    hero_title = models.CharField(
        max_length=160,
        default="AJ SALON EXPERIENCE",
        help_text="Main heading displayed on the video hero (split across 2 lines).",
    )
    hero_date = models.CharField(
        max_length=160,
        default="In Kathmandu since 2018",
        help_text="Subtitle displayed under the hero title.",
    )
    hero_scroll_prompt = models.CharField(
        max_length=160,
        default="Scroll to Explore Our Salon",
        help_text="Text prompt shown with animated mouse icon and down arrow. Leave filled to show scroll indicators, or clear to hide them.",
    )
    hero_video = models.FileField(
        upload_to="about/video/",
        blank=True,
        storage=video_storage,
        validators=[validate_video_upload],
        help_text=(
            "Upload the clip here. It goes to Cloudinary when the account is "
            "configured, and to the local media folder otherwise. An upload "
            "always wins over the URL below."
        ),
    )
    hero_video_url = models.CharField(
        max_length=500,
        blank=True,
        default=(
            "https://res.cloudinary.com/ufiebboc/video/upload/f_auto,q_auto/"
            "hfjpk00y9fqeznekhrh9"
        ),
        help_text=(
            "Leave empty if you uploaded a file above -- the upload is always "
            "used. Only fill this in to point at a video hosted somewhere else."
        ),
    )
    hero_bg_image = models.ImageField(
        upload_to="about/",
        blank=True,
        help_text="DEPRECATED: No longer used in the frontend. The hero now uses video only with a dark overlay for text readability.",
    )
    hero_bg_image_url = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="DEPRECATED: No longer used in the frontend. The hero now uses video only.",
    )

    # --- Intro block ---
    eyebrow = models.CharField(max_length=120, default="About Our Salon")
    heading_line_1 = models.CharField(max_length=120, default="More Than")
    heading_line_2 = models.CharField(
        max_length=120,
        default="Just A Salon.",
        help_text="Rendered in the accent colour.",
    )
    intro_body = models.TextField(
        default=(
            "Our Salon provides a unique way to engage with our beauty "
            "community through personalized experiences. Located in the heart "
            "of Kathmandu, we have been transforming lives for over {years} "
            "years with our commitment to exceptional beauty services and "
            "personalized styling solutions. Our state-of-the-art facility "
            "combines modern techniques with expert guidance from 6+ certified "
            "stylists who are passionate about helping you achieve your beauty "
            "goals. Open Sunday through Friday from 10:00 AM to 8:00 PM, we "
            "offer flexible hours to fit your schedule. With a supportive "
            "community of 500+ happy clients, we offer more than just a beauty "
            "service - we provide a complete beauty experience designed to "
            "unlock your true confidence."
        )
    )

    # --- Team block ---
    team_heading = models.CharField(max_length=160, default="Meet Our Team")
    team_body = models.TextField(
        default=(
            "Our certified beauty professionals are passionate about helping "
            "you look and feel your best. With years of experience and "
            "specialized training in the latest beauty trends and techniques, "
            "they provide personalized styling and treatments tailored to your "
            "unique needs."
        )
    )

    # --- Closing call to action ---
    cta_heading_lead = models.CharField(max_length=120, default="Ready to")
    cta_heading_accent = models.CharField(
        max_length=120,
        default="Book Your Appointment?",
        help_text="Rendered in the accent colour, following the lead above.",
    )
    cta_body = models.TextField(
        default=(
            "Join our community and experience what beauty excellence feels "
            "like. No commitments, no pressure - just stunning results."
        )
    )
    cta_primary_label = models.CharField(max_length=80, default="Contact Us")
    cta_primary_href = models.CharField(max_length=200, default="/contact")
    cta_secondary_label = models.CharField(max_length=80, default="View Membership")
    cta_secondary_href = models.CharField(max_length=200, default="/#membership")

    # --- Instagram strip ---
    instagram_handle = models.CharField(
        max_length=120,
        default="@beautysalon_kathmandu",
        help_text="Shown down the side of the Instagram strip.",
    )

    class Meta:
        verbose_name = "About us"
        verbose_name_plural = "About us"

    def __str__(self):
        return "About us"


class AboutColumn(OrderedModel):
    """One of the columns under the About hero.

    Two shapes share this model because the design treats them the same: a
    heading with prose (`body`), or a heading with a bullet list (`items`).
    Fill in whichever the column needs -- both render if both are set.
    """

    section = models.ForeignKey(
        AboutSection, related_name="columns", on_delete=models.CASCADE
    )
    heading = models.CharField(max_length=120)
    body = models.TextField(
        blank=True,
        help_text=(
            "Prose for this column. Leave empty if the column is a bullet list "
            "and add the bullets on this page instead. A blank line starts a "
            "new paragraph."
        ),
    )

    class Meta(OrderedModel.Meta):
        verbose_name = "About column"
        verbose_name_plural = "About columns"

    def __str__(self):
        return self.heading


class AboutColumnItem(OrderedModel):
    """A single bullet inside an About column."""

    column = models.ForeignKey(
        AboutColumn, related_name="items", on_delete=models.CASCADE
    )
    text = models.CharField(max_length=200)

    class Meta(OrderedModel.Meta):
        verbose_name = "Column bullet"
        verbose_name_plural = "Column bullets"

    def __str__(self):
        return self.text


class AboutStat(OrderedModel):
    """One of the counters above the team grid.

    `value` is free text rather than a number because the row mixes kinds:
    three tiles count up ("500+") and one is a pair of opening days
    ("Sun-Fri"). The component animates it only when it contains a digit.
    """

    section = models.ForeignKey(
        AboutSection, related_name="stats", on_delete=models.CASCADE
    )
    value = models.CharField(
        max_length=40,
        help_text=(
            "Counts up on screen when it contains a number. {years} works here "
            "too -- use it for the years-in-business tile so it cannot go stale."
        ),
    )
    label = models.CharField(max_length=120)

    class Meta(OrderedModel.Meta):
        verbose_name = "About stat"
        verbose_name_plural = "About stats"

    def __str__(self):
        return f"{self.value} {self.label}"


class TeamMember(OrderedModel):
    """A stylist in the team grid.

    The social fields are per-person rather than reusing `core.SocialLink`,
    which holds the salon's own accounts for the footer.
    """

    section = models.ForeignKey(
        AboutSection, related_name="team", on_delete=models.CASCADE
    )
    name = models.CharField(max_length=120)
    role = models.CharField(max_length=120)
    image = models.ImageField(upload_to="team/", blank=True)
    image_url = models.CharField(max_length=500, blank=True, help_text=IMAGE_URL_HELP)
    facebook_url = models.CharField(
        max_length=300,
        blank=True,
        help_text="Leave empty to hide this icon for this person.",
    )
    twitter_url = models.CharField(max_length=300, blank=True)
    youtube_url = models.CharField(max_length=300, blank=True)

    class Meta(OrderedModel.Meta):
        verbose_name = "Team member"
        verbose_name_plural = "Team members"

    def __str__(self):
        return self.name
