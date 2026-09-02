"""API views.

Reads are all public and read-only — the payload is literally the page the
world already sees. The only writable endpoints are the two enquiry forms,
which are rate-limited by scope.
"""

import logging

from django.contrib.auth import get_user_model
from django.db import DatabaseError, IntegrityError, transaction
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.generics import CreateAPIView
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.reverse import reverse

logger = logging.getLogger("api")

from api.serializers import (
    AboutSerializer,
    AppointmentCreateSerializer,
    AsSeenOnSerializer,
    BarberSerializer,
    BookingCopySerializer,
    ClassCardSerializer,
    ClassesSerializer,
    ContactMessageCreateSerializer,
    MyBookingSerializer,
    FollowUsSerializer,
    FooterSerializer,
    GallerySerializer,
    HeroSerializer,
    MotivationSerializer,
    NavLinkSerializer,
    OurStorySerializer,
    WhoWeAreSerializer,
    ServiceSerializer,
    SiteSettingsSerializer,
    SocialLinkSerializer,
    TimeSlotSerializer,
)
from bookings.models import Appointment, Barber, BookingSection, GoogleProfile, TimeSlot
from common.cache import cached_payload
from common.google_auth import user_from_request
from common.throttling import MyBookingsThrottle, ScreenshotThrottle
from common.notifications import (
    notify_new_booking,
    notify_new_contact_message,
)
from common.storage import reference_from_token, signed_url
from common.utils import resolve_image
from core.models import NavLink, SiteSettings, SocialLink
from core.notifications import record_new_booking, record_new_contact_message
from sections.models import (
    AboutSection,
    AsSeenOnSection,
    ClassCard,
    ClassesSection,
    FollowUsSection,
    FooterSection,
    GallerySection,
    HeroSection,
    MotivationSection,
    OurStorySection,
    Service,
    WhoWeAreSection,
)


# Built from the URL names rather than written out, because the hand-written
# version had already drifted — `my-bookings` was missing from it. Anything
# needing an argument (the screenshot route) is left out: there is no id to
# put in it here.
_ROOT_ROUTES = {
    "health": "health",
    "homepage": "homepage",
    "booking-config": "booking-config",
    "my-bookings": "my-bookings",
    "services": "service-list",
    "barbers": "barber-list",
    "classes": "classcard-list",
    "nav-links": "navlink-list",
    "social-links": "sociallink-list",
    "appointments": "appointment-create",
    "contact-messages": "contact-create",
}


@api_view(["GET"])
def api_root(request, format=None):
    return Response(
        {
            label: reverse(name, request=request, format=format)
            for label, name in _ROOT_ROUTES.items()
        }
    )


@api_view(["GET"])
def health(request, format=None):
    """Is the process up and can it reach the database?

    Deliberately says nothing else. A health check is unauthenticated by
    definition, so version numbers, hostnames and settings do not go in it.
    """
    from django.db import connection

    try:
        connection.ensure_connection()
    except DatabaseError:
        logger.exception("Health check failed: database unreachable")
        return Response({"status": "degraded"}, status=503)

    return Response({"status": "ok"})


@api_view(["GET"])
def homepage(request, format=None):
    """Everything the landing page needs, in one request.

    The page is one server-rendered document, so it should cost one round trip
    rather than eleven. The individual endpoints below still exist for anything
    that wants a single resource.

    Cached: thirteen serializers with their own queries, rebuilt identically on
    every request between admin edits. Saving any of the content behind it
    invalidates immediately -- see `common.cache`.
    """
    context = {"request": request}

    def build():
        return {
            "site": SiteSettingsSerializer(SiteSettings.load(), context=context).data,
            "navLinks": NavLinkSerializer(
                NavLink.objects.filter(is_published=True, show_in_header=True),
                many=True,
                context=context,
            ).data,
            "footerLinks": NavLinkSerializer(
                NavLink.objects.filter(is_published=True, show_in_footer=True),
                many=True,
                context=context,
            ).data,
            "socialLinks": SocialLinkSerializer(
                SocialLink.objects.filter(is_published=True), many=True, context=context
            ).data,
            "hero": HeroSerializer(HeroSection.load(), context=context).data,
            "whoWeAre": WhoWeAreSerializer(
                WhoWeAreSection.load(), context=context
            ).data,
            "motivation": MotivationSerializer(
                MotivationSection.load(), context=context
            ).data,
            "gallery": GallerySerializer(GallerySection.load(), context=context).data,
            "classes": ClassesSerializer(ClassesSection.load(), context=context).data,
            "ourStory": OurStorySerializer(OurStorySection.load(), context=context).data,
            "asSeenOn": AsSeenOnSerializer(AsSeenOnSection.load(), context=context).data,
            "followUs": FollowUsSerializer(FollowUsSection.load(), context=context).data,
            "footer": FooterSerializer(FooterSection.load(), context=context).data,
        }

    return Response(cached_payload("homepage", request, build))


@api_view(["GET"])
def about(request, format=None):
    """Everything /about-us needs, in one request.

    Separate from `homepage` rather than another key on it: the landing page
    renders none of this, and a team grid it will never draw is dead weight on
    the heaviest page on the site.
    """
    context = {"request": request}

    return Response(
        cached_payload(
            "about",
            request,
            lambda: AboutSerializer(AboutSection.load(), context=context).data,
        )
    )


class ReadOnlyPublishedViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """List/retrieve over published rows only."""

    model = None

    def get_queryset(self):
        return self.model.objects.filter(is_published=True)


class ServiceViewSet(ReadOnlyPublishedViewSet):
    model = Service
    serializer_class = ServiceSerializer


class BarberViewSet(ReadOnlyPublishedViewSet):
    model = Barber
    serializer_class = BarberSerializer
    
    from rest_framework.decorators import action
    
    @action(detail=True, methods=['get'], url_path='time-slots')
    def time_slots(self, request, pk=None):
        """Get available time slots for a specific barber.
        
        GET /api/v1/barbers/{id}/time-slots/?date=2026-09-02
        
        Returns all time slots for the barber on the specified date,
        showing which ones are available and which are booked.
        """
        from datetime import datetime
        
        barber = self.get_object()
        date_str = request.query_params.get('date')
        
        if not date_str:
            return Response({
                'error': 'date parameter is required (format: YYYY-MM-DD)'
            }, status=400)
        
        try:
            slot_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({
                'error': 'Invalid date format. Use YYYY-MM-DD'
            }, status=400)
        
        # Get all time slots for this barber on this date
        slots = TimeSlot.objects.filter(
            barber=barber,
            date=slot_date,
            is_published=True
        ).order_by('start_time', 'order')
        
        serializer = TimeSlotSerializer(slots, many=True, context={'request': request})
        
        return Response({
            'barber_id': barber.id,
            'barber_name': barber.name,
            'date': date_str,
            'slots': serializer.data
        })


@api_view(["GET"])
def booking_config(request, format=None):
    """Everything the booking form needs, in one request.

    Same reasoning as `homepage`: the /services page renders server-side and
    walks the customer through service -> barber -> details -> payment, so it
    should cost one round trip rather than three.

    `esewa.qr` is empty until someone uploads a QR in the admin. The form is
    built to render that step without an image rather than to break.
    """
    context = {"request": request}

    def build():
        booking = BookingSection.load()
        # Called directly rather than through ImageURLField: there is no
        # url-column counterpart for this one, and a field instantiated outside
        # a serializer would have no context to build an absolute URL from.
        qr = resolve_image(booking, "esewa_qr", url_attr=None, request=request)

        return {
            "services": ServiceSerializer(
                Service.objects.filter(is_published=True), many=True, context=context
            ).data,
            "barbers": BarberSerializer(
                Barber.objects.filter(is_published=True), many=True, context=context
            ).data,
            "esewa": {
                "qr": qr,
                "note": booking.esewa_note,
                "depositPercent": booking.deposit_percent,
            },
            "copy": BookingCopySerializer(booking, context=context).data,
        }

    return Response(cached_payload("booking-config", request, build))


class ClassCardViewSet(ReadOnlyPublishedViewSet):
    model = ClassCard
    serializer_class = ClassCardSerializer
    lookup_field = "slug"


class NavLinkViewSet(ReadOnlyPublishedViewSet):
    model = NavLink
    serializer_class = NavLinkSerializer


class SocialLinkViewSet(ReadOnlyPublishedViewSet):
    model = SocialLink
    serializer_class = SocialLinkSerializer


def _ensure_account_visible(claims):
    """Mirror a Google account into Django's Users, and mark it seen.

    Everything stored comes from claims that `common.google_auth` has already
    verified. There is no back-end call to Google to enrich it: unlike Clerk,
    Google publishes no "list my users" API, so a sign-in is the only moment
    this information exists and this is the only place it is captured.

    Two things this must not do. It must not raise: mirroring an account is a
    convenience for the admin sidebar, and a customer who has just paid should
    not lose the booking because of it. And it must not use check-then-create —
    a customer's first two bookings arriving together both saw "no profile yet"
    and the loser died on the unique constraint. `get_or_create` inside a
    savepoint makes the database settle it.
    """
    google_id = claims.get("sub")
    if not google_id:
        return

    try:
        with transaction.atomic():
            profile = GoogleProfile.objects.filter(google_user_id=google_id).first()
            if profile is not None:
                # Already mirrored. The only thing worth refreshing is when we
                # last heard from them - `update` rather than `save()` so two
                # concurrent bookings cannot clobber each other's fields.
                GoogleProfile.objects.filter(pk=profile.pk).update(
                    last_seen_at=timezone.now()
                )
                return

            User = get_user_model()
            user, created = User.objects.get_or_create(
                username=f"google_{google_id[-24:]}",
                defaults={"email": claims.get("email") or ""},
            )
            if created:
                user.set_unusable_password()
                user.save(update_fields=["password"])
            GoogleProfile.objects.get_or_create(
                google_user_id=google_id,
                defaults={
                    "user": user,
                    "image_url": claims.get("picture") or "",
                    "email_verified": bool(claims.get("email_verified")),
                    "last_seen_at": timezone.now(),
                },
            )
    except (IntegrityError, DatabaseError):
        # Lost the race to a concurrent request, which means the row it was
        # going to create now exists. Nothing to do and nothing to report.
        logger.info("Google account mirror skipped for %s (already created)", google_id)


def _never_cached(response):
    """Stop anything between here and the customer from keeping a copy.

    These responses are one person's bookings and one person's payment
    screenshot. With no Cache-Control at all -- which is what these sent before
    -- an intermediary is free to apply its own heuristic freshness to a 200,
    and a shared proxy or a browser's back/forward cache can then hand one
    customer's data to whoever asks next on the same connection. `private`
    alone is not enough: it permits a browser-local copy that survives sign-out
    on a shared machine, so `no-store` is the operative half.
    """
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    return response


@api_view(["GET"])
@throttle_classes([MyBookingsThrottle])
def my_bookings(request, format=None):
    """The signed-in customer's own bookings.

    The filter is the `sub` claim of a *verified* session token — never a query
    parameter or a header the caller controls — so there is no id to tamper
    with and no way to ask for somebody else's list.

    No token means an empty list rather than a 401: the section that renders
    this simply does not appear for signed-out visitors, and an error status
    would make that a console error on every anonymous page load.
    """
    claims = user_from_request(request) or {}
    google_id = claims.get("sub")
    if not google_id:
        return _never_cached(Response({"bookings": []}))

    queryset = (
        Appointment.objects.filter(google_user_id=google_id)
        .select_related("service", "barber", "time_slot")
        .order_by("-created_at")
    )
    return _never_cached(
        Response(
            {
                "bookings": MyBookingSerializer(
                    queryset, many=True, context={"request": request}
                ).data
            }
        )
    )


@api_view(["GET"])
@throttle_classes([ScreenshotThrottle])
def payment_screenshot(request, reference, format=None):
    """The payment screenshot for one booking, to the people entitled to it.

    This exists because the file itself is no longer reachable. Payment
    screenshots are financial records — a customer's name against an eSewa
    transfer — and they used to sit in MEDIA_ROOT, which the web server hands
    to anyone who asks for the path. Now they live in private storage and this
    is the only door.

    Three callers are allowed through:

    * the customer who made the booking, identified by the `sub` claim of a
      *verified* session token. The reference in the URL is not the credential;
      it selects the row, and the token decides whether that row is yours.
      Knowing somebody else's reference gets you a 404.
    * a signed-in Django staff user, which is how the salon checks a payment
      before approving it.
    * anyone holding a `?token=` minted for this exact booking. That exists
      because a browser will not put an Authorization header on an `<img>`
      request, so the customer's own status page could not otherwise display
      the thing it just proved they own. The token is signed, bound to one
      reference, and expires — see common.storage.screenshot_token.

    A booking with no screenshot, and a reference that does not exist, both
    return 404. They are deliberately indistinguishable: a different response
    for "exists but not yours" would confirm the reference is real.
    """
    booking = Appointment.objects.filter(reference=reference).first()
    if booking is None or not booking.payment_screenshot:
        raise NotFound("No screenshot for that booking.")

    user = getattr(request, "user", None)
    allowed = bool(user and user.is_authenticated and user.is_staff)

    if not allowed:
        token = request.query_params.get("token", "")
        # Compared against this booking's own reference, so a token minted for
        # one booking cannot be replayed against another.
        allowed = bool(token) and reference_from_token(token) == booking.reference

    if not allowed:
        claims = user_from_request(request) or {}
        google_id = claims.get("sub")
        # `google_user_id` is "" on bookings made before sign-in existed, so the
        # first half of this matters: an empty claim must not match an empty
        # column and let an anonymous caller through.
        allowed = bool(google_id) and google_id == booking.google_user_id

    if not allowed:
        # Same 404 as a missing booking — see the docstring.
        raise NotFound("No screenshot for that booking.")

    signed = signed_url(booking.payment_screenshot.name)
    if signed:
        # Cloudinary: hand over a signed URL rather than proxying the bytes.
        # The redirect carries a short-lived credential in its Location header,
        # so it must not be cached any more than the image itself.
        return _never_cached(HttpResponseRedirect(signed))

    # Local private storage: stream it, because nothing else can reach it.
    try:
        handle = booking.payment_screenshot.open("rb")
    except (FileNotFoundError, OSError):
        logger.warning("Screenshot missing on disk for %s", booking.reference)
        raise NotFound("No screenshot for that booking.")
    return _never_cached(FileResponse(handle, content_type="image/*"))


class AppointmentCreateView(CreateAPIView):
    serializer_class = AppointmentCreateSerializer
    # Multipart so the booking form can post its payment screenshot with the
    # rest of the fields in one request; JSON still works for the plain enquiry.
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    # Still IP-throttled rather than per-account: the endpoint stays reachable
    # without a session (see perform_create), so the account is not the limit.
    # Its own scope, tighter than the contact form's, because every request
    # here carries a file that costs storage.
    throttle_scope = "bookings"

    def perform_create(self, serializer):
        """Stamp the booking with the *verified* Google user, if there is one.

        The claims come from the signed session token, not from the request
        body — `google_user_id` is not a serializer field, so a client cannot
        post one and claim to be somebody else. The email is overwritten from
        the token for the same reason.

        A request with no valid token still succeeds, anonymously. Gating the
        booking page is the frontend's job; refusing here as well would mean a
        sign-in outage, or an expired tab, silently loses a real customer.
        """
        claims = user_from_request(self.request) or {}
        extra = {}
        if claims.get("sub"):
            extra["google_user_id"] = claims["sub"]
            # Always from the token, never from the body. The form shows this
            # address as a read-only field taken from the account, so the only
            # way a different one could arrive here is a caller editing the
            # request — and `email` is read-only on the serializer for exactly
            # that reason.
            # Only present when Google reported the address as verified —
            # `common.google_auth` drops it otherwise, so an unverified address
            # can never be stamped on a booking as the customer's own.
            token_email = claims.get("email")
            if token_email:
                extra["email"] = token_email
            # Make sure whoever just booked is visible under Users. Only the
            # claims already verified above are used.
            _ensure_account_visible(claims)
        appointment = serializer.save(**extra)
        # Queued, not sent: it goes out on a background thread once this
        # transaction commits, so a slow or unreachable Gmail costs the
        # customer nothing and cannot fail a booking that is already saved.
        notify_new_booking(appointment)
        # And the bell in the admin navbar, for whoever is already logged in
        # and looking at a different screen. Separate from the email because
        # they fail separately: see core/notifications.py.
        record_new_booking(appointment)


class ContactMessageCreateView(CreateAPIView):
    serializer_class = ContactMessageCreateSerializer
    throttle_scope = "submissions"

    def perform_create(self, serializer):
        """Stamp the enquiry with the *verified* Google user, if there is one.

        The claims come from the signed session token, not the request body, so
        a caller cannot post somebody else's id and attribute a message to them.
        `google_user_id` is not a serializer field, which is what makes that
        true rather than merely intended.

        A request with no valid token still succeeds, anonymously. The website
        only shows the form to a signed-in visitor, but gating it there is a
        product decision; refusing here as well would mean a sign-in outage
        silently loses a customer's enquiry.
        """
        claims = user_from_request(self.request) or {}
        extra = {}
        if claims.get("sub"):
            extra["google_user_id"] = claims["sub"]
            _ensure_account_visible(claims)
        message = serializer.save(**extra)
        notify_new_contact_message(message)
        record_new_contact_message(message)
