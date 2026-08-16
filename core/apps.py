from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    # Sidebar order comes from JAZZMIN_SETTINGS["order_with_respect_to"], so
    # these names stay plain rather than carrying numeric prefixes.
    verbose_name = "Site"
