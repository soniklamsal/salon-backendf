import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from bookings.models import Appointment
from api.serializers import MyBookingSerializer

# Get latest booking
booking = Appointment.objects.order_by('-created_at').first()

if booking:
    print(f"\n=== BOOKING DATA ===")
    print(f"Reference: {booking.reference}")
    print(f"Service: {booking.service}")
    print(f"Barber: {booking.barber}")
    print(f"Time slot object: {booking.time_slot}")
    
    if booking.time_slot:
        print(f"\n=== TIME SLOT DETAILS ===")
        print(f"Date: {booking.time_slot.date}")
        print(f"Time label: {booking.time_slot.time_label}")
        print(f"Start: {booking.time_slot.start_time}")
        print(f"End: {booking.time_slot.end_time}")
    
    # Serialize it
    serializer = MyBookingSerializer(booking)
    data = serializer.data
    
    print(f"\n=== API RESPONSE (what frontend receives) ===")
    import json
    print(json.dumps(data, indent=2, default=str))
    
    print(f"\n=== CHECK selectedTimeSlot FIELD ===")
    if 'selectedTimeSlot' in data:
        print(f"✅ selectedTimeSlot EXISTS in API response")
        print(f"Value: {data['selectedTimeSlot']}")
    else:
        print(f"❌ selectedTimeSlot MISSING from API response!")
        print(f"Available fields: {list(data.keys())}")
else:
    print("No bookings found")
