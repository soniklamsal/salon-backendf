"""Load the copy the React components currently hardcode into the database.

Run once after `migrate`. It is idempotent: singletons and keyed rows are
matched on a natural key and updated, so re-running restores the site to its
shipped state without duplicating anything.

    python manage.py seed_content            # fill in what is missing
    python manage.py seed_content --reset    # also overwrite edited rows

Without `--reset` existing rows are left alone, so a seed run can never quietly
undo someone's admin edits.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from bookings.models import Barber, BookingSection
from core.models import NavLink, SiteSettings, SocialLink
from sections.models import (
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
    WhoWeAreSection,
)

NAV_LINKS = [
    ("Home", "/"),
    ("About Us", "/about-us"),
    # "Service Menu" opens the booking flow rather than a separate menu page.
    ("Service Menu", "/services"),
    ("Contact Us", "/contact"),
]

SOCIAL_LINKS = [
    (SocialLink.Platform.FACEBOOK, "https://facebook.com"),
    (SocialLink.Platform.INSTAGRAM, "https://instagram.com"),
]

# The bookable list, shown as photo cards in step 1 of the booking flow and as
# the drawn-icon row in components/service-menu.tsx on the landing page.
#
# `icon` still has to be one of the five drawn glyphs — that is all the Figma
# file provides — so several of these share one. The photo is what the booking
# card leads with; the glyph only appears in the landing-page row.
#
# Photos are the same devis-gym Cloudinary shots the Moments band uses, matched
# to the service of the same name. Replace them per service in the admin.
SERVICES = [
    (
        "Fresh Cut",
        Service.Icon.HAIR,
        "v1786269602/devis-gym/people/DSC07734.JPG.webp",
        "A full cut and finish, shaped to how you actually wear it.",
        "800.00",
    ),
    (
        "Sharp Fade",
        Service.Icon.HAIR,
        "v1786269452/devis-gym/people/DSC07615-4.JPG.webp",
        "Skin, low or high — blended clean through the sides and back.",
        "900.00",
    ),
    (
        "Beard Work",
        Service.Icon.FACIAL,
        "v1786269591/devis-gym/people/DSC07629-3.JPG.webp",
        "Line-up, trim and hot-towel finish.",
        "500.00",
    ),
    (
        "Wash & Style",
        Service.Icon.SKINCARE,
        "v1786269637/devis-gym/people/DSC07636-3.JPG.webp",
        "Wash, condition and a blow-dry set for the day.",
        "600.00",
    ),
    (
        "Colour Day",
        Service.Icon.MAKEUP,
        "v1786268875/devis-gym/people/DSC07385.JPG.webp",
        "Full colour or highlights, booked with time to do it properly.",
        "2500.00",
    ),
]

# components/motivation-lines.tsx
MOTIVATION_LINES = [
    "BEAUTY IS POWER",
    "CONFIDENCE IS YOUR",
    "BEST ACCESSORY",
]

# components/classes-designed.tsx
#
# These are shots from the chair, not a service list — the caption says what is
# happening in the picture. Every card points at /services, because the band's
# job is to get someone into the booking flow rather than to a page per card.
#
# Images now use the gallery images from /images/dribbble/ to match the
# "Our Speciality" section above. These are local frontend images that display
# until updated through the admin with real salon photos.
CLASS_CARDS = [
    ("fresh-cut", "Fresh\nCut", "/services", "/images/dribbble/first.jpeg"),
    ("sharp-fade", "Sharp\nFade", "/services", "/images/dribbble/second.jpeg"),
    ("beard-work", "Beard\nWork", "/services", "/images/dribbble/third.jpeg"),
    ("wash-style", "Wash &\nStyle", "/services", "/images/dribbble/fourth.jpeg"),
    ("colour-day", "Colour\nDay", "/services", "/images/dribbble/fifth.jpeg"),
    ("clean-lines", "Clean\nLines", "/services", "/images/dribbble/sixth.jpeg"),
    ("finishing-touch", "Finishing\nTouch", "/services", "/images/dribbble/first.jpeg"),
    ("book-your-seat", "Book\nYour Seat", "/services", "/images/dribbble/second.jpeg"),
]

# bookings.Barber — step 2 of the booking flow needs at least one row or the
# customer cannot get past it. These are placeholders: rename them and upload
# real photographs in the admin. No photo is fine, the card falls back to
# initials.
BARBERS = [
    ("Aashish Shrestha", "Senior stylist"),
    ("Bina Gurung", "Colour specialist"),
    ("Kiran Tamang", "Barber"),
]

CLOUDINARY_BASE = "https://res.cloudinary.com/ufiebboc/image/upload/"

# components/dribbble-grid.tsx — the files sit in the frontend's public folder.
GALLERY_IMAGES = [
    ("/images/dribbble/first.jpeg", "Editorial fashion landing page"),
    ("/images/dribbble/second.jpeg", "Studio portfolio layout"),
    ("/images/dribbble/third.jpeg", "Brand identity showcase"),
    ("/images/dribbble/fourth.jpeg", "Product page concept"),
    ("/images/dribbble/fifth.jpeg", "Interface design study"),
    ("/images/dribbble/sixth.jpeg", "Marketing site exploration"),
]

SINGLETONS = [
    SiteSettings,
    BookingSection,
    HeroSection,
    WhoWeAreSection,
    MotivationSection,
    GallerySection,
    ClassesSection,
    OurStorySection,
    AsSeenOnSection,
    FollowUsSection,
    FooterSection,
]


class Command(BaseCommand):
    help = "Populate the database with the site's current content."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Overwrite rows that already exist instead of leaving them alone.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        reset = options["reset"]
        created_total = 0

        # Singletons carry their content as field defaults, so creating the row
        # is all it takes. --reset restores those defaults on an edited row.
        for model in SINGLETONS:
            obj, created = model.objects.get_or_create(pk=1)
            if created:
                created_total += 1
                self.stdout.write(f"  + {model._meta.verbose_name}")
            elif reset:
                fresh = model()
                for field in model._meta.fields:
                    if field.name in {"id", "pk", "created_at", "updated_at"}:
                        continue
                    setattr(obj, field.name, getattr(fresh, field.name))
                obj.save()
                self.stdout.write(f"  ~ {model._meta.verbose_name} (reset)")

        created_total += self._seed(
            NavLink,
            [
                {"label": label, "href": href, "order": i}
                for i, (label, href) in enumerate(NAV_LINKS)
            ],
            key="label",
            reset=reset,
        )

        created_total += self._seed(
            SocialLink,
            [
                {"platform": platform, "url": url, "order": i}
                for i, (platform, url) in enumerate(SOCIAL_LINKS)
            ],
            key="platform",
            reset=reset,
        )

        created_total += self._seed(
            Service,
            [
                {
                    "label": label,
                    "icon": icon,
                    "image_url": CLOUDINARY_BASE + path,
                    "description": description,
                    "price_from": price,
                    "order": i,
                }
                for i, (label, icon, path, description, price) in enumerate(SERVICES)
            ],
            key="label",
            reset=reset,
        )

        motivation = MotivationSection.objects.get(pk=1)
        created_total += self._seed(
            MotivationLine,
            [
                {"section": motivation, "text": text, "order": i}
                for i, text in enumerate(MOTIVATION_LINES)
            ],
            key="text",
            reset=reset,
        )

        gallery = GallerySection.objects.get(pk=1)
        created_total += self._seed(
            GalleryImage,
            [
                {"section": gallery, "image_url": url, "alt": alt, "order": i}
                for i, (url, alt) in enumerate(GALLERY_IMAGES)
            ],
            key="image_url",
            reset=reset,
        )

        classes = ClassesSection.objects.get(pk=1)
        created_total += self._seed(
            ClassCard,
            [
                {
                    "section": classes,
                    "slug": slug,
                    "name": name,
                    "href": href,
                    "image_url": path if path.startswith("/") else CLOUDINARY_BASE + path,
                    "order": i,
                }
                for i, (slug, name, href, path) in enumerate(CLASS_CARDS)
            ],
            key="slug",
            reset=reset,
        )

        created_total += self._seed(
            Barber,
            [
                {"name": name, "role": role, "order": i}
                for i, (name, role) in enumerate(BARBERS)
            ],
            key="name",
            reset=reset,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed complete — {created_total} row(s) created."
                + ("" if reset else " Existing rows were left untouched (--reset to overwrite).")
            )
        )

    def _seed(self, model, rows, key, reset):
        """Create or update `rows`, matching existing ones on `key`."""
        created_count = 0
        for row in rows:
            lookup = {key: row[key]}
            defaults = {k: v for k, v in row.items() if k != key}
            if reset:
                _obj, created = model.objects.update_or_create(**lookup, defaults=defaults)
            else:
                _obj, created = model.objects.get_or_create(**lookup, defaults=defaults)
            if created:
                created_count += 1
                self.stdout.write(f"  + {model._meta.verbose_name}: {row[key]}")
        return created_count
