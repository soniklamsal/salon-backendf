"""The admin, which is the salon's actual staff interface.

There is no staff-facing API — approving a booking, checking a payment and
answering an enquiry all happen here. That makes these actions production code
even though they are not endpoints.
"""

import io
import json
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from bookings.models import (
    Appointment,
    Barber,
    BookingSection,
    ContactMessage,
    TimeSlot,
)
from common.testing import admin_static_storage

User = get_user_model()


def png_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), "green").save(buffer, format="PNG")
    return buffer.getvalue()


@admin_static_storage
class AdminAccessTests(TestCase):
    def test_admin_requires_a_login(self):
        response = self.client.get(reverse("admin:bookings_appointment_changelist"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_a_mirrored_google_user_cannot_log_in(self):
        """They have no usable password, so this must fail rather than land."""
        User.objects.create(username="google_user_abc").set_unusable_password()
        logged_in = self.client.login(username="google_user_abc", password="")
        self.assertFalse(logged_in)


@admin_static_storage
class ApprovalActionTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_superuser("boss", "b@salon.test", "x" * 20)
        self.client.force_login(self.staff)
        self.url = reverse("admin:bookings_appointment_changelist")

    def run_action(self, action, bookings):
        return self.client.post(
            self.url,
            {
                "action": action,
                "_selected_action": [str(b.pk) for b in bookings],
            },
            follow=True,
        )

    def a_slot(self):
        """One bookable slot, of the kind a customer picks in the form."""
        from datetime import date, time

        barber = Barber.objects.create(name="Kiran")
        return TimeSlot.objects.create(
            barber=barber,
            date=date(2026, 9, 1),
            start_time=time(14, 0),
            end_time=time(15, 0),
        )

    def test_approve_issues_order_ids_to_the_selection(self):
        bookings = [Appointment.objects.create(name=f"C{i}") for i in range(3)]
        self.run_action("approve_bookings", bookings)

        for booking in bookings:
            booking.refresh_from_db()
            self.assertTrue(booking.order_id.startswith("ORD-"))
            self.assertEqual(booking.status, Appointment.Status.APPROVED)

    def test_approve_gives_each_booking_a_distinct_order_id(self):
        """A bulk update() would stamp them all with the same number."""
        bookings = [Appointment.objects.create(name=f"C{i}") for i in range(5)]
        self.run_action("approve_bookings", bookings)

        ids = {Appointment.objects.get(pk=b.pk).order_id for b in bookings}
        self.assertEqual(len(ids), 5)

    def test_approve_skips_cancelled_bookings(self):
        cancelled = Appointment.objects.create(
            name="Gone", status=Appointment.Status.CANCELLED
        )
        self.run_action("approve_bookings", [cancelled])

        cancelled.refresh_from_db()
        self.assertIsNone(cancelled.order_id)
        self.assertEqual(cancelled.status, Appointment.Status.CANCELLED)

    def test_approving_an_already_approved_booking_keeps_its_order_id(self):
        booking = Appointment.objects.create(name="Asha")
        first = booking.approve()
        self.run_action("approve_bookings", [booking])

        booking.refresh_from_db()
        self.assertEqual(booking.order_id, first)

    def test_complete_requires_approval_first(self):
        pending = Appointment.objects.create(name="Pending")
        self.run_action("complete_bookings", [pending])

        pending.refresh_from_db()
        self.assertEqual(pending.status, Appointment.Status.PENDING)

    def test_complete_marks_approved_bookings_done(self):
        booking = Appointment.objects.create(name="Asha")
        booking.approve()
        self.run_action("complete_bookings", [booking])

        booking.refresh_from_db()
        self.assertEqual(booking.status, Appointment.Status.COMPLETED)
        self.assertIsNotNone(booking.completed_at)

    def test_approving_warns_when_no_time_slot_was_chosen(self):
        """Otherwise the blank is only noticed when the customer asks.

        The customer picks their slot in the booking form, so a booking with
        none is either a legacy row or one entered by phone. Either way the
        salon has approved somebody without telling them when to come.
        """
        booking = Appointment.objects.create(name="No time given")
        response = self.run_action("approve_bookings", [booking])
        self.assertIn("No time slot selected", response.content.decode())

    def test_no_warning_when_the_customer_chose_a_slot(self):
        booking = Appointment.objects.create(name="Asha", time_slot=self.a_slot())
        response = self.run_action("approve_bookings", [booking])
        self.assertNotIn("No time slot selected", response.content.decode())

    def test_the_form_does_not_offer_a_typed_in_time(self):
        """The retired fields must not come back as editable inputs.

        `preferred_*` and `scheduled_*` are both legacy columns now: the time a
        customer comes in is `time_slot`, which they chose themselves. The
        admin shows it, read-only, rather than offering a second time for staff
        to type and disagree with.
        """
        from bookings.admin import AppointmentAdmin

        offered = {
            field
            for _, options in AppointmentAdmin.fieldsets
            for field in options["fields"]
        }
        self.assertNotIn("preferred_date", offered)
        self.assertNotIn("preferred_time", offered)
        self.assertNotIn("scheduled_date", offered)
        self.assertNotIn("scheduled_time", offered)
        self.assertIn("selected_time_display", offered)
        self.assertIn("selected_time_display", AppointmentAdmin.readonly_fields)

    def test_the_customers_chosen_slot_is_what_the_admin_shows(self):
        """The visit time is the slot the customer picked, not a staff entry."""
        slot = self.a_slot()
        booking = Appointment.objects.create(name="Asha", time_slot=slot)

        body = self.client.get(
            reverse("admin:bookings_appointment_change", args=[booking.pk])
        ).content.decode()

        self.assertIn(slot.time_label, body)
        self.assertIn(slot.date.strftime("%A, %B %d, %Y"), body)

    def test_the_message_reports_what_was_skipped(self):
        approved = Appointment.objects.create(name="Ready")
        approved.approve()
        pending = Appointment.objects.create(name="Not ready")

        response = self.run_action("complete_bookings", [approved, pending])
        body = response.content.decode()
        self.assertIn("1 booking(s) completed", body)
        self.assertIn("skipped", body)


@admin_static_storage
class AppointmentAdminDisplayTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._tmp = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.overridden = override_settings(PRIVATE_MEDIA_ROOT=self._tmp)
        self.overridden.enable()
        self.addCleanup(self.overridden.disable)

        self.staff = User.objects.create_superuser("boss", "b@salon.test", "x" * 20)
        self.client.force_login(self.staff)

    def test_change_page_renders_with_a_screenshot(self):
        """This is the regression: the preview used `.url`, which now raises."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        booking = Appointment.objects.create(
            name="Asha",
            payment_screenshot=SimpleUploadedFile(
                "p.png", png_bytes(), content_type="image/png"
            ),
        )
        response = self.client.get(
            reverse("admin:bookings_appointment_change", args=[booking.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(booking.reference, response.content.decode())

    def test_change_page_renders_without_a_screenshot(self):
        booking = Appointment.objects.create(name="Phone booking")
        response = self.client.get(
            reverse("admin:bookings_appointment_change", args=[booking.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("nothing uploaded", response.content.decode())

    def test_staff_can_load_the_screenshot_the_preview_points_at(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        booking = Appointment.objects.create(
            name="Asha",
            payment_screenshot=SimpleUploadedFile(
                "p.png", png_bytes(), content_type="image/png"
            ),
        )
        url = reverse("payment-screenshot", kwargs={"reference": booking.reference})
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_staff_can_still_attach_a_screenshot(self):
        """The custom widget removed the link, not the upload."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        booking = Appointment.objects.create(name="Phone booking")
        response = self.client.post(
            reverse("admin:bookings_appointment_change", args=[booking.pk]),
            {
                "name": "Phone booking",
                "email": "",
                "phone": "",
                "address": "",
                "notes": "",
                "status": Appointment.Status.PENDING,
                "payment_screenshot": SimpleUploadedFile(
                    "p.png", png_bytes(), content_type="image/png"
                ),
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        booking.refresh_from_db()
        self.assertTrue(booking.payment_screenshot)

    def test_the_form_never_renders_a_direct_file_link(self):
        """A link there would be an unauthorised URL straight to the file."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        booking = Appointment.objects.create(
            name="Asha",
            payment_screenshot=SimpleUploadedFile(
                "p.png", png_bytes(), content_type="image/png"
            ),
        )
        body = self.client.get(
            reverse("admin:bookings_appointment_change", args=[booking.pk])
        ).content.decode()
        self.assertNotIn("/private-media/", body)
        self.assertNotIn(f'href="/media/{booking.payment_screenshot.name}"', body)

    def test_changelist_loads(self):
        Appointment.objects.create(name="Asha")
        response = self.client.get(reverse("admin:bookings_appointment_changelist"))
        self.assertEqual(response.status_code, 200)

    def test_reference_and_order_id_are_not_editable(self):
        """They are issued by the system; typing one in would break the count."""
        from bookings.admin import AppointmentAdmin

        for field in ("reference", "order_id", "google_user_id", "approved_at"):
            self.assertIn(field, AppointmentAdmin.readonly_fields)


@admin_static_storage
@admin_static_storage
class VisitTimeDropdownTests(TestCase):
    """The visit time is picked from opening hours, not typed."""

    def setUp(self):
        self.staff = User.objects.create_superuser("boss", "b@salon.test", "x" * 20)
        self.client.force_login(self.staff)

    def form_for(self, booking=None):
        from bookings.admin import AppointmentAdminForm

        return AppointmentAdminForm(instance=booking)

    def options(self, booking=None):
        from django import forms

        widget = self.form_for(booking).fields["scheduled_time"].widget
        self.assertIsInstance(widget, forms.Select)
        return list(widget.choices)

    def test_the_field_is_a_dropdown_not_a_free_text_time(self):
        values = [value for value, _ in self.options()]
        self.assertIn("09:00:00", values)
        self.assertIn("19:00:00", values)

    def test_midnight_cannot_be_chosen(self):
        """A plain time input accepts 00:00; that is what this replaces."""
        self.assertNotIn("00:00:00", [value for value, _ in self.options()])

    def test_nothing_outside_opening_hours_is_offered(self):
        from datetime import time

        section = BookingSection.load()
        section.opens_at, section.closes_at = time(10, 0), time(16, 0)
        section.save()

        for value, _ in self.options():
            if not value:
                continue
            hour = int(value.split(":")[0])
            self.assertTrue(10 <= hour <= 16, value)

    def test_labels_read_like_a_person_says_them(self):
        labels = [label for _, label in self.options()]
        self.assertIn("9:00 am", labels)
        self.assertIn("12:00 noon", labels)
        self.assertIn("7:00 pm", labels)

    def test_a_blank_option_exists_because_the_time_is_optional(self):
        self.assertEqual(self.options()[0][0], "")

    def test_changing_opening_hours_changes_the_dropdown(self):
        from datetime import time

        section = BookingSection.load()
        section.opens_at, section.closes_at = time(7, 0), time(8, 0)
        section.slot_minutes = 60
        section.save()

        values = [value for value, _ in self.options() if value]
        self.assertEqual(values, ["07:00:00", "08:00:00"])

    def test_an_existing_out_of_hours_time_is_kept_as_an_option(self):
        """Otherwise opening the page silently resets a real booking to blank."""
        from datetime import time

        booking = Appointment.objects.create(name="Odd", scheduled_time=time(3, 14))
        options = self.options(booking)

        self.assertIn("03:14:00", [value for value, _ in options])
        self.assertIn(
            "3:14 am — outside opening hours", [label for _, label in options]
        )

    def test_saving_an_untouched_out_of_hours_booking_keeps_its_time(self):
        from datetime import time

        booking = Appointment.objects.create(name="Odd", scheduled_time=time(3, 14))
        self.client.post(
            reverse("admin:bookings_appointment_change", args=[booking.pk]),
            {
                "name": "Odd",
                "email": "",
                "phone": "",
                "address": "",
                "notes": "",
                "status": Appointment.Status.PENDING,
                "scheduled_date": "",
                "scheduled_time": "03:14:00",
            },
            follow=True,
        )
        booking.refresh_from_db()
        self.assertEqual(booking.scheduled_time, time(3, 14))

    def test_a_chosen_slot_is_a_valid_value_for_the_field(self):
        """The dropdown must accept what it offers.

        Asserted through the form rather than a POST: `scheduled_time` is a
        legacy column and is no longer on any fieldset, so the change screen
        does not render it and a POST would prove nothing about the widget.
        """
        from datetime import time

        form = self.form_for()
        self.assertIn("14:30:00", [value for value, _ in self.options()])
        self.assertEqual(
            form.fields["scheduled_time"].clean("14:30:00"), time(14, 30)
        )

    def test_the_existing_value_is_preselected(self):
        """A dropdown that renders unselected looks like the time was lost.

        Read off the bound form: the field is legacy and no longer rendered on
        the change screen, so scraping that page would assert nothing.
        """
        from datetime import time

        booking = Appointment.objects.create(name="Asha", scheduled_time=time(14, 30))
        body = str(self.form_for(booking)["scheduled_time"])
        self.assertIn('value="14:30:00" selected', body)


@admin_static_storage
class ContactMessageAdminTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_superuser("boss", "b@salon.test", "x" * 20)
        self.client.force_login(self.staff)

    def test_messages_cannot_be_created_in_the_admin(self):
        """They are a record of what someone sent, not content."""
        response = self.client.get(reverse("admin:bookings_contactmessage_add"))
        self.assertEqual(response.status_code, 403)

    def test_the_message_body_is_read_only(self):
        from bookings.admin import ContactMessageAdmin

        for field in ("name", "email", "subject", "message"):
            self.assertIn(field, ContactMessageAdmin.readonly_fields)

    def test_is_handled_is_the_one_editable_field(self):
        message = ContactMessage.objects.create(
            name="Asha", email="a@b.com", message="Hello"
        )
        self.assertFalse(message.is_handled)
        from bookings.admin import ContactMessageAdmin

        self.assertIn("is_handled", ContactMessageAdmin.list_editable)


@admin_static_storage
class BarberAdminTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_superuser("boss", "b@salon.test", "x" * 20)
        self.client.force_login(self.staff)

    def test_working_hours_are_dropdowns_not_free_text(self):
        from django import forms

        from bookings.admin import BarberAdminForm

        form = BarberAdminForm()
        for field in ("works_from", "works_to"):
            with self.subTest(field=field):
                widget = form.fields[field].widget
                self.assertIsInstance(widget, forms.Select)
                values = [value for value, _ in widget.choices if value]
                self.assertIn("09:00:00", values)
                self.assertNotIn("00:00:00", values)

    def test_an_existing_out_of_hours_shift_is_kept(self):
        from datetime import time

        from bookings.admin import BarberAdminForm

        barber = Barber.objects.create(name="Early", works_from=time(6, 0))
        choices = BarberAdminForm(instance=barber).fields["works_from"].widget.choices
        self.assertIn("06:00:00", [value for value, _ in choices])

    def test_a_shift_ending_before_it_starts_is_refused(self):
        """"7:00 pm – 10:00 am" on a card looks deliberate and goes unnoticed."""
        from datetime import time

        from bookings.admin import BarberAdminForm

        form = BarberAdminForm(
            data={
                "name": "Backwards",
                "role": "",
                "bio": "",
                "working_days": "",
                "works_from": time(19, 0),
                "works_to": time(10, 0),
                "is_available": True,
                "unavailable_note": "",
                "is_published": True,
                "order": 0,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("works_to", form.errors)

    def test_availability_can_be_toggled_from_the_list_page(self):
        """Taking someone off for the day should not need opening their page."""
        from bookings.admin import BarberAdmin

        self.assertIn("is_available", BarberAdmin.list_editable)
        self.assertIn("is_available", BarberAdmin.list_filter)

    def test_the_changelist_shows_who_is_bookable(self):
        Barber.objects.create(name="Here")
        Barber.objects.create(
            name="Away", is_available=False, unavailable_note="On holiday"
        )
        body = self.client.get(reverse("admin:bookings_barber_changelist")).content.decode()
        self.assertIn("Available", body)
        self.assertIn("On holiday", body)

    def test_barber_without_a_photo_still_renders(self):
        """Adding the row and uploading the picture happen at different times."""
        barber = Barber.objects.create(name="Ram")
        response = self.client.get(
            reverse("admin:bookings_barber_change", args=[barber.pk])
        )
        self.assertEqual(response.status_code, 200)


@admin_static_storage
class RowActionTests(TestCase):
    """Approving one booking without reloading the page.

    The bulk action is deliberately untouched and still covered above; these
    only check that the row button is the *same* code reached a different way,
    and that the ways it could be misused are closed.
    """

    def setUp(self):
        self.staff = User.objects.create_superuser("boss", "b@salon.test", "x" * 20)
        self.client.force_login(self.staff)
        self.booking = Appointment.objects.create(name="Asha")
        self.url = reverse("admin:bookings_appointment_ajax_action")

    def post(self, **body):
        return self.client.post(
            self.url, data=json.dumps(body), content_type="application/json"
        )

    def test_the_row_button_approves_and_issues_an_order_id(self):
        response = self.post(action="approve_bookings", pk=self.booking.pk)
        self.assertEqual(response.status_code, 200)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Appointment.Status.APPROVED)
        self.assertTrue(self.booking.order_id.startswith("ORD-"))

    def test_it_runs_the_same_code_as_the_bulk_action(self):
        """Two ways of approving must not become two implementations."""
        other = Appointment.objects.create(name="Ram")
        self.post(action="approve_bookings", pk=self.booking.pk)
        self.client.post(
            reverse("admin:bookings_appointment_changelist"),
            {"action": "approve_bookings", "_selected_action": [str(other.pk)]},
            follow=True,
        )
        self.booking.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(self.booking.status, other.status)
        self.assertTrue(self.booking.order_id)
        self.assertTrue(other.order_id)

    def test_the_action_message_comes_back_in_the_response(self):
        """The action's own message_user output, drained for the page to show."""
        body = self.post(action="approve_bookings", pk=self.booking.pk).json()
        self.assertTrue(body["messages"])
        self.assertIn("Approved", body["messages"][0]["text"])

    def test_the_warning_about_a_missing_visit_time_still_reaches_the_screen(self):
        """It is the whole reason the bulk action is reused rather than copied."""
        body = self.post(action="approve_bookings", pk=self.booking.pk).json()
        texts = " ".join(m["text"] for m in body["messages"])
        self.assertIn("No time slot selected", texts)

    def test_the_response_re_renders_the_status_pill(self):
        body = self.post(action="approve_bookings", pk=self.booking.pk).json()
        self.assertIn("Approved", body["cells"]["state"])

    def test_the_response_re_renders_the_buttons_so_the_row_catches_up(self):
        """An approved row must offer "Mark done", not "Approve" again."""
        body = self.post(action="approve_bookings", pk=self.booking.pk).json()
        self.assertIn("complete_bookings", body["cells"]["row_actions"])

    def test_approving_twice_keeps_one_order_id(self):
        """A double click must not issue a second number."""
        self.post(action="approve_bookings", pk=self.booking.pk)
        self.booking.refresh_from_db()
        first = self.booking.order_id
        self.post(action="approve_bookings", pk=self.booking.pk)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.order_id, first)

    def test_delete_selected_cannot_be_run_from_a_row(self):
        """It is registered on every ModelAdmin; the allowlist is what stops it."""
        response = self.post(action="delete_selected", pk=self.booking.pk)
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Appointment.objects.filter(pk=self.booking.pk).exists())

    def test_a_customer_supplied_name_is_escaped_in_the_response(self):
        """These cells are assigned with innerHTML, and customers pick the name."""
        self.booking.name = "<img src=x onerror=alert(1)>"
        self.booking.save()
        body = self.post(action="approve_bookings", pk=self.booking.pk).json()
        blob = "".join(body["cells"].values()) + str(body["messages"])
        self.assertNotIn("<img src=x", blob)

    def test_a_get_changes_nothing(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Appointment.Status.PENDING)

    def test_a_signed_out_request_cannot_approve(self):
        self.client.logout()
        response = self.post(action="approve_bookings", pk=self.booking.pk)
        self.assertEqual(response.status_code, 401)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Appointment.Status.PENDING)


@admin_static_storage
class RowActionMarkupTests(TestCase):
    """The button markup, which the JavaScript depends on and cannot fix."""

    def setUp(self):
        self.client.force_login(
            User.objects.create_superuser("boss", "b@salon.test", "x" * 20)
        )
        self.booking = Appointment.objects.create(name="Asha")
        self.url = reverse("admin:bookings_appointment_changelist")

    def test_the_buttons_are_type_button(self):
        """A bare <button> inside #changelist-form submits the whole changelist."""
        self.assertContains(self.client.get(self.url), 'type="button"')

    def test_the_buttons_render_disabled(self):
        """With no JavaScript a live-looking button that does nothing is worse
        than one that shows it is unavailable -- the bulk actions still work."""
        body = self.client.get(self.url).content.decode()
        self.assertIn('data-salon-action="approve_bookings"', body)
        self.assertIn("disabled", body)

    def test_the_row_carries_its_own_primary_key(self):
        """So the script never infers identity from a link that list_display_links
        may not have put there."""
        self.assertContains(
            self.client.get(self.url), 'data-salon-pk="{}"'.format(self.booking.pk)
        )

    def test_a_finished_booking_offers_no_button(self):
        self.booking.status = Appointment.Status.COMPLETED
        self.booking.save()
        self.assertNotContains(self.client.get(self.url), "data-salon-action")

    def test_the_changelist_still_marks_cells_with_field_classes(self):
        """Django's `td.field-<name>` is the contract the cell swap relies on."""
        self.assertContains(self.client.get(self.url), "field-state")


class ContactToggleTests(TestCase):
    """Marking an enquiry handled without re-POSTing the whole changelist."""

    def setUp(self):
        self.client.force_login(
            User.objects.create_superuser("boss", "b@salon.test", "x" * 20)
        )
        self.message = ContactMessage.objects.create(
            name="Asha", email="a@b.com", subject="Hours", message="When do you open?"
        )
        self.url = reverse("admin:bookings_contactmessage_ajax_toggle")

    def test_marking_it_handled_saves(self):
        response = self.client.post(
            self.url,
            data=json.dumps(
                {"pk": self.message.pk, "field": "is_handled", "value": True}
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.message.refresh_from_db()
        self.assertTrue(self.message.is_handled)

    def test_list_editable_is_kept_as_the_no_javascript_path(self):
        from bookings.admin import ContactMessageAdmin

        self.assertIn("is_handled", ContactMessageAdmin.list_editable)
