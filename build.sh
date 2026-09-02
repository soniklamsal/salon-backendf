#!/usr/bin/env bash
# Render build step. Runs with the service's env vars available, including
# DATABASE_URL, so migrate and the superuser bootstrap below reach the real DB.
set -o errexit

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Collect static files (WhiteNoise serves them in production)
python manage.py collectstatic --no-input

# Run database migrations
python manage.py migrate

# Create or refresh the admin superuser from env vars, idempotently. Runs only
# when all three are set; skipped otherwise. The password is reset on every
# deploy so the intended login always works on a fresh database -- if you later
# change the password in the admin, either clear DJANGO_SUPERUSER_PASSWORD or
# remove this block, or the next deploy will reset it.
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  python manage.py shell <<'PY'
import os
from django.contrib.auth import get_user_model

User = get_user_model()
user, created = User.objects.get_or_create(
    username=os.environ["DJANGO_SUPERUSER_USERNAME"],
    defaults={"email": os.environ.get("DJANGO_SUPERUSER_EMAIL", "")},
)
user.is_staff = user.is_superuser = user.is_active = True
user.set_password(os.environ["DJANGO_SUPERUSER_PASSWORD"])
if os.environ.get("DJANGO_SUPERUSER_EMAIL"):
    user.email = os.environ["DJANGO_SUPERUSER_EMAIL"]
user.save()
print(("Created" if created else "Refreshed"), "superuser:", user.username)
PY
fi
