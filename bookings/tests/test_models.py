"""Model-level behaviour: reference allocation, approval, ordering.

These cover the two places the booking flow allocates a unique identifier by
reading the database and then writing — the shape that breaks under concurrent
requests and had been failing silently as a 500.
"""

from datetime import time, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from bookings.models import Appointment, Barber, BookingSection, label_time


class ReferenceAllocationTests(TestCase):
    def test_reference_is_assigned_on_create(self):
        booking = Appointment.objects.create(name="Asha")
        self.assertTrue(booking.reference.startswith("SLN-"))
        self.assertEqual(len(booking.reference), 10)

    def test_reference_alphabet_excludes_confusable_characters(self):
        # The code gets read out over the phone; I/O/1/0 are the pairs people
        # mishear and mistype.
        for _ in range(50):
            code = Appointment._make_reference()
            self.assertNotRegex(code[4:], r"[IO10]")

    def test_reference_is_stable_across_saves(self):
        booking = Appointment.objects.create(name="Asha")
        original = booking.reference
        booking.name = "Asha B"
        booking.save()
        booking.refresh_from_db()
        self.assertEqual(booking.reference, original)

    def test_collision_is_retried_rather_than_raising(self):
        """A duplicate code must cost a retry, not a 500.

        The generator is forced to hand out a code that already exists once,
        which is exactly what two simultaneous submissions produce.
        """
        existing = Appointment.objects.create(name="First")

        codes = iter([existing.reference, "SLN-ZZZ999"])
        with patch.object(Appointment, "_make_reference", side_effect=lambda: next(codes)):
            second = Appointment.objects.create(name="Second")

        self.assertEqual(second.reference, "SLN-ZZZ999")
        self.assertEqual(Appointment.objects.count(), 2)

    def test_gives_up_after_repeated_collisions(self):
        existing = Appointment.objects.create(name="First")
        with patch.object(Appointment, "_make_reference", return_value=existing.reference):
            with self.assertRaises(Exception):
                Appointment.objects.create(name="Second")

    def test_unrelated_integrity_error_is_not_retried(self):
        """A collision on something else must surface, not spin ten times."""
        first = Appointment.objects.create(name="First")
        first.approve()

        clash = Appointment(name="Second", order_id=first.order_id)
        with self.assertRaises(Exception):
            clash.save()


class ApprovalTests(TestCase):
    def test_approve_issues_sequential_order_ids(self):
        ids = [Appointment.objects.create(name=f"C{i}").approve() for i in range(3)]
        suffixes = [int(oid.rsplit("-", 1)[1]) for oid in ids]
        self.assertEqual(suffixes, [1, 2, 3])

    def test_approve_sets_status_and_timestamp(self):
        booking = Appointment.objects.create(name="Asha")
        booking.approve()
        booking.refresh_from_db()
        self.assertEqual(booking.status, Appointment.Status.APPROVED)
        self.assertIsNotNone(booking.approved_at)

    def test_approve_is_idempotent(self):
        booking = Appointment.objects.create(name="Asha")
        first = booking.approve()
        approved_at = booking.approved_at
        second = booking.approve()
        self.assertEqual(first, second)
        self.assertEqual(booking.approved_at, approved_at)

    def test_order_id_is_unique_across_bookings(self):
        a = Appointment.objects.create(name="A").approve()
        b = Appointment.objects.create(name="B").approve()
        self.assertNotEqual(a, b)

    def test_complete_requires_nothing_but_records_when(self):
        booking = Appointment.objects.create(name="Asha")
        booking.approve()
        booking.complete()
        booking.refresh_from_db()
        self.assertEqual(booking.status, Appointment.Status.COMPLETED)
        self.assertIsNotNone(booking.completed_at)


class SchedulingTests(TestCase):
    """The visit time, which only the salon sets."""

    def setUp(self):
        self.day = timezone.localdate() + timedelta(days=3)
        self.at = time(11, 0)

    def test_a_time_set_by_staff_survives_approval(self):
        booking = Appointment.objects.create(
            name="Asha", scheduled_date=self.day, scheduled_time=self.at
        )
        booking.approve()
        booking.refresh_from_db()

        self.assertEqual(booking.scheduled_date, self.day)
        self.assertEqual(booking.scheduled_time, self.at)

    def test_approving_without_a_time_leaves_the_schedule_empty(self):
        """No time is invented. The status page says so, rather than guessing."""
        booking = Appointment.objects.create(name="Phone booking")
        booking.approve()
        booking.refresh_from_db()

        self.assertIsNone(booking.scheduled_date)
        self.assertIsNone(booking.scheduled_time)

    def test_re_approving_does_not_overwrite_a_later_change(self):
        """Staff move the booking after approving; approve() must not undo it."""
        booking = Appointment.objects.create(
            name="Asha", scheduled_date=self.day, scheduled_time=self.at
        )
        booking.approve()

        booking.scheduled_time = time(9, 0)
        booking.save()
        booking.approve()
        booking.refresh_from_db()

        self.assertEqual(booking.scheduled_time, time(9, 0))

    def test_an_old_booking_keeps_the_time_it_was_made_with(self):
        """`preferred_*` is retired but older rows still carry one, and losing
        it on approval would strand a real customer with no time at all."""
        booking = Appointment.objects.create(
            name="Legacy", preferred_date=self.day, preferred_time=time(14, 30)
        )
        booking.approve()
        booking.refresh_from_db()

        self.assertEqual(booking.scheduled_date, self.day)
        self.assertEqual(booking.scheduled_time, time(14, 30))


class TimeSlotTests(TestCase):
    """The list of times the admin dropdown offers."""

    def slots(self, **kwargs):
        section = BookingSection(**kwargs)
        return section.time_slots()

    def test_defaults_cover_a_working_day_on_the_half_hour(self):
        slots = BookingSection().time_slots()
        self.assertEqual(slots[0], time(9, 0))
        self.assertEqual(slots[-1], time(19, 0))
        self.assertEqual(len(slots), 21)

    def test_closing_time_is_offered(self):
        """It is described as the last appointment, not the moment you lock up."""
        slots = self.slots(opens_at=time(9, 0), closes_at=time(10, 0), slot_minutes=30)
        self.assertEqual(slots, [time(9, 0), time(9, 30), time(10, 0)])

    def test_hourly_and_quarter_hourly_intervals(self):
        self.assertEqual(
            self.slots(opens_at=time(9, 0), closes_at=time(11, 0), slot_minutes=60),
            [time(9, 0), time(10, 0), time(11, 0)],
        )
        self.assertEqual(
            len(self.slots(opens_at=time(9, 0), closes_at=time(10, 0), slot_minutes=15)),
            5,
        )

    def test_no_slot_falls_outside_opening_hours(self):
        """The whole point — 3am must not be selectable."""
        for slot in self.slots(
            opens_at=time(9, 0), closes_at=time(19, 0), slot_minutes=30
        ):
            self.assertGreaterEqual(slot, time(9, 0))
            self.assertLessEqual(slot, time(19, 0))

    def test_midnight_is_never_offered_by_default(self):
        self.assertNotIn(time(0, 0), BookingSection().time_slots())

    def test_closing_before_opening_still_gives_something_to_pick(self):
        """A typo must not leave staff with an empty dropdown and no clue why."""
        slots = self.slots(opens_at=time(18, 0), closes_at=time(9, 0), slot_minutes=30)
        self.assertEqual(slots, [time(18, 0)])

    def test_an_uneven_interval_stops_before_closing(self):
        """09:00-10:00 every 45 minutes has no slot at 10:00, and must not
        invent one past closing."""
        slots = self.slots(opens_at=time(9, 0), closes_at=time(10, 0), slot_minutes=45)
        self.assertEqual(slots, [time(9, 0), time(9, 45)])


class TimeLabelTests(TestCase):
    def test_reads_the_way_a_person_says_it(self):
        cases = {
            time(0, 0): "12:00 midnight",
            time(12, 0): "12:00 noon",
            time(9, 0): "9:00 am",
            time(9, 30): "9:30 am",
            time(13, 15): "1:15 pm",
            time(19, 0): "7:00 pm",
            time(12, 30): "12:30 pm",
            time(0, 30): "12:30 am",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(label_time(value), expected)


class BarberTests(TestCase):
    def test_initials_take_first_two_words(self):
        self.assertEqual(Barber(name="Ram Bahadur Thapa").initials, "RB")

    def test_schedule_omits_missing_parts_without_stray_separators(self):
        self.assertEqual(Barber(name="R", working_days="Sun – Fri").schedule, "Sun – Fri")
        self.assertEqual(Barber(name="R").schedule, "")

    def test_schedule_formats_twelve_hour_clock(self):
        barber = Barber(name="R", works_from=time(10, 0), works_to=time(19, 30))
        self.assertEqual(barber.schedule, "10:00 am – 7:30 pm")

    def test_schedule_handles_only_one_end_being_set(self):
        self.assertEqual(Barber(name="R", works_from=time(10, 0)).schedule, "from 10:00 am")
        self.assertEqual(Barber(name="R", works_to=time(19, 0)).schedule, "until 7:00 pm")

    def test_schedule_says_noon_the_way_the_booking_dropdown_does(self):
        barber = Barber(name="R", works_from=time(12, 0), works_to=time(18, 0))
        self.assertEqual(barber.schedule, "12:00 noon – 6:00 pm")

    def test_barbers_are_available_by_default(self):
        """Adding a barber should not require remembering to switch them on."""
        self.assertTrue(Barber(name="R").is_available)

    def test_availability_label_reads_for_the_badge(self):
        self.assertEqual(Barber(name="R").availability_label, "Available")
        self.assertEqual(
            Barber(name="R", is_available=False).availability_label, "Not available"
        )
        self.assertEqual(
            Barber(
                name="R", is_available=False, unavailable_note="Back on 20 August"
            ).availability_label,
            "Back on 20 August",
        )

    def test_a_note_is_ignored_while_the_barber_is_available(self):
        """A stale note from last month must not label a working barber."""
        barber = Barber(name="R", is_available=True, unavailable_note="On holiday")
        self.assertEqual(barber.availability_label, "Available")
