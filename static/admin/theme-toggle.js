/*
 * Light/dark switch for the admin.
 *
 * Jazzmin already owns the mechanism: an inline script in the <head> reads
 * `jazzmin-theme-mode` from localStorage (falling back to
 * `default_theme_mode` in config/jazzmin.py, which is "auto"), resolves
 * "auto" against the OS, and stamps the result on <html> as
 * `data-bs-theme`. What it does not give you is a way to change it —
 * Jazzmin's own control lives behind `show_theme_chooser`, which also
 * exposes a Bootswatch theme picker that would swap the base stylesheet
 * out from under static/admin/salon-admin.css.
 *
 * So this adds only the missing half: one button in the navbar that flips
 * the same attribute and writes the same key. Nothing here is a private
 * arrangement — a mode set from Jazzmin's chooser, or from another tab,
 * is understood by this button and vice versa.
 *
 * The button carries both icons and CSS decides which one shows, keyed off
 * `data-bs-theme` on <html>. That is deliberate: the icon then cannot drift
 * out of step with the theme, however the theme came to be set.
 */
(function () {
  "use strict";

  var STORAGE_KEY = "jazzmin-theme-mode";
  var root = document.documentElement;

  function current() {
    return root.getAttribute("data-bs-theme") === "dark" ? "dark" : "light";
  }

  function apply(mode) {
    root.setAttribute("data-bs-theme", mode);
    try {
      localStorage.setItem(STORAGE_KEY, mode);
    } catch (e) {
      /* Private mode, or storage disabled: the switch still works for this
         page view, it just will not be remembered. Not worth failing over. */
    }
    label(mode);
  }

  function label(mode) {
    var button = document.querySelector(".salon-theme-toggle");
    if (!button) return;
    var next = mode === "dark" ? "light" : "dark";
    var text = "Switch to " + next + " mode";
    button.setAttribute("title", text);
    button.setAttribute("aria-label", text);
  }

  function build() {
    // The right-hand cluster of the navbar, where the user and docs icons
    // already sit. Without it there is nowhere sensible to put this.
    var cluster = document.querySelector(".app-header .navbar-nav.ms-auto");
    if (!cluster || document.querySelector(".salon-theme-toggle")) return;

    var item = document.createElement("li");
    item.className = "nav-item";

    var button = document.createElement("a");
    button.className = "nav-link btn salon-theme-toggle";
    button.href = "#";
    button.setAttribute("role", "button");
    button.innerHTML =
      '<i class="fas fa-sun salon-theme-icon-dark" aria-hidden="true"></i>' +
      '<i class="fas fa-moon salon-theme-icon-light" aria-hidden="true"></i>';

    button.addEventListener("click", function (event) {
      event.preventDefault();
      apply(current() === "dark" ? "light" : "dark");
    });

    item.appendChild(button);
    /*
     * Directly to the left of the profile menu, which the template renders
     * last in this cluster. Anchored to `lastElementChild` rather than to a
     * fixed index so it stays put if the admindocs or language items — both
     * conditional in the template — appear alongside it.
     */
    cluster.insertBefore(item, cluster.lastElementChild);
    label(current());
  }

  /* Following the OS means following it for as long as it is being
     followed — if the preference is still "auto", a system change while
     the page is open should move the page too. Once an explicit choice is
     stored, this stops applying. */
  function watchSystem() {
    if (!window.matchMedia) return;
    var query = window.matchMedia("(prefers-color-scheme: dark)");
    var handler = function (event) {
      var stored;
      try {
        stored = localStorage.getItem(STORAGE_KEY);
      } catch (e) {
        stored = null;
      }
      if (stored && stored !== "auto") return;
      root.setAttribute("data-bs-theme", event.matches ? "dark" : "light");
      label(current());
    };
    if (query.addEventListener) {
      query.addEventListener("change", handler);
    } else if (query.addListener) {
      query.addListener(handler); // Safari < 14
    }
  }

  function init() {
    build();
    watchSystem();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
