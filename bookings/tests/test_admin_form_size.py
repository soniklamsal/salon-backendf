"""The admin pages that post a row per slot, against the field-count ceiling.

`DATA_UPLOAD_MAX_NUMBER_FIELDS` is global, and it was set to 200 to bound what
an anonymous booking can post -- a form of about a dozen fields. The admin is
not a public form: a changelist with editable columns posts every row on the
page at once, and an inline posts every row it renders. With a week of twelve
slots for four barbers that came to 518 fields on the time slot list and 795 on
a barber's own page, so ticking "Closed" and pressing Save was answered with a
bare 400 and nothing to say why.

These render the real pages against a real timetable and count what a save
would carry. They fail if the ceiling is lowered again, or if the timetable
grows past what the ceiling allows -- either way, before a member of staff
finds out by losing an edit.
"""

from datetime import time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from bookings.models import Barber, TimeSlot, Weekday
from common.testing import admin_static_storage

User = get_user_model()

#: The salon's day, as seeded: twelve 45-minute slots with an hour for lunch.
SLOTS_A_DAY = 12


def a_weeks_timetable(barber):
    """Twelve slots a day, every day -- what the salon actually runs."""
    start_minutes = [
        10 * 60, 10 * 60 + 45, 11 * 60 + 30, 12 * 60 + 15,
        14 * 60, 14 * 60 + 45, 15 * 60 + 30, 16 * 60 + 15,
        17 * 60, 17 * 60 + 45, 18 * 60 + 30, 19 * 60 + 15,
    ]
    assert len(start_minutes) == SLOTS_A_DAY
    TimeSlot.objects.bulk_create(
        [
            TimeSlot(
                barber=barber,
                weekday=day,
                start_time=time(minute // 60, minute % 60),
                end_time=time((minute + 45) // 60, (minute + 45) % 60),
                order=position,
            )
            for day in Weekday
            for position, minute in enumerate(start_minutes)
        ]
    )


@admin_static_storage
class AdminFormSizeTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_superuser("boss", "boss@x.com", "pw")
        self.client.force_login(self.staff)
        self.barber = Barber.objects.create(name="Kiran")
        a_weeks_timetable(self.barber)

    def field_count(self, url):
        """How many form fields a save of this page would carry."""
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        return sum(body.count(f"<{tag}") for tag in ("input", "select", "textarea"))

    def test_the_slot_list_fits_in_one_request(self):
        """`list_editable` posts every row on the page, not just the edited one."""
        fields = self.field_count(reverse("admin:bookings_timeslot_changelist"))
        self.assertLessEqual(
            fields,
            settings.DATA_UPLOAD_MAX_NUMBER_FIELDS,
            f"The time slot list posts {fields} fields and the ceiling is "
            f"{settings.DATA_UPLOAD_MAX_NUMBER_FIELDS}. Saving it answers 400.",
        )

    def test_a_barbers_own_page_fits_in_one_request(self):
        """The inline renders the barber's whole week, and posts all of it."""
        url = reverse("admin:bookings_barber_change", args=[self.barber.pk])
        fields = self.field_count(url)
        self.assertLessEqual(
            fields,
            settings.DATA_UPLOAD_MAX_NUMBER_FIELDS,
            f"A barber's page posts {fields} fields and the ceiling is "
            f"{settings.DATA_UPLOAD_MAX_NUMBER_FIELDS}. Saving it answers 400.",
        )

    def test_closing_a_slot_from_its_own_page_saves(self):
        """The edit staff reported: tick Closed, press Save."""
        slot = TimeSlot.objects.first()
        self.assertFalse(slot.is_booked)
        response = self.client.post(
            reverse("admin:bookings_timeslot_change", args=[slot.pk]),
            {
                "barber": slot.barber_id,
                "weekday": slot.weekday,
                "start_time": slot.start_time.strftime("%H:%M:%S"),
                "end_time": slot.end_time.strftime("%H:%M:%S"),
                "is_booked": "on",
                "is_published": "on",
                "order": slot.order,
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302)
        slot.refresh_from_db()
        self.assertTrue(slot.is_booked)
