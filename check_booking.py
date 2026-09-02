import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from bookings.models import Appointment

# Get the most recent booking
latest = Appointment.objects.order_by('-created_at').first()

if latest:
    print(f"Latest booking: {latest.reference}")
    print(f"Service: {latest.service}")
    print(f"Barber: {latest.barber}")
    print(f"Time slot: {latest.time_slot}")
    if latest.time_slot:
        print(f"  - Date: {latest.time_slot.date}")
        print(f"  - Time label: {latest.time_slot.time_label}")
        print(f"  - Start: {latest.time_slot.start_time}")
        print(f"  - End: {latest.time_slot.end_time}")
    print(f"Scheduled date: {latest.scheduled_date}")
    print(f"Scheduled time: {latest.scheduled_time}")
else:
    print("No bookings found")
