"""Move the account columns from Clerk to Google sign-in.

Written by hand rather than generated. `makemigrations` sees a renamed field as
a drop and an add unless it is told otherwise, and answering its prompts is not
something a deploy can do — so the renames are spelled out here, where they
keep the data in the column instead of throwing it away.

The profile table loses six columns. They existed to hold what Clerk's back-end
API reported about an account (provider, phone, ban state, its own timestamps),
and there is no equivalent call to Google, so nothing would ever write to them
again. `last_seen_at` replaces `last_sign_in_at`: the API cannot observe a
sign-in any more, only a request arriving with a valid token.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0021_timeslot_appointment_time_slot_and_more"),
    ]

    operations = [
        # The index leads with the column being renamed, so it comes out first
        # and goes back on under its new name at the end. Dropping and
        # recreating is cheap here and portable across the three databases this
        # project runs on; an in-place rename is not.
        migrations.RemoveIndex(
            model_name="appointment",
            name="appt_clerk_created_idx",
        ),
        migrations.RenameField(
            model_name="appointment",
            old_name="clerk_user_id",
            new_name="google_user_id",
        ),
        migrations.RenameField(
            model_name="contactmessage",
            old_name="clerk_user_id",
            new_name="google_user_id",
        ),
        migrations.AlterField(
            model_name="appointment",
            name="google_user_id",
            field=models.CharField(
                blank=True,
                help_text="Google account id. Set automatically; not editable by the customer.",
                max_length=64,
            ),
        ),
        migrations.AlterField(
            model_name="contactmessage",
            name="google_user_id",
            field=models.CharField(
                blank=True,
                help_text="Google account id. Set automatically; not editable by the sender.",
                max_length=64,
            ),
        ),
        migrations.AddIndex(
            model_name="appointment",
            index=models.Index(
                fields=["google_user_id", "-created_at"],
                name="appt_google_created_idx",
            ),
        ),
        # --- the profile table ------------------------------------------
        migrations.RenameModel(
            old_name="ClerkProfile",
            new_name="GoogleProfile",
        ),
        migrations.RenameField(
            model_name="googleprofile",
            old_name="clerk_user_id",
            new_name="google_user_id",
        ),
        migrations.RenameField(
            model_name="googleprofile",
            old_name="last_sign_in_at",
            new_name="last_seen_at",
        ),
        migrations.RemoveField(model_name="googleprofile", name="providers"),
        migrations.RemoveField(model_name="googleprofile", name="phone"),
        migrations.RemoveField(model_name="googleprofile", name="banned"),
        migrations.RemoveField(model_name="googleprofile", name="clerk_created_at"),
        migrations.RemoveField(model_name="googleprofile", name="last_synced_at"),
        migrations.AlterField(
            model_name="googleprofile",
            name="user",
            field=models.OneToOneField(
                on_delete=models.deletion.CASCADE,
                related_name="google_profile",
                to="auth.user",
            ),
        ),
        migrations.AlterModelOptions(
            name="googleprofile",
            options={
                "ordering": ["-last_seen_at", "-created_at"],
                "verbose_name": "Google account",
                "verbose_name_plural": "Google accounts",
            },
        ),
    ]
