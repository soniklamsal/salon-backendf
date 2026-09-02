"""What the salon needs to look at first, counted once.

The admin's front page was Jazzmin's stock app list -- the sidebar again in a
second shape, with no numbers on it. `SingletonAdmin.response_post_save_change`
sends staff there after every save, so the most-visited page in the admin was
also the one that said the least.

This is the data behind the replacement. Four numbers and a short list, chosen
by one test: does it tell somebody arriving in the morning what is waiting for
them? Anything that fails that test is a number for its own sake, and the page
is more useful without it.

Cost is deliberately bounded and asserted by a test. Every figure below comes
from four queries in total, because a dashboard is the page most likely to grow
a tile a month until it is the slowest screen in the application.
"""

from django.apps import apps
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

#: How many waiting bookings the page lists under the tiles. Enough to act on
#: this morning; not so many that the app list is pushed off the screen.
PENDING_PREVIEW = 5


def _models():
    """Resolved at call time, not imported at module scope.

    `core` sits below `bookings` and must not grow an import-time dependency
    on it -- the same reasoning `common/email_config.py` writes out for
    reaching the settings model.
    """
    return (
        apps.get_model("bookings", "Appointment"),
        apps.get_model("bookings", "ContactMessage"),
    )


def dashboard_stats():
    """The four headline numbers. One query for three of them, one for the last."""
    Appointment, ContactMessage = _models()
    status = Appointment.Status

    today = timezone.localdate()

    # When a booking happens is `time_slot.date`: the customer picks the slot
    # in the booking form and `approve()` no longer copies anything onto
    # `scheduled_*`. Those two columns are only still consulted for rows made
    # before slots existed, which is why both halves are needed here -- counting
    # `scheduled_date` alone reported 0 visits on a day fully booked, and
    # flagged every approved booking as having no time.
    booked_for_today = Q(time_slot__date=today) | Q(
        time_slot__isnull=True, scheduled_date=today
    )
    has_no_time = Q(
        time_slot__isnull=True, scheduled_date__isnull=True, scheduled_time__isnull=True
    )

    counts = Appointment.objects.aggregate(
        pending=Count("pk", filter=Q(status=status.PENDING)),
        today=Count(
            "pk",
            filter=booked_for_today
            & Q(status__in=[status.APPROVED, status.COMPLETED]),
        ),
        # Approved but with no time set -- the customer has been told yes and
        # has not been told when. Invisible on every other screen.
        timeless=Count("pk", filter=Q(status=status.APPROVED) & has_no_time),
    )
    counts["unhandled"] = ContactMessage.objects.filter(is_handled=False).count()
    return counts


def pending_bookings():
    """The newest bookings waiting on a decision, each with its action button.

    `select_related` is not an optimisation here. Each row renders its service
    and its barber, so without it this is one query plus two per row.

    The button HTML comes from `AppointmentAdmin.row_actions`, reached through
    the admin registry rather than reimplemented: it is the same markup the
    changelist emits, so the same script binding covers it and there is no
    second version to keep in step. Attached to each object as `row_actions`
    because a template cannot call a ModelAdmin method itself.
    """
    from django.contrib import admin as django_admin

    Appointment, _ = _models()
    model_admin = django_admin.site._registry.get(Appointment)

    bookings = list(
        Appointment.objects.filter(status=Appointment.Status.PENDING)
        .select_related("service", "barber")
        .order_by("-created_at")[:PENDING_PREVIEW]
    )
    for booking in bookings:
        booking.row_actions = (
            model_admin.row_actions(booking) if model_admin is not None else ""
        )
    return bookings


def dashboard_context():
    """Everything the dashboard template needs.

    Each tile carries the URL of the list it counts. A number you cannot click
    into is a poster; the link is what makes it somewhere to start work.
    """
    stats = dashboard_stats()
    appointments = reverse("admin:bookings_appointment_changelist")
    enquiries = reverse("admin:bookings_contactmessage_changelist")

    from common.email_config import active_config

    config = active_config()

    return {
        "stats": stats,
        "tiles": [
            {
                "key": "pending",
                "value": stats["pending"],
                "label": "Waiting for approval",
                "url": appointments + "?status__exact=pending",
                "hero": True,
                "warn": False,
                "icon": "fa-hourglass-half",
            },
            {
                "key": "today",
                "value": stats["today"],
                "label": "Coming in today",
                "url": appointments + "?status__exact=approved",
                "hero": False,
                "warn": False,
                "icon": "fa-calendar-day",
            },
            {
                "key": "unhandled",
                "value": stats["unhandled"],
                "label": "Unanswered enquiries",
                "url": enquiries + "?is_handled__exact=0",
                "hero": False,
                "warn": False,
                "icon": "fa-envelope",
            },
            {
                "key": "timeless",
                "value": stats["timeless"],
                # Says what is wrong in words as well as in colour, so it does
                # not depend on telling amber from grey.
                "label": "Approved with no visit time",
                "url": appointments + "?status__exact=approved",
                "hero": False,
                "warn": stats["timeless"] > 0,
                "icon": "fa-exclamation-triangle",
            },
        ],
        "pending_bookings": pending_bookings(),
        "email_ready": config.is_configured,
        "email_source": "this admin" if config.source == "admin" else "the .env file",
    }
