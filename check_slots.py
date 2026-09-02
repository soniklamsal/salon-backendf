import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from bookings.models import TimeSlot

total = TimeSlot.objects.count()
published = TimeSlot.objects.filter(is_published=True).count()
today_slots = TimeSlot.objects.filter(date='2026-09-01').count()
today_published = TimeSlot.objects.filter(date='2026-09-01', is_published=True).count()

print(f"Total slots in database: {total}")
print(f"Published slots: {published}")
print(f"Slots for 2026-09-01: {today_slots}")
print(f"Published slots for 2026-09-01: {today_published}")

# Show all dates with slots
from django.db.models import Count
dates_with_slots = TimeSlot.objects.values('date').annotate(count=Count('id')).order_by('date')
print("\nSlots per date:")
for item in dates_with_slots:
    print(f"  {item['date']}: {item['count']} slots")
