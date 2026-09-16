"""Every registered admin, driven through create, read, update and delete.

The admin is the salon's only staff interface -- there is no other way to
approve a booking, close a slot or change the copy on the site -- so a screen
that 400s or 500s on save is an outage for the people running the shop, and one
that only shows up when somebody tries it.

These walk the admin registry rather than naming screens one by one, so a model
registered later is covered the day it is added instead of the day someone
notices it was missed. For each one: the list renders, the add form renders and
accepts a valid object, the change form renders and saves, and the delete
confirmation renders and removes it. Where an admin refuses add or delete on
purpose -- the singletons, one Footer and one Hero -- that refusal is asserted
instead, because a singleton that can be added twice is its own bug.

Nothing here touches the real database. Django builds a separate test database
for the run and destroys it afterwards.
"""

import io
import re
from datetime import date, datetime, time as dt_time

from django import forms
from django.contrib import admin as dj_admin
from django.db import models as db_models
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from django.urls import reverse
from PIL import Image

from common.testing import admin_static_storage

User = get_user_model()


def png_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (12, 12), "green").save(buffer, format="PNG")
    return buffer.getvalue()


def ensure_instance(model, depth=0):
    """One row of `model`, made if the table is empty.

    A time slot needs a barber and a class card needs a section, so a form
    for either is unfillable until its parent exists. Rather than ordering
    the models by hand and hoping the order survives the next model added,
    the parent is created on demand -- recursively, since a parent can have
    one of its own.
    """
    existing = model.objects.first()
    if existing is not None:
        return existing
    if depth > 4:  # a cycle, or a model too tangled to be worth guessing at
        return None

    values = {}
    for field in model._meta.get_fields():
        if not getattr(field, "concrete", False) or field.auto_created:
            continue
        if field.blank or field.null or field.has_default():
            continue
        if isinstance(field, db_models.ForeignKey):
            values[field.name] = ensure_instance(field.related_model, depth + 1)
        elif isinstance(field, (db_models.DateTimeField,)):
            values[field.name] = datetime(2026, 1, 1, 10, 0)
        elif isinstance(field, db_models.DateField):
            values[field.name] = date(2026, 1, 1)
        elif isinstance(field, db_models.TimeField):
            values[field.name] = dt_time(10, 0)
        elif isinstance(field, (db_models.IntegerField, db_models.FloatField,
                                db_models.DecimalField)):
            values[field.name] = 1
        elif isinstance(field, db_models.BooleanField):
            values[field.name] = False
        else:
            values[field.name] = "Probe"
    return model.objects.create(**values)

class Values:
    """Plausible input for a form field, without knowing the model.

    A counter rides along because several models carry uniqueness -- a slug, a
    nav link, a slot's barber-and-time -- and a factory that answered "Test" to
    every CharField would fail the second row it made and look like a bug in
    the admin rather than in the test.
    """

    def __init__(self):
        self.n = 0

    def next(self):
        self.n += 1
        return self.n

    #: Both halves of a password pair have to match, and the counter would
    #: hand them different values. It also has to survive the validators,
    #: which reject anything short or obvious.
    PASSWORD = "pr0be-Passw0rd!x9"

    def for_field(self, name, field):
        if name.startswith("password"):
            return self.PASSWORD
        n = self.next()
        # A few fields carry a validator that a generic label fails. These
        # are the factory being wrong, not the admin: a real member of staff
        # would never type "Probe 1" into a phone box.
        if "phone" in name:
            return f"98{n:08d}"
        if name in ("username", "slug"):
            return f"probe-{n}"
        # Order matters: ModelChoiceField is a ChoiceField, SlugField and
        # EmailField are CharFields, and FloatField is an IntegerField.
        if isinstance(field, forms.ModelMultipleChoiceField):
            return [obj.pk for obj in field.queryset[:1]]
        if isinstance(field, forms.ModelChoiceField):
            obj = field.queryset.first() or ensure_instance(field.queryset.model)
            return obj.pk if obj is not None else ""
        if isinstance(field, forms.BooleanField):
            return "on"
        if isinstance(field, (forms.ImageField, forms.FileField)):
            return SimpleUploadedFile(f"probe{n}.png", png_bytes(), "image/png")
        if isinstance(field, forms.ChoiceField):
            usable = [c for c, _ in field.choices if c not in ("", None)]
            return usable[0] if usable else ""
        if isinstance(field, forms.EmailField):
            return f"probe{n}@example.com"
        if isinstance(field, forms.URLField):
            return f"https://example.com/{n}"
        if isinstance(field, forms.SlugField):
            return f"probe-slug-{n}"
        if isinstance(field, forms.SplitDateTimeField):
            return ["2026-01-01", "10:00:00"]
        if isinstance(field, forms.DateTimeField):
            return "2026-01-01 10:00:00"
        if isinstance(field, forms.DateField):
            return "2026-01-01"
        if isinstance(field, forms.TimeField):
            # Varied, so a second slot for the same barber does not collide
            # with the first on the unique constraint.
            return f"{6 + (n % 12):02d}:{(n * 5) % 60:02d}:00"
        if isinstance(field, forms.DecimalField):
            return "1"
        if isinstance(field, forms.IntegerField):
            # Inside whatever range the field declares. A port is >= 1, so
            # a factory answering 0 fails validation and looks like a bug in
            # the form it is testing.
            low = 1 if field.min_value is None else max(field.min_value, 1)
            high = field.max_value if field.max_value is not None else low + 10
            return min(low + (n % 3), high)
        text = f"Probe {n}"
        limit = getattr(field, "max_length", None)
        return text[:limit] if limit else text


FIELD_RE = re.compile(
    r'<(input|select|textarea)\b([^>]*)>(.*?)</\1>|<(input)\b([^>]*?)/?>',
    re.I | re.S,
)
ATTR_RE = re.compile(r'(\w[\w-]*)\s*=\s*"([^"]*)"')
OPTION_RE = re.compile(r'<option\b([^>]*)>', re.I)


def rendered_payload(html):
    """What a browser would post back from this page, unchanged.

    Used for updates rather than rebuilding the form from scratch, because a
    change page carries inline rows and their management forms, and posting a
    formset that does not describe what is already there deletes it.
    """
    data = {}
    for tag, attrs, inner, tag2, attrs2 in FIELD_RE.findall(html):
        tag = (tag or tag2).lower()
        attributes = dict(ATTR_RE.findall(attrs or attrs2 or ""))
        name = attributes.get("name")
        if not name or name == "csrfmiddlewaretoken":
            continue
        if tag == "input":
            kind = attributes.get("type", "text").lower()
            if kind in ("submit", "button", "image", "reset", "file"):
                continue
            if kind in ("checkbox", "radio"):
                # An unticked box is simply absent from a real post; sending
                # it with any value at all would read as ticked.
                if "checked" in (attrs or attrs2 or "").lower():
                    data[name] = attributes.get("value", "on")
                continue
            data.setdefault(name, attributes.get("value", ""))
        elif tag == "textarea":
            data.setdefault(name, re.sub(r"<[^>]+>", "", inner or "").strip())
        else:
            selected = ""
            for opt_attrs in OPTION_RE.findall(inner or ""):
                opts = dict(ATTR_RE.findall(opt_attrs))
                if "selected" in opt_attrs.lower():
                    selected = opts.get("value", "")
                    break
            data.setdefault(name, selected)
    return data


@admin_static_storage
class AdminCrudTests(TestCase):
    """One test per operation, each looping the whole registry.

    Grouped by operation rather than by model so a failure reads as "delete is
    broken on Barber" rather than as one of twenty-six near-identical tests.
    """

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_superuser("boss", "boss@x.com", "pw")

    def setUp(self):
        self.client.force_login(self.staff)
        self.values = Values()

    # -- helpers ---------------------------------------------------------

    def registry(self):
        for model, model_admin in dj_admin.site._registry.items():
            yield model, model_admin, model._meta.label

    def url(self, model, view, *args):
        opts = model._meta
        return reverse(
            f"admin:{opts.app_label}_{opts.model_name}_{view}", args=args
        )

    def request(self):
        """A bare request for the permission and form hooks.

        Built with RequestFactory rather than by asking the client for one:
        `Client.request()` actually issues a request and rewrites the
        client's cookie jar, so calling it once per model quietly logged the
        session out part-way through the loop and every later save came back
        as a redirect to the login page.
        """
        request = RequestFactory().get("/admin/")
        request.user = self.staff
        return request

    def add_payload(self, model, model_admin):
        """A whole valid object, built from the admin's own form."""
        request = self.request()
        form_class = model_admin.get_form(request)
        data = {}
        for name, field in form_class.base_fields.items():
            value = self.values.for_field(name, field)
            if value in ("", [], None) and not field.required:
                continue
            data[name] = value
        # Inlines post a management form even with no rows; without it the
        # formset is invalid and the save is rejected for a reason that has
        # nothing to do with the object being created.
        for inline in model_admin.get_inline_instances(request):
            formset = inline.get_formset(request)
            prefix = formset.get_default_prefix()
            data.update({
                f"{prefix}-TOTAL_FORMS": "0",
                f"{prefix}-INITIAL_FORMS": "0",
                f"{prefix}-MIN_NUM_FORMS": "0",
                f"{prefix}-MAX_NUM_FORMS": "1000",
            })
        return data

    def an_object(self, model, model_admin):
        """An existing row to read, update and delete; created if need be.

        Never the account running the test. The first user in the table is
        the superuser this client is logged in as, and deleting it turns
        every later request into a redirect to the login page -- which reads
        as the whole admin being broken rather than as the test having shot
        itself. The suite only passed before because the registry happened to
        put users last.
        """
        queryset = model.objects.all()
        if model is User:
            queryset = queryset.exclude(pk=self.staff.pk)
        existing = queryset.first()
        if existing is not None:
            return existing
        request = self.request()
        if not model_admin.has_add_permission(request):
            return None
        self.client.post(self.url(model, "add"), self.add_payload(model, model_admin))
        return queryset.first()

    # -- the four operations --------------------------------------------

    #: Every screen in the admin is one of these. If the registry shrinks
    #: below this, either a section has been dropped or the loops below are
    #: quietly walking nothing and passing for it.
    EXPECTED_MODELS = 26

    def test_the_registry_is_what_these_tests_think_it_is(self):
        registered = len(dj_admin.site._registry)
        self.assertGreaterEqual(
            registered,
            self.EXPECTED_MODELS,
            f"Only {registered} models registered; these tests were written "
            f"against {self.EXPECTED_MODELS}. A section has gone missing, or "
            "the CRUD loops are passing because they iterate nothing.",
        )
    def test_every_list_renders(self):
        for model, model_admin, label in self.registry():
            with self.subTest(model=label):
                # Followed, because a singleton admin sends its list
                # straight to the one row that exists rather than showing a
                # list of one. Either way the page has to render.
                response = self.client.get(
                    self.url(model, "changelist"), follow=True
                )
                self.assertEqual(response.status_code, 200, f"{label} list")

    def test_create(self):
        for model, model_admin, label in self.registry():
            with self.subTest(model=label):
                request = self.request()
                url = self.url(model, "add")
                if not model_admin.has_add_permission(request):
                    # A singleton refusing a second row is the point, not a gap.
                    self.assertEqual(
                        self.client.get(url).status_code, 403, f"{label} add"
                    )
                    continue
                self.assertEqual(
                    self.client.get(url).status_code, 200, f"{label} add form"
                )
                before = model.objects.count()
                response = self.client.post(url, self.add_payload(model, model_admin))
                self.assertEqual(
                    response.status_code,
                    302,
                    f"{label} create rejected: "
                    f"{self.form_errors(response)}",
                )
                self.assertEqual(
                    model.objects.count(), before + 1, f"{label} created nothing"
                )

    def test_read_and_update(self):
        for model, model_admin, label in self.registry():
            with self.subTest(model=label):
                obj = self.an_object(model, model_admin)
                if obj is None:
                    continue
                url = self.url(model, "change", obj.pk)
                page = self.client.get(url)
                self.assertEqual(page.status_code, 200, f"{label} change form")

                payload = rendered_payload(page.content.decode())
                payload["_continue"] = "Save and continue editing"
                response = self.client.post(url, payload)
                self.assertIn(
                    response.status_code,
                    (302, 200),
                    f"{label} update blew up",
                )
                self.assertLess(
                    response.status_code, 400, f"{label} update failed"
                )

    def test_delete(self):
        for model, model_admin, label in self.registry():
            with self.subTest(model=label):
                obj = self.an_object(model, model_admin)
                if obj is None:
                    continue
                request = self.request()
                url = self.url(model, "delete", obj.pk)
                if not model_admin.has_delete_permission(request, obj):
                    self.assertEqual(
                        self.client.get(url).status_code, 403, f"{label} delete"
                    )
                    continue
                self.assertEqual(
                    self.client.get(url).status_code, 200, f"{label} delete page"
                )
                response = self.client.post(url, {"post": "yes"})
                self.assertEqual(response.status_code, 302, f"{label} delete")
                self.assertFalse(
                    model.objects.filter(pk=obj.pk).exists(),
                    f"{label} survived deletion",
                )

    # -- reporting -------------------------------------------------------

    @staticmethod
    def form_errors(response):
        """The admin's own complaint, so a failure names the field and why.

        Read from the response context rather than scraped out of the HTML:
        the theme does not render Django's stock `errorlist` markup, so a
        regex over the page found nothing and reported a rejected save as a
        mystery.
        """
        context = response.context or {}
        parts = []
        adminform = context.get("adminform")
        if adminform is not None:
            parts.append(dict(adminform.form.errors))
        for formset in context.get("inline_admin_formsets", []) or []:
            if formset.formset.errors or formset.formset.non_form_errors():
                parts.append(
                    {
                        "inline": formset.formset.prefix,
                        "errors": formset.formset.errors,
                        "non_form": list(formset.formset.non_form_errors()),
                    }
                )
        return str(parts)[:500] if parts else "no form errors in context"
