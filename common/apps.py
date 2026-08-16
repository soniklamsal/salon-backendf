from django.apps import AppConfig


class CommonConfig(AppConfig):
    """Hosts the shared base models, and connects the cache invalidation.

    `common` carries only abstract models, so being an installed app adds no
    tables and no migrations. It is listed for `ready()` alone: the signals
    below have to be imported once, after the app registry is populated, and
    importing them from a module that merely happens to load is how receivers
    end up silently unregistered.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "common"
    verbose_name = "Shared"

    def ready(self):
        # Imported for the @receiver side effects, not for a name.
        from common import signals  # noqa: F401
