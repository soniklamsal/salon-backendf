"""Pull the signed-up accounts from Clerk into the admin.

    python manage.py sync_clerk_users

Clerk owns the accounts; this copies them so the admin can show who has signed
up and how they signed in. Safe to re-run — everything is matched on the Clerk
user id and updated in place, so it never duplicates a person.

Read-only against Clerk: nothing here creates, edits or deletes anything on
their side.
"""

from __future__ import annotations

from datetime import datetime, timezone

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from bookings.models import ClerkProfile

CLERK_API = "https://api.clerk.com/v1"
PAGE_SIZE = 100


def _dt(value):
    """Clerk sends epoch milliseconds; None stays None."""
    if not value:
        return None
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)


class Command(BaseCommand):
    help = "Copy Clerk accounts into the admin so signed-up users are visible."

    def add_arguments(self, parser):
        parser.add_argument(
            "--prune",
            action="store_true",
            help="Also remove local copies of accounts deleted in Clerk.",
        )

    def handle(self, *args, **options):
        secret = getattr(settings, "CLERK_SECRET_KEY", "")
        if not secret:
            raise CommandError(
                "CLERK_SECRET_KEY is not set in backend/.env — nothing to sync "
                "against. Copy it from the Clerk dashboard (API Keys)."
            )

        import requests

        User = get_user_model()
        session = requests.Session()
        session.headers.update({"Authorization": f"Bearer {secret}"})

        seen: set[str] = set()
        created = updated = 0
        offset = 0

        while True:
            response = session.get(
                f"{CLERK_API}/users",
                params={"limit": PAGE_SIZE, "offset": offset, "order_by": "-created_at"},
                timeout=30,
            )
            if response.status_code == 401:
                raise CommandError(
                    "Clerk rejected the secret key (401). Check CLERK_SECRET_KEY."
                )
            response.raise_for_status()
            batch = response.json()
            if not batch:
                break

            for item in batch:
                did_create = self._upsert(User, item)
                created += did_create
                updated += not did_create
                seen.add(item["id"])

            if len(batch) < PAGE_SIZE:
                break
            offset += PAGE_SIZE

        removed = 0
        if options["prune"]:
            stale = ClerkProfile.objects.exclude(clerk_user_id__in=seen)
            removed = stale.count()
            # The mirrored auth.User goes too: it exists only to carry this
            # profile, and leaving it behind would look like a real account.
            User.objects.filter(clerk_profile__in=stale).delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Synced {len(seen)} account(s): {created} new, {updated} updated"
                + (f", {removed} removed" if options["prune"] else "")
            )
        )

    @transaction.atomic
    def _upsert(self, User, item) -> bool:
        emails = item.get("email_addresses") or []
        primary_id = item.get("primary_email_address_id")
        primary = next(
            (e for e in emails if e.get("id") == primary_id),
            emails[0] if emails else None,
        )
        email = (primary or {}).get("email_address", "") or ""
        verified = ((primary or {}).get("verification") or {}).get("status") == "verified"

        # Every way this person can sign in, across all their linked emails.
        #
        # Clerk reports an OAuth-verified email as `from_oauth_google` while the
        # linked account itself is `oauth_google`. They are the same sign-in
        # route, so the prefix is stripped before deduping — otherwise a plain
        # Google signup shows up as two providers.
        raw = {
            v.get("strategy")
            for e in emails
            for v in [e.get("verification") or {}]
            if v.get("strategy")
        } | {
            f"oauth_{a.get('provider')}".replace("oauth_oauth_", "oauth_")
            for a in (item.get("external_accounts") or [])
            if a.get("provider")
        }
        providers = sorted({p.replace("from_oauth_", "oauth_") for p in raw})

        phones = item.get("phone_numbers") or []
        phone = (phones[0] or {}).get("phone_number", "") if phones else ""

        profile = ClerkProfile.objects.filter(clerk_user_id=item["id"]).first()
        is_new = profile is None

        # Username must be unique and stable; the Clerk id always is, whereas
        # an email can be changed or shared with the staff superuser.
        username = f"clerk_{item['id'][-24:]}"
        if is_new:
            # get_or_create, not create: the mirrored user row can outlive its
            # profile — deleting a Clerk account in the admin removes the
            # profile and leaves the user, and `_ensure_account_visible` builds
            # a row with this same username. A plain create() then raises on
            # the unique constraint and aborts the whole sync for everybody,
            # because one person deleted one row.
            user, was_created = User.objects.get_or_create(
                username=username, defaults={"email": email}
            )
            if was_created:
                # Authentication happens in Clerk. An unusable password means
                # this row cannot be used to log into Django at all.
                user.set_unusable_password()
            else:
                user.email = email
        else:
            user = profile.user
            user.email = email

        user.first_name = (item.get("first_name") or "")[:150]
        user.last_name = (item.get("last_name") or "")[:150]
        user.save()

        ClerkProfile.objects.update_or_create(
            clerk_user_id=item["id"],
            defaults={
                "user": user,
                "providers": ",".join(providers),
                "image_url": item.get("image_url") or "",
                "phone": phone,
                "email_verified": verified,
                "banned": bool(item.get("banned")),
                "clerk_created_at": _dt(item.get("created_at")),
                "last_sign_in_at": _dt(item.get("last_sign_in_at")),
                "last_synced_at": datetime.now(tz=timezone.utc),
            },
        )
        return is_new
