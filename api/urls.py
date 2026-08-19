from django.urls import include, path
from rest_framework.routers import SimpleRouter

from api import views

# SimpleRouter, not DefaultRouter: DefaultRouter adds its own view at "" under
# the name "api-root", which would collide with the hand-written one below.
router = SimpleRouter()
router.register("services", views.ServiceViewSet, basename="service")
router.register("barbers", views.BarberViewSet, basename="barber")
router.register("classes", views.ClassCardViewSet, basename="classcard")
router.register("nav-links", views.NavLinkViewSet, basename="navlink")
router.register("social-links", views.SocialLinkViewSet, basename="sociallink")

urlpatterns = [
    path("", views.api_root, name="api-root"),
    path("health/", views.health, name="health"),
    path("homepage/", views.homepage, name="homepage"),
    path("about/", views.about, name="about"),
    path("booking-config/", views.booking_config, name="booking-config"),
    path("my-bookings/", views.my_bookings, name="my-bookings"),
    # The reference selects the booking; the Clerk token in the header decides
    # whether the caller may see it. See views.payment_screenshot.
    path(
        "bookings/<str:reference>/screenshot/",
        views.payment_screenshot,
        name="payment-screenshot",
    ),
    path("appointments/", views.AppointmentCreateView.as_view(), name="appointment-create"),
    path("contact-messages/", views.ContactMessageCreateView.as_view(), name="contact-create"),
    path("", include(router.urls)),
]
