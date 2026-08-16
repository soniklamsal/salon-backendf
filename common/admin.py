"""Admin bases shared by the content apps."""

import re

from django import forms
from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from common.utils import resolve_image


class SingletonAdmin(admin.ModelAdmin):
    """Admin for a section that exists once.

    Clicking the model in the sidebar lands directly on its edit form rather
    than on a one-row changelist, and neither "Add another" nor "Delete" is
    offered. That is the whole difference between "a section of the page" and
    "a list of things".
    """

    save_on_top = True

    def has_add_permission(self, request):
        return not self.model.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj, _created = self.model.objects.get_or_create(pk=1)
        url = reverse(
            f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_change",
            args=[obj.pk],
        )
        return HttpResponseRedirect(url)

    def response_post_save_change(self, request, obj):
        # The changelist redirects back here, so "Save" would bounce the user
        # into the form again. Send them to the dashboard instead.
        if "_continue" not in request.POST and "_saveasnew" not in request.POST:
            return HttpResponseRedirect(reverse("admin:index"))
        return super().response_post_save_change(request, obj)


_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class ImagePreviewMixin:
    """Adds a `preview` readonly field rendering whichever image resolves.

    Set `preview_fields = [("image", "image_url"), ...]` to preview more than
    the default pair.
    """

    preview_fields = [("image", "image_url")]

    @admin.display(description="Preview")
    def preview(self, obj):
        if obj is None or obj.pk is None:
            return mark_safe('<span class="salon-preview--empty">Save first</span>')

        chunks = []
        for file_attr, url_attr in self.preview_fields:
            url = resolve_image(obj, file_attr, url_attr)
            if not url:
                continue
            chunks.append(
                format_html('<div class="salon-preview"><img src="{}" alt=""></div>', url)
            )

        if not chunks:
            return mark_safe('<span class="salon-preview--empty">No image set</span>')
        return mark_safe("".join(chunks))


class ColorInput(forms.TextInput):
    """A hex text field with a native colour picker beside it.

    Both, not one or the other. The picker is what people reach for, but the
    model column accepts any CSS colour and `<input type="color">` can only
    represent 7-character hex — so the text field stays authoritative and the
    picker is a convenience bolted onto it. `static/admin/color-widget.js`
    keeps them in step.
    """

    class Media:
        js = ("admin/color-widget.js",)

    def render(self, name, value, attrs=None, renderer=None):
        text = super().render(name, value, attrs, renderer)
        swatch = value if isinstance(value, str) and _HEX.match(value or "") else "#000000"
        return format_html(
            '<span class="salon-color" style="display:inline-flex;gap:8px;align-items:center">'
            '<input type="color" value="{}" aria-label="Colour picker" '
            'style="width:42px;height:32px;padding:0;border:1px solid #bbb;'
            'border-radius:4px;background:none;cursor:pointer">{}</span>',
            swatch,
            mark_safe(text),
        )
