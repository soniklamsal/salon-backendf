"""Fill the weekly timetable with bookable slots.

Slots repeat weekly, so this is a one-off setup chore rather than something
anyone should run on a schedule: it gives each barber the salon's standard
week, and staff then adjust it in the admin.

    python manage.py seed_time_slots                   # fill in what is missing
    python manage.py seed_time_slots --reset           # rebuild from scratch
    python manage.py seed_time_slots --per-day 5       # five times a day
    python manage.py seed_time_slots --days sun,mon    # only those days
    python manage.py seed_time_slots --barber "Ram"    # only that barber

The times come from the Booking form's opening hours rather than a list kept
here, so the shop's day is defined in exactly one place -- change `opens_at`,
`closes_at` or `slot_minutes` in the admin and re-run.

Without `--reset` existing rows are left alone, so a run can never quietly
undo an edit or reopen a slot the salon closed on purpose.
"""

from datetime import date, datetime, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from bookings.models import Barber, BookingSection, TimeSlot, Weekday


def slot_ranges(section):
    """Every (start, end) pair the salon's opening hours imply.

    `BookingSection.time_slots()` is the same list the admin's visit-time
    dropdown is built from, so a seeded slot can always be picked there too.
    """
    length = timedelta(minutes=section.slot_minutes or 30)
    # Any date works; it is only here so times can be added to.
    anchor = date.today()
    for start in section.time_slots():
        end = (datetime.combine(anchor, start) + length).time()
        # A slot that wraps past midnight is a misconfiguration, not a late
        # night, and storing end < start would make the range nonsense.
        if end > start:
            yield start, end


def pick_evenly(ranges, count):
    """Thin `ranges` down to `count`, spread across the day.

    Taking the first few instead would bunch every appointment into the
    morning and leave the afternoon looking shut. Spreading them keeps the
    first and last opening times as the endpoints and spaces the rest between,
    so five slots on a 9-to-7 day come out as 9:00, 11:30, 2:00, 4:30, 7:00
    rather than 9:00 through 11:00.
    """
    if count is None or count <= 0 or count >= len(ranges):
        return ranges
    if count == 1:
        return ranges[:1]
    last = len(ranges) - 1
    # `dict.fromkeys` rather than a set: it keeps the order, and rounding can
    # land two steps on the same index when `count` is close to `len(ranges)`.
    indexes = dict.fromkeys(round(i * last / (count - 1)) for i in range(count))
    return [ranges[i] for i in indexes]


def parse_days(raw):
    """"sun,mon" -> the matching weekdays, in the salon's order."""
    if not raw:
        return list(Weekday)
    wanted = []
    for part in raw.split(","):
        name = part.strip().lower()
        if not name:
            continue
        match = [day for day in Weekday if day.label.lower().startswith(name)]
        if not match:
            raise CommandError(
                f"'{part.strip()}' is not a day. Use names like sun, mon, tuesday."
            )
        wanted.append(match[0])
    return wanted or list(Weekday)


class Command(BaseCommand):
    help = "Give every barber a week of bookable slots."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete the barbers' existing slots first, then rebuild.",
        )
        parser.add_argument(
            "--per-day",
            type=int,
            default=0,
            help=(
                "How many slots each barber offers per day, spread across "
                "opening hours. Default: one per opening time."
            ),
        )
        parser.add_argument(
            "--days",
            default="",
            help='Comma separated, e.g. "sun,mon". Default: every day.',
        )
        parser.add_argument(
            "--barber",
            action="append",
            default=[],
            help="Barber name (repeatable). Default: every published barber.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        section = BookingSection.load()
        days = parse_days(options["days"])

        barbers = Barber.objects.filter(is_published=True).order_by("order", "id")
        names = options["barber"]
        if names:
            barbers = barbers.filter(name__in=names)
            missing = set(names) - set(barbers.values_list("name", flat=True))
            if missing:
                raise CommandError("No published barber named: " + ", ".join(sorted(missing)))
        if not barbers.exists():
            raise CommandError("No published barbers to seed. Add one first.")

        ranges = list(slot_ranges(section))
        if not ranges:
            raise CommandError(
                "The Booking form's opening hours produce no slots. Check "
                "opens_at, closes_at and slot_minutes in the admin."
            )
        ranges = pick_evenly(ranges, options["per_day"])

        if options["reset"]:
            removed, _ = TimeSlot.objects.filter(
                barber__in=barbers, weekday__in=days
            ).delete()
            self.stdout.write(f"Removed {removed} existing slot(s).")

        created = kept = 0
        for barber in barbers:
            for day in days:
                # `order` follows the time, so the admin's own ordering column
                # does not have to be filled in by hand for a seeded week.
                for position, (start, end) in enumerate(ranges):
                    _, was_created = TimeSlot.objects.get_or_create(
                        barber=barber,
                        weekday=day,
                        start_time=start,
                        end_time=end,
                        defaults={"order": position, "is_booked": False},
                    )
                    if was_created:
                        created += 1
                    else:
                        kept += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created} slot(s): {len(ranges)} a day for "
                f"{barbers.count()} barber(s) across {len(days)} day(s); "
                f"left {kept} existing slot(s) alone."
            )
        )
