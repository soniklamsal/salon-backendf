"""
Create test time slots for demonstration.
Run this from the backend directory: python create_test_slots.py
"""
import os
import django
from datetime import date, time, timedelta

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from bookings.models import Barber, TimeSlot

def create_test_slots():
    """Create test time slots for the next 7 days."""
    barbers = Barber.objects.all()
    
    if not barbers.exists():
        print("No barbers found. Please create barbers first.")
        return
    
    # Clear existing test slots
    TimeSlot.objects.all().delete()
    print("Cleared existing time slots.")
    
    # Time slots for a typical day
    time_slots = [
        (time(10, 0), time(11, 0)),
        (time(11, 0), time(12, 0)),
        (time(12, 0), time(13, 0)),
        (time(14, 0), time(15, 0)),  # After lunch
        (time(15, 0), time(16, 0)),
        (time(16, 0), time(17, 0)),
        (time(17, 0), time(18, 0)),
    ]
    
    today = date.today()
    slots_created = 0
    
    for barber in barbers:
        print(f"\nCreating slots for {barber.name}...")
        
        # Create slots for next 7 days
        for day_offset in range(7):
            slot_date = today + timedelta(days=day_offset)
            
            for order, (start, end) in enumerate(time_slots):
                # Make some slots booked (randomly - first and last of each day)
                is_booked = order in [0, len(time_slots) - 1]
                
                slot = TimeSlot.objects.create(
                    barber=barber,
                    date=slot_date,
                    start_time=start,
                    end_time=end,
                    is_booked=is_booked,
                    order=order,
                    is_published=True
                )
                slots_created += 1
                
                if is_booked:
                    print(f"  [{slot_date}] {slot.time_label} - BOOKED")
                else:
                    print(f"  [{slot_date}] {slot.time_label} - Available")
    
    print(f"\n✓ Created {slots_created} time slots for {barbers.count()} barbers over 7 days.")
    print(f"✓ Each day has {len(time_slots)} slots (some marked as booked for testing)")

if __name__ == "__main__":
    create_test_slots()
