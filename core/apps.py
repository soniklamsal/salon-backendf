from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    # Sidebar order comes from JAZZMIN_SETTINGS["order_with_respect_to"], so
    # these names stay plain rather than carrying numeric prefixes.
    verbose_name = "Site"

    def ready(self):
        # The stock front page is Jazzmin's app list -- the sidebar again in a
        # second shape. Pointing `index_template` at our own file swaps it for
        # something that says what is waiting, and does so in one line: a
        # custom AdminSite subclass would mean replacing
        # django.contrib.admin in INSTALLED_APPS, which the ordering comment
        # in settings.py exists to protect.
        #
        # Set here rather than by adding "admin/index.html" to templates/,
        # because our template extends that name and cannot extend itself.
        from django.contrib import admin

        admin.site.index_template = "admin/salon_dashboard.html"
