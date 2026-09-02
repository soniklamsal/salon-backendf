"""Booking status workflow, reference and order ID.

Three steps on purpose. `reference` is unique, and adding a unique column to a
table that already has rows would give every one of them the same empty string
and fail the constraint. So the column arrives without the constraint, a data
migration fills it in, and only then is uniqueness applied.

The same pass renames the old statuses: "new" -> "pending" and "confirmed" ->
"approved". Existing approved bookings also get an order ID, since staff would
otherwise have nothing to verify them against.
"""

import django.db.models.deletion
from django.db import migrations, models


def fill_in(apps, schema_editor):
    import secrets

    Appointment = apps.get_model("bookings", "Appointment")
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    used = set()

    # Deterministic order so re-running on a copy of the data numbers the
    # order IDs the same way.
    for row in Appointment.objects.order_by("created_at", "pk"):
        if not row.reference:
            while True:
                code = "SLN-" + "".join(secrets.choice(alphabet) for _ in range(6))
                if code not in used:
                    used.add(code)
                    break
            row.reference = code

        if row.status == "new":
            row.status = "pending"
        elif row.status == "confirmed":
            row.status = "approved"

        row.save(update_fields=["reference", "status"])

    # Anything already approved needs an order ID to be verifiable.
    approved = Appointment.objects.filter(status="approved", order_id__isnull=True)
    year_counter = {}
    for row in approved.order_by("created_at", "pk"):
        year = row.created_at.year
        year_counter[year] = year_counter.get(year, 0) + 1
        row.order_id = f"ORD-{year}-{year_counter[year]:04d}"
        row.save(update_fields=["order_id"])


def back_out(apps, schema_editor):
    Appointment = apps.get_model("bookings", "Appointment")
    Appointment.objects.filter(status="pending").update(status="new")
    Appointment.objects.filter(status="approved").update(status="confirmed")


class Migration(migrations.Migration):
    dependencies = [("bookings", "0011_clerkprofile")]

    operations = [
        # 1. Columns, without the unique constraint yet.
        #
        # No `db_index=True` here even though step 3 makes these unique. On
        # Postgres a CharField index is really two -- a btree and a `_like`
        # pattern index -- and creating one now (db_index) and then adding
        # `unique=True` in step 3 makes Django try to create the same `_like`
        # index twice, which aborts the whole migration with "relation ...
        # already exists". SQLite builds no pattern index, so it never showed
        # this locally. `unique=True` alone, added in step 3, builds the index
        # once; the final field the model declares is `unique=True` with no
        # `db_index`, so nothing downstream changes.
        migrations.AddField(
            model_name="appointment",
            name="reference",
            field=models.CharField(blank=True, default="", max_length=16),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="appointment",
            name="order_id",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="appointment",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="appointment",
            name="completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="appointment",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("approved", "Approved"),
                    ("completed", "Completed"),
                    ("cancelled", "Cancelled"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
        # 2. Populate, so no two rows share a value.
        migrations.RunPython(fill_in, back_out),
        # 3. Now the constraints can hold. `unique=True` builds the index on
        #    every backend; no `db_index=True` alongside it -- see step 1.
        migrations.AlterField(
            model_name="appointment",
            name="reference",
            field=models.CharField(
                blank=True,
                help_text="Shown to the customer on submit. Generated automatically.",
                max_length=16,
                unique=True,
            ),
        ),
        migrations.AlterField(
            model_name="appointment",
            name="order_id",
            field=models.CharField(
                blank=True,
                help_text="Created automatically on approval. Blank until then.",
                max_length=20,
                null=True,
                unique=True,
            ),
        ),
    ]
