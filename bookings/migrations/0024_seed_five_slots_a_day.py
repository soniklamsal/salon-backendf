"""Deliberately does nothing. Kept so the migration graph stays intact.

This once wiped every slot and seeded five a day for each barber. That was
wrong, and it was nearly destructive: the salon had already built its
timetable by hand in the admin -- 45-minute slots on Saturdays, a different
number of them for each barber, and a run of early-morning times for one of
them that nobody else has. A seed replaces all of that with the same five
rows per person, which is not a default so much as an erasure of the only
copy of that work.

Seeding is not a thing a deploy should do. It is a decision about the salon's
week, and it now lives where a decision belongs -- behind a command someone
runs on purpose:

    python manage.py seed_time_slots --reset --per-day 5

The file is emptied rather than deleted because it had already been recorded
as applied in at least one database, and removing it there would leave a hole
in the graph that `migrate` then refuses to plan around.

`0023` still runs and is still needed: that is the schema change that turns
dated slots into weekly ones, and it carries the salon's existing timetable
across rather than replacing it.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0023_alter_timeslot_options_and_more"),
    ]

    operations = []
