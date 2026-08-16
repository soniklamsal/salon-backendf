"""Serializer plumbing shared by the API.

Two things live here. `CamelCaseMixin` rekeys output so the payload reads
natively in the TypeScript that consumes it — the frontend is the only client,
so there is no reason to make it translate. `ImageURLField` collapses the
upload/URL pair every image on the site carries into the single string a
`<Image src>` wants.
"""

from rest_framework import serializers

from common.utils import resolve_image


def to_camel_case(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(word[:1].upper() + word[1:] for word in rest)


class CamelCaseMixin:
    """Rekeys `to_representation` output to camelCase.

    Applied per-serializer, so nested serializers convert their own keys and
    nesting needs no special handling.
    """

    def to_representation(self, instance):
        data = super().to_representation(instance)
        return {to_camel_case(key): value for key, value in data.items()}


class ImageURLField(serializers.Field):
    """Emits one URL for a model's (ImageField, url CharField) pair.

    `source="*"` hands the whole instance to the field, so the output key is
    this field's name on the serializer rather than any single model field.
    """

    def __init__(self, file_field="image", url_field="image_url", **kwargs):
        self.file_field = file_field
        self.url_field = url_field
        kwargs.setdefault("source", "*")
        kwargs["read_only"] = True
        super().__init__(**kwargs)

    def to_representation(self, instance):
        return resolve_image(
            instance,
            self.file_field,
            self.url_field,
            request=self.context.get("request"),
        )


class LinkField(serializers.Serializer):
    """A {label, href} pair assembled from two flat model fields.

    Buttons appear all over the page and the frontend treats them as one thing,
    so the API hands over one object instead of two parallel strings.
    """

    def __init__(self, label_field, href_field, **kwargs):
        self.label_field = label_field
        self.href_field = href_field
        kwargs.setdefault("source", "*")
        kwargs["read_only"] = True
        super().__init__(**kwargs)

    def to_representation(self, instance):
        return {
            "label": getattr(instance, self.label_field, "") or "",
            "href": getattr(instance, self.href_field, "") or "",
        }


class CamelCaseModelSerializer(CamelCaseMixin, serializers.ModelSerializer):
    pass


class CamelCaseSerializer(CamelCaseMixin, serializers.Serializer):
    pass
