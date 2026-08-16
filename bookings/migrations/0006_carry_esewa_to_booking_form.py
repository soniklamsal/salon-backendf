"""Carry the eSewa QR and its note from SiteSettings to BookingSection.

The two fields moved to the section they actually belong to — the booking form.
This has to run *between* the two schema migrations: after bookings.0005 adds
the new columns, and before core.0005 drops the old ones. `core.0005` depends on
this migration for exactly that reason.

Copies rather than assumes: if a QR was already uploaded it keeps working, and
the file itself is untouched (only the path is copied, and both models upload to
"payment/").
"""

from django.db import migrations


def carry_forward(apps, schema_editor):
    SiteSettings = apps.get_model("core", "SiteSettings")
    BookingSection = apps.get_model("bookings", "BookingSection")

    site = SiteSettings.objects.first()
    if site is None:
        return

    booking, _ = BookingSection.objects.get_or_create(pk=1)
    changed = False

    if getattr(site, "esewa_qr", None):
        booking.esewa_qr = site.esewa_qr
        changed = True
    # Only carry the note when it was edited away from the default, so an
    # untouched install does not overwrite the new model's own default.
    note = getattr(site, "esewa_note", "") or ""
    default = "Scan with eSewa, pay, then upload your payment screenshot below."
    if note and note != default:
        booking.esewa_note = note
        changed = True

    if changed:
        booking.save()


def back_out(apps, schema_editor):
    """Reverse: put them back on SiteSettings so the migration is undoable."""
    SiteSettings = apps.get_model("core", "SiteSettings")
    BookingSection = apps.get_model("bookings", "BookingSection")

    site = SiteSettings.objects.first()
    booking = BookingSection.objects.first()
    if site is None or booking is None:
        return

    if booking.esewa_qr:
        site.esewa_qr = booking.esewa_qr
    site.esewa_note = booking.esewa_note
    site.save()


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0005_bookingsection_esewa_note_bookingsection_esewa_qr_and_more"),
        # The old columns must still exist when this runs.
        ("core", "0004_alter_sitesettings_nav_cta_href"),
    ]

    operations = [migrations.RunPython(carry_forward, back_out)]
