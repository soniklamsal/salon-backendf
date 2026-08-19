"""
Jazzmin configuration.

The point of the ordering below is that the admin sidebar reads in the same
order as the landing page: Hero, Service Menu, Motivation, Classes, Our Story,
As Seen On, Follow Us, Footer. Someone editing the site can walk the menu
top-to-bottom and see the page assemble in the same sequence.

The other pages follow after the footer, one page at a time: About Us today.

Icon names are Font Awesome 5 Free, which is what Jazzmin bundles.
"""

JAZZMIN_SETTINGS = {
    "site_title": "Salon Admin",
    "site_header": "Salon",
    "site_brand": "SALON",
    "site_logo": None,
    "login_logo": None,
    "site_icon": None,
    "welcome_sign": "Sign in to edit the site",
    "copyright": "Salon",
    # Global search box targets the models most likely to be looked up by name.
    "search_model": ["sections.Service", "sections.ClassCard", "bookings.Appointment"],
    "user_avatar": None,
    "topmenu_links": [
        {"name": "Home", "url": "admin:index", "permissions": ["auth.view_user"]},
        {"name": "View site", "url": "http://localhost:3000", "new_window": True},
        {"name": "API", "url": "/api/v1/", "new_window": True},
    ],
    "usermenu_links": [
        {"name": "Homepage payload", "url": "/api/v1/homepage/", "new_window": True},
    ],
    "show_sidebar": True,
    "navigation_expanded": True,
    "hide_apps": [],
    # The real model stays registered so Appointment's autocomplete can
    # resolve it; only its duplicate sidebar entry is hidden. The list is
    # reached through Enquiries -> Services (a proxy) instead.
    "hide_models": ["sections.Service"],
    "order_with_respect_to": [
        "core",
        "core.SiteSettings",
        "core.EmailSettings",
        "core.NavLink",
        "core.SocialLink",
        "sections",
        "sections.HeroSection",
        "sections.WhoWeAreSection",
        "sections.MotivationSection",
        "sections.GallerySection",
        "sections.ClassesSection",
        "sections.ClassCard",
        "sections.OurStorySection",
        "sections.AsSeenOnSection",
        "sections.FollowUsSection",
        "sections.FooterSection",
        "sections.AboutSection",
        "sections.AboutColumn",
        "sections.AboutColumnItem",
        "bookings",
        "bookings.Appointment",
        "bookings.ContactMessage",
        "bookings.Service",
        "auth",
    ],
    "icons": {
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "auth.Group": "fas fa-users",
        "core.SiteSettings": "fas fa-sliders-h",
        "core.EmailSettings": "fas fa-paper-plane",
        "core.NavLink": "fas fa-bars",
        "core.SocialLink": "fas fa-share-alt",
        "sections.HeroSection": "fas fa-star",
        "sections.ServiceMenuSection": "fas fa-concierge-bell",
        "sections.Service": "fas fa-cut",
        "sections.MotivationSection": "fas fa-quote-left",
        "sections.GallerySection": "fas fa-images",
        "sections.ClassesSection": "fas fa-chalkboard-teacher",
        "sections.ClassCard": "fas fa-th-large",
        "sections.OurStorySection": "fas fa-book-open",
        "sections.AsSeenOnSection": "fas fa-newspaper",
        "sections.FollowUsSection": "fas fa-heart",
        "sections.FooterSection": "fas fa-shoe-prints",
        "sections.AboutSection": "fas fa-address-book",
        "sections.AboutColumn": "fas fa-columns",
        "sections.AboutColumnItem": "fas fa-list-ul",
        "bookings.Appointment": "fas fa-calendar-check",
        "bookings.ContactMessage": "fas fa-envelope",
    },
    "default_icon_parents": "fas fa-chevron-circle-right",
    "default_icon_children": "fas fa-circle",
    "related_modal_active": True,
    "custom_css": "admin/salon-admin.css",
    # Adds the light/dark switch to the navbar. Jazzmin's own control is
    # `show_theme_chooser`, which is left off: it also exposes a Bootswatch
    # picker that would swap the base stylesheet the skin is painted on.
    "custom_js": "admin/theme-toggle.js",
    "use_google_fonts_cdn": True,
    "show_ui_builder": False,
    # Singletons are edited on one long form; the tabbed layout that Jazzmin
    # applies by default would hide fieldsets behind clicks for no gain.
    "changeform_format": "horizontal_tabs",
    "changeform_format_overrides": {
        "core.SiteSettings": "collapsible",
        "sections.HeroSection": "collapsible",
        "auth.user": "collapsible",
        "auth.group": "vertical_tabs",
    },
    "language_chooser": False,
}

JAZZMIN_UI_TWEAKS = {
    "navbar_small_text": False,
    "footer_small_text": False,
    "body_small_text": False,
    "brand_small_text": False,
    "brand_colour": "navbar-dark",
    "accent": "accent-lime",
    "navbar": "navbar-dark",
    "no_navbar_border": False,
    "navbar_fixed": True,
    "layout_boxed": False,
    "footer_fixed": False,
    "sidebar_fixed": True,
    "sidebar": "sidebar-dark-lime",
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": True,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": False,
    # "default" is plain Bootstrap 5 as bundled in adminlte.min.css, which
    # defines a complete light AND dark set behind `data-bs-theme`. The
    # Bootswatch themes mostly do not — `darkly`, the closest match to the
    # site by colour, is dark-only, and asking it for a light mode leaves
    # hard-coded dark surfaces stranded on a white page. The skin supplies
    # the salon's palette either way, so the neutral base is the one that
    # can actually be both.
    "theme": "default",
    # Jazzmin 3 dropped `dark_mode_theme`: every theme now renders light or dark
    # via `data-bs-theme`, and this picks the starting point. "auto" follows the
    # OS; the navbar switch (admin/theme-toggle.js) overrides it per browser.
    "default_theme_mode": "auto",
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success",
    },
}
