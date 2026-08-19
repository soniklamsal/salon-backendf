/*
 * Keeps the navbar preview on Site settings showing the logo that is actually
 * selected, including one that has been chosen but not yet saved.
 *
 * Without this the preview would show the stored logo — or the wordmark — right
 * up until save, which is exactly the wrong moment to find out a mark is
 * illegible at the header's size. The browser can read the chosen file locally,
 * so the answer arrives while there is still time to pick a different one.
 *
 * The logo's size is not adjustable and is not touched here: the header draws
 * it at a fixed height, and the preview is rendered with those same numbers
 * server-side (see `core.admin.LOGO_HEIGHT_PX`).
 *
 * Plain DOM on purpose: the admin loads no framework, and jQuery is only
 * guaranteed inside django.jQuery.
 */
(function () {
  "use strict";

  function init() {
    var root = document.querySelector("[data-navbar-preview]");
    var field = document.getElementById("id_logo");
    if (!root || !field) return;

    var img = root.querySelector(".salon-navbar__logo");
    var text = root.querySelector(".salon-navbar__wordmark");
    if (!img || !text) return;

    function show(hasLogo) {
      img.style.display = hasLogo ? "" : "none";
      text.style.display = hasLogo ? "none" : "";
    }

    field.addEventListener("change", function () {
      var file = field.files && field.files[0];
      if (file) {
        var reader = new FileReader();
        reader.onload = function (event) {
          img.src = event.target.result;
          show(true);
        };
        reader.readAsDataURL(file);
        return;
      }
      // Nothing selected: fall back to whatever is already stored.
      var stored = root.getAttribute("data-logo");
      img.src = stored || "";
      show(Boolean(stored));
    });

    // Django renders a "Clear" checkbox beside an existing upload.
    var clear = document.getElementById("logo-clear_id");
    if (clear) {
      clear.addEventListener("change", function () {
        show(!clear.checked && Boolean(root.getAttribute("data-logo")));
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
