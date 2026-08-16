from django.contrib import admin

from common.admin import SingletonAdmin
from core.models import NavLink, SiteSettings, SocialLink


@admin.register(SiteSettings)
class SiteSettingsAdmin(SingletonAdmin):
    fieldsets = (
        ("Brand", {"fields": ("brand_name", "badge_caption")}),
        ("Search & sharing", {"fields": ("meta_title", "meta_description")}),
        ("Header call to action", {"fields": ("nav_cta_label", "nav_cta_href")}),
        ("Footer", {"fields": ("copyright_text",)}),
    )


@admin.register(NavLink)
class NavLinkAdmin(admin.ModelAdmin):
    list_display = ("label", "href", "show_in_header", "show_in_footer", "order", "is_published")
    list_editable = ("href", "show_in_header", "show_in_footer", "order", "is_published")
    list_filter = ("show_in_header", "show_in_footer", "is_published")
    search_fields = ("label", "href")
    ordering = ("order", "pk")


@admin.register(SocialLink)
class SocialLinkAdmin(admin.ModelAdmin):
    list_display = ("platform", "url", "order", "is_published")
    list_editable = ("url", "order", "is_published")
    list_filter = ("platform", "is_published")
    ordering = ("order", "pk")
