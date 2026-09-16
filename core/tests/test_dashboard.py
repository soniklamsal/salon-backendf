"""The admin's front page.

It replaces Jazzmin's stock app list, and the risk in doing that is not that
the new page is wrong -- it is that the old one quietly goes missing. So the
first thing tested is that the app list and Recent actions survive.

After that: the numbers are right, they are cheap, and they are there without
any JavaScript. A dashboard is the page most likely to grow one more tile a
month until it is the slowest screen in the application, so the query count is
pinned rather than left to drift.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from bookings.models import Appointment, Barber, ContactMessage, TimeSlot, Weekday
from common.testing import admin_static_storage
from core.dashboard import dashboard_stats, pending_bookings
from sections.models import Service

User = get_user_model()


class DashboardStatsTests(TestCase):
    def setUp(self):
        self.service = Service.objects.create(label="Fresh Cut", is_published=True)

    def booking(self, **overrides):
        payload = {
            "name": "Asha",
            "phone": "9801234567",
            "address": "Thamel",
            "notes": "A trim",
            "service": self.service,
        }
        payload.update(overrides)
        return Appointment.objects.create(**payload)

    def a_slot(self, weekday=Weekday.SUNDAY):
        """One slot on the weekly timetable, of the kind a customer picks."""
        from datetime import time

        barber, _ = Barber.objects.get_or_create(name="Kiran")
        slot, _ = TimeSlot.objects.get_or_create(
            barber=barber,
            weekday=weekday,
            start_time=time(14, 0),
            end_time=time(15, 0),
        )
        return slot

    def test_it_counts_what_is_waiting(self):
        self.booking()
        self.booking()
        self.booking(status=Appointment.Status.COMPLETED)
        ContactMessage.objects.create(
            name="Ram", email="r@x.com", subject="Hi", message="Hello"
        )
        stats = dashboard_stats()
        self.assertEqual(stats["pending"], 2)
        self.assertEqual(stats["unhandled"], 1)

    def test_a_handled_enquiry_stops_being_counted(self):
        ContactMessage.objects.create(
            name="Ram", email="r@x.com", subject="Hi", message="Hello", is_handled=True
        )
        self.assertEqual(dashboard_stats()["unhandled"], 0)

    def test_it_counts_approved_bookings(self):
        """How much work is booked in -- the number staff want at a glance."""
        self.booking(status=Appointment.Status.APPROVED, time_slot=self.a_slot())
        self.booking(status=Appointment.Status.APPROVED)
        self.booking()
        self.booking(status=Appointment.Status.COMPLETED)
        self.booking(status=Appointment.Status.CANCELLED)
        self.assertEqual(dashboard_stats()["approved"], 2)

    def test_approved_does_not_count_the_other_statuses(self):
        """Pending is its own tile; completed and cancelled are done with."""
        self.booking()
        self.booking(status=Appointment.Status.COMPLETED)
        self.booking(status=Appointment.Status.CANCELLED)
        self.assertEqual(dashboard_stats()["approved"], 0)

    def test_a_slot_on_todays_weekday_counts_as_a_visit_today(self):
        """Slots repeat weekly, so "today" is a weekday match, not a date."""
        from django.utils import timezone

        today = timezone.localdate()
        self.booking(
            status=Appointment.Status.APPROVED,
            time_slot=self.a_slot(weekday=today.isoweekday() % 7),
        )
        self.assertEqual(dashboard_stats()["today"], 1)

    def test_a_slot_on_another_day_is_not_today(self):
        from django.utils import timezone

        today = timezone.localdate()
        self.booking(
            status=Appointment.Status.APPROVED,
            time_slot=self.a_slot(weekday=(today.isoweekday() + 3) % 7),
        )
        self.assertEqual(dashboard_stats()["today"], 0)

    def test_a_date_set_by_hand_beats_the_day_that_was_asked_for(self):
        """Staff move a booking by filling in the date, and it has to stick.

        Without this the booking would go on counting for the weekday of the
        slot it was originally booked into, on top of the date it was moved to.
        """
        from datetime import timedelta

        from django.utils import timezone

        today = timezone.localdate()
        self.booking(
            status=Appointment.Status.APPROVED,
            time_slot=self.a_slot(weekday=today.isoweekday() % 7),
            scheduled_date=today + timedelta(days=1),
        )
        self.assertEqual(dashboard_stats()["today"], 0)

    def test_the_numbers_cost_two_queries(self):
        """So adding a tile is a visible cost rather than a quiet N+1."""
        self.booking()
        with self.assertNumQueries(2):
            dashboard_stats()

    def test_the_waiting_list_does_not_query_per_row(self):
        """Each row renders its service and barber; without select_related
        that is two more queries per booking."""
        for _ in range(5):
            self.booking()
        with self.assertNumQueries(1):
            for booking in pending_bookings():
                str(booking.service)

    def test_it_works_on_an_empty_database(self):
        """The fresh-clone case: no bookings, no enquiries, no email settings."""
        stats = dashboard_stats()
        self.assertEqual(stats["pending"], 0)
        self.assertEqual(list(pending_bookings()), [])


@admin_static_storage
class DashboardPageTests(TestCase):
    def setUp(self):
        self.client.force_login(
            User.objects.create_superuser("boss", "b@salon.test", "x" * 20)
        )
        self.service = Service.objects.create(label="Fresh Cut", is_published=True)
        self.booking = Appointment.objects.create(
            name="Asha",
            phone="9801234567",
            address="Thamel",
            notes="A trim",
            service=self.service,
        )
        self.url = reverse("admin:index")

    def test_it_keeps_jazzmins_app_list_and_recent_actions(self):
        """The risk in replacing the index is not a wrong page, it is a lost one."""
        response = self.client.get(self.url)
        self.assertContains(response, "salon-stats")
        self.assertContains(response, "Recent actions")
        self.assertContains(response, "Site settings")

    def test_the_numbers_are_there_without_any_javascript(self):
        response = self.client.get(self.url)
        self.assertContains(response, "salon-stat__value")
        self.assertContains(response, "Waiting for approval")

    def test_there_is_exactly_one_hero_figure(self):
        """A second headline means neither is the headline."""
        body = self.client.get(self.url).content.decode()
        self.assertEqual(body.count("salon-stat__value--hero"), 1)

    def test_the_tiles_link_into_the_lists_they_count(self):
        """A number you cannot click into is a poster, not a place to start."""
        self.assertContains(self.client.get(self.url), "status__exact=pending")

    def test_a_waiting_booking_is_listed_with_its_action_button(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Asha")
        self.assertContains(response, "data-salon-action=\"approve_bookings\"")

    def test_the_listed_button_is_the_same_markup_the_changelist_uses(self):
        """Same Python method, so one script binding covers both."""
        dashboard = self.client.get(self.url).content.decode()
        changelist = self.client.get(
            reverse("admin:bookings_appointment_changelist")
        ).content.decode()
        marker = 'data-salon-pk="{}"'.format(self.booking.pk)
        self.assertIn(marker, dashboard)
        self.assertIn(marker, changelist)

    def test_an_empty_salon_says_so(self):
        Appointment.objects.all().delete()
        self.assertContains(self.client.get(self.url), "Nothing waiting")
