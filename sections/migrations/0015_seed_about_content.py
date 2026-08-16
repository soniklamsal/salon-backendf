"""Seed the About page lists with the copy the React page shipped with.

The singleton's own fields carry their defaults, so `AboutSection.load()`
already returns today's intro and CTA on an empty database. Lists cannot work
that way -- there is no such thing as a default row -- so the four columns, the
four stat tiles and the five stylists are written here instead. Without this,
a fresh install would render the About page with an empty team grid.

Only runs when the tables are empty, so re-running it on a database someone has
already edited cannot overwrite their work.
"""

from django.db import migrations

COLUMNS = [
    {
        "heading": "Our Facilities",
        "body": "",
        "items": [
            "Premium hair styling stations",
            "Professional makeup area",
            "Spa and treatment rooms",
            "Professional styling consultation",
        ],
    },
    {
        "heading": "Why Choose Us",
        "body": "",
        "items": [
            "Located in the heart of Kathmandu",
            "Welcoming beauty community",
            "Flexible membership options",
            "Clean and well-maintained facility",
        ],
    },
    {
        "heading": "Mission",
        "body": (
            "Our purpose is to pass on empowering beauty knowledge and styling "
            "guidance in order to have a positive impact on the confidence and "
            "self-expression of everyone we work with.\n\n"
            "To provide a personalized beauty and styling service that unlocks "
            "every individual's true confidence so they can express their "
            "unique style and achieve their desired look."
        ),
        "items": [],
    },
    {
        "heading": "Story",
        "body": (
            "Our main focus at our Salon is personalized beauty services "
            "because of the proven benefits. With an emphasis on individual "
            "style, quality products and expert techniques, our personalized "
            "approach ensures that every client receives treatments tailored "
            "specifically to their unique needs and preferences."
        ),
        "items": [],
    },
]

# "{years}" is substituted by the serializer, which is how the first tile keeps
# counting up on its own the way the JSX used to.
STATS = [
    ("{years}+", "Years in Beauty Industry"),
    ("500+", "Happy Clients"),
    ("6+", "Expert Stylists"),
    ("Sun-Fri", "10:00 AM - 8:00 PM"),
]

CLOUDINARY = (
    "https://res.cloudinary.com/ufiebboc/image/upload/"
    "v{version}/devis-gym/people/Trainers/{file}"
)

TEAM = [
    ("Bijay Grg", "Senior Stylist", "1786269634", "BijayGrg.JPG.webp"),
    ("Aditya Grg", "Hair Specialist", "1786269619", "AdityaGrg.JPG.webp"),
    ("Barsha Grg", "Makeup Artist", "1786269630", "BarshaGrg.JPG.webp"),
    ("Abhishek Mishra", "Color Specialist", "1786269614", "AbhishekMishra.JPG.webp"),
    ("Anup Grg", "Beauty Consultant", "1786269624", "AnupGrg.JPG.webp"),
]


def seed(apps, schema_editor):
    AboutSection = apps.get_model("sections", "AboutSection")
    AboutColumn = apps.get_model("sections", "AboutColumn")
    AboutColumnItem = apps.get_model("sections", "AboutColumnItem")
    AboutStat = apps.get_model("sections", "AboutStat")
    TeamMember = apps.get_model("sections", "TeamMember")

    # The singleton collapses onto pk=1 in its save(), but historical models do
    # not carry that override, so it is spelled out here.
    section, _ = AboutSection.objects.get_or_create(pk=1)

    if not AboutColumn.objects.exists():
        for order, spec in enumerate(COLUMNS):
            column = AboutColumn.objects.create(
                section=section,
                heading=spec["heading"],
                body=spec["body"],
                order=order,
            )
            for item_order, text in enumerate(spec["items"]):
                AboutColumnItem.objects.create(
                    column=column, text=text, order=item_order
                )

    if not AboutStat.objects.exists():
        for order, (value, label) in enumerate(STATS):
            AboutStat.objects.create(
                section=section, value=value, label=label, order=order
            )

    if not TeamMember.objects.exists():
        for order, (name, role, version, filename) in enumerate(TEAM):
            TeamMember.objects.create(
                section=section,
                name=name,
                role=role,
                image_url=CLOUDINARY.format(version=version, file=filename),
                # The old markup pointed every icon at "#". Left blank instead:
                # the serializer omits empty links and the grid then draws no
                # icon, which beats three that go nowhere. Fill these in per
                # stylist in the admin.
                facebook_url="",
                twitter_url="",
                youtube_url="",
                order=order,
            )


def unseed(apps, schema_editor):
    """Remove only the rows this migration created."""
    for model in ("AboutColumnItem", "AboutColumn", "AboutStat", "TeamMember"):
        apps.get_model("sections", model).objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("sections", "0014_aboutcolumn_aboutsection_aboutcolumnitem_and_more"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
