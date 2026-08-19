/*
 * The admin, answering in place instead of reloading.
 *
 * Three interactions, one mechanism: post JSON to an endpoint the page told us
 * about, put the HTML that comes back where it belongs, and say what happened
 * in the same alert box Django would have used. Sending a test email stops
 * freezing the page for ten seconds; approving a booking stops costing a
 * checkbox, a dropdown and a re-rendered changelist; publishing something stops
 * re-POSTing every row on the page to flip one box.
 *
 * Bootstrap and AdminLTE are already loaded by the time this runs, and the
 * alert markup below is copied from Jazzmin's own base.html — which means
 * dismissal works with no code here at all, because Bootstrap's alert handler
 * is delegated at the document. The only reason to build the markup rather
 * than reuse a component is that Django rendered its own alerts server-side
 * and these have to be indistinguishable from those.
 *
 * No domain markup is built here. A status pill, a visit time, a boolean tick
 * and the row buttons are all rendered by Python and arrive as HTML, because
 * those rules already exist in bookings/admin.py and a second copy in
 * JavaScript would drift the first time someone edited the first one — and
 * nothing tests this file.
 *
 * Plain DOM on purpose: the admin loads no framework of ours, and jQuery is
 * only guaranteed inside django.jQuery. The one at the bottom of the page is a
 * second, separate instance, so a handler bound through one is invisible to
 * the other; a native event with `bubbles: true` is seen by both.
 */
(function () {
  "use strict";

  var CONFIG_ID = "salon-ajax-config";
  var BUSY_CLASS = "salon-busy";

  /* Twice EMAIL_TIMEOUT, which is 10 seconds. Long enough for a slow Gmail,
     short enough that a dead connection does not spin forever. */
  var SEND_TIMEOUT_MS = 20000;

  var cachedConfig = null;

  function config() {
    if (cachedConfig) return cachedConfig;
    cachedConfig = { csrfToken: "", endpoints: {} };
    var block = document.getElementById(CONFIG_ID);
    if (block) {
      try {
        cachedConfig = JSON.parse(block.textContent);
      } catch (e) {
        /* A malformed config leaves every feature switched off, which is the
           same place we start from. Nothing to recover, nothing to report. */
      }
    }
    return cachedConfig;
  }

  function token() {
    var fromConfig = config().csrfToken;
    if (fromConfig) return fromConfig;
    // The dashboard has no form to read one from, which is why the config
    // block carries it; this is only a fallback for pages that do.
    var input = document.querySelector("[name=csrfmiddlewaretoken]");
    return input ? input.value : "";
  }

  function failure(reason, message) {
    return { reason: reason, message: message };
  }

  function signedOut() {
    return failure(
      "signed_out",
      "Your sign-in has expired. Nothing was saved."
    );
  }

  /*
   * Post JSON and get JSON back, or a `failure` describing why not.
   *
   * The awkward part is the signed-out case. An expired session is answered
   * with a redirect to the login page, fetch follows it, and what arrives is a
   * perfectly valid 200 holding an HTML form. Calling .json() on that throws a
   * SyntaxError that reads like a bug in this file, so the redirect is caught
   * before parsing rather than after. The server also answers 401 JSON for the
   * same case; this is the second layer, and catches a redirect introduced by
   * anything else — a proxy, a future middleware.
   */
  function post(url, body, timeoutMs) {
    var controller = window.AbortController ? new AbortController() : null;
    var timer = null;
    if (controller && timeoutMs) {
      timer = window.setTimeout(function () {
        controller.abort();
      }, timeoutMs);
    }

    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": token()
      },
      body: JSON.stringify(body),
      signal: controller ? controller.signal : undefined
    })
      .then(function (response) {
        if (response.redirected) throw signedOut();
        var type = response.headers.get("Content-Type") || "";
        if (type.indexOf("application/json") !== 0) throw signedOut();
        return response.json().then(function (data) {
          if (!data || !data.ok) {
            throw failure(
              (data && data.reason) || "server",
              (data && data.error) || "Something went wrong."
            );
          }
          return data;
        });
      })
      .catch(function (error) {
        if (error && error.reason) throw error;
        if (error && error.name === "AbortError") {
          throw failure("timeout", "That took too long. Nothing was saved.");
        }
        throw failure(
          "network",
          "Could not reach the server. Nothing was saved."
        );
      })
      .then(function (data) {
        if (timer) window.clearTimeout(timer);
        return data;
      })
      .catch(function (error) {
        if (timer) window.clearTimeout(timer);
        throw error;
      });
  }

  /* --- saying what happened ---------------------------------------------- */

  var ICONS = {
    success: "fa-check",
    danger: "fa-ban",
    error: "fa-ban",
    warning: "fa-exclamation-triangle",
    info: "fa-info"
  };

  function alertHost() {
    return document.querySelector(".app-content .container-fluid");
  }

  function capitalise(text) {
    // Django's message template applies |capfirst; these have to match.
    if (!text) return "";
    return text.charAt(0).toUpperCase() + text.slice(1);
  }

  /*
   * Django's alert markup, rebuilt. Copied from jazzmin/templates/admin/
   * base.html so an alert raised here is indistinguishable from one the server
   * rendered — same classes, same icon, same dismiss button.
   */
  function notify(level, text, permanent) {
    var host = alertHost();
    if (!host || !text) return;

    var css = level === "error" ? "danger" : level;
    var previous = host.querySelector(".salon-alert");
    // A jammed button should not stack ten identical alerts.
    if (previous && previous.getAttribute("data-salon-text") === text) return;

    var box = document.createElement("div");
    box.className =
      "alert alert-" + css + " salon-alert fade show" +
      (permanent ? "" : " alert-dismissible");
    box.setAttribute("role", "alert");
    box.setAttribute("data-salon-text", text);

    var icon = document.createElement("i");
    icon.className = "icon fa " + (ICONS[css] || ICONS.info);
    box.appendChild(icon);
    box.appendChild(document.createTextNode(" " + capitalise(text)));

    if (!permanent) {
      var close = document.createElement("button");
      close.type = "button";
      close.className = "btn-close";
      close.setAttribute("data-bs-dismiss", "alert");
      close.setAttribute("aria-label", "Close");
      box.appendChild(close);
    }

    host.insertBefore(box, host.firstChild);
    return box;
  }

  function report(error) {
    if (error.reason === "signed_out") {
      // Deliberately not a redirect. On a change form that would throw away
      // everything typed; the person can open the link in a new tab, sign in,
      // and come back to a page that is still intact.
      var box = notify("warning", error.message, true);
      if (!box) return;
      var link = document.createElement("a");
      link.href = "/admin/login/?next=" + encodeURIComponent(window.location.pathname);
      link.textContent = "Sign in again";
      box.appendChild(document.createTextNode(" "));
      box.appendChild(link);
      return;
    }
    notify("danger", error.message);
  }

  function announce(data) {
    var messages = (data && data.messages) || [];
    for (var i = 0; i < messages.length; i++) {
      notify(messages[i].level, messages[i].text);
    }
  }

  /* --- busy states -------------------------------------------------------- */

  function busy(element, on) {
    if (!element) return;
    element.disabled = !!on;
    if (on) {
      element.setAttribute("aria-busy", "true");
      element.classList.add(BUSY_CLASS);
    } else {
      element.removeAttribute("aria-busy");
      element.classList.remove(BUSY_CLASS);
    }
  }

  /* --- rows --------------------------------------------------------------- */

  function rowFor(element) {
    var node = element;
    while (node && node.tagName !== "TR") node = node.parentNode;
    return node;
  }

  /*
   * The row's primary key. Two sources, because neither is always there: the
   * action checkbox is absent when a ModelAdmin has no actions, and the object
   * link is absent when list_display_links is empty. Where we render the markup
   * ourselves we stamp data-salon-pk and that wins.
   */
  function pkFor(row, element) {
    var stamped = element && element.closest ? element.closest("[data-salon-pk]") : null;
    if (stamped) return stamped.getAttribute("data-salon-pk");
    if (!row) return null;

    var checkbox = row.querySelector("input.action-select");
    if (checkbox && checkbox.value) return checkbox.value;

    var link = row.querySelector("th a[href], td a[href]");
    if (link) {
      var match = link.getAttribute("href").match(/(\d+)\/change\//);
      if (match) return match[1];
    }
    return null;
  }

  function swapCells(row, cells) {
    if (!row || !cells) return;
    for (var name in cells) {
      if (!Object.prototype.hasOwnProperty.call(cells, name)) continue;
      var cell = row.querySelector(".field-" + name);
      if (!cell) continue;
      cell.innerHTML = cells[name];
      // Row buttons arrive disabled — that is how they render for someone with
      // no JavaScript — so re-enable the ones we just put back.
      var buttons = cell.querySelectorAll("[data-salon-action]");
      for (var i = 0; i < buttons.length; i++) buttons[i].disabled = false;
    }
  }

  /* --- 1. the SMTP screen's test button ----------------------------------- */

  function initSendTest() {
    var form = document.getElementById("salon-send-test");
    if (!form) return;
    var url = form.getAttribute("data-salon-json");
    if (!url) return;

    var button = document.querySelector('input[form="salon-send-test"]');

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var label = button ? button.value : "";
      if (button) button.value = "Sending…";
      busy(button, true);

      post(url, {}, SEND_TIMEOUT_MS)
        .then(function (data) {
          announce(data);
          var panels = data.panels || {};
          for (var name in panels) {
            if (!Object.prototype.hasOwnProperty.call(panels, name)) continue;
            var target = document.querySelector('[data-salon-panel="' + name + '"]');
            if (target) target.innerHTML = panels[name];
          }
        })
        .catch(report)
        .then(function () {
          if (button) button.value = label;
          busy(button, false);
        });
    });
  }

  /* --- 2. per-row actions -------------------------------------------------- */

  function initRowActions() {
    var url = config().endpoints.action;
    var buttons = document.querySelectorAll("[data-salon-action]");
    if (!url || !buttons.length) return;

    for (var i = 0; i < buttons.length; i++) buttons[i].disabled = false;

    document.addEventListener("click", function (event) {
      var button = event.target.closest
        ? event.target.closest("[data-salon-action]")
        : null;
      if (!button || button.disabled) return;

      event.preventDefault();
      var row = rowFor(button);
      var pk = pkFor(row, button);
      if (!pk) return;

      busy(button, true);
      post(url, {
        action: button.getAttribute("data-salon-action"),
        pk: pk,
        with_stats: !!document.querySelector("[data-salon-stats]")
      })
        .then(function (data) {
          announce(data);
          swapCells(row, data.cells);
          refreshStats(data.stats);
        })
        .catch(function (error) {
          busy(button, false);
          report(error);
        });
    });
  }

  /* --- 3. instant toggles -------------------------------------------------- */

  function columnName(cell) {
    var match = (cell.className || "").match(/field-([\w]+)/);
    return match ? match[1] : null;
  }

  function initToggles() {
    var url = config().endpoints.toggle;
    var allowed = config().endpoints.toggleFields || [];
    if (!url || !allowed.length) return;

    var boxes = document.querySelectorAll(
      '#result_list td input[type="checkbox"]'
    );

    for (var i = 0; i < boxes.length; i++) {
      var box = boxes[i];
      var cell = box.parentNode;
      while (cell && cell.tagName !== "TD") cell = cell.parentNode;
      if (!cell) continue;

      var name = columnName(cell);
      if (!name || allowed.indexOf(name) === -1) continue;

      cell.classList.add("salon-switch");
      box.setAttribute("data-salon-toggle", name);
    }

    document.addEventListener("change", function (event) {
      var box = event.target;
      if (!box || !box.getAttribute) return;
      var field = box.getAttribute("data-salon-toggle");
      if (!field) return;

      var row = rowFor(box);
      var pk = pkFor(row, box);
      if (!pk) return;

      var wanted = box.checked;
      var cell = box.parentNode;
      while (cell && cell.tagName !== "TD") cell = cell.parentNode;

      busy(box, true);
      // The desired value, not "flip". If this row is stale, "turn it off"
      // still lands on off; flipping it would turn it back on.
      post(url, { pk: pk, field: field, value: wanted })
        .then(function (data) {
          swapCells(row, data.cells);
          if (cell) {
            // No alert: a switch settling into place is the feedback, and one
            // alert per checkbox would bury the page.
            cell.classList.add("salon-switch--saved");
            window.setTimeout(function () {
              cell.classList.remove("salon-switch--saved");
            }, 600);
          }
        })
        .catch(function (error) {
          // Never leave the box showing a state the database does not have.
          box.checked = !wanted;
          report(error);
        })
        .then(function () {
          busy(box, false);
        });
    });
  }

  /* --- 4. the dashboard's counters ---------------------------------------- */

  function refreshStats(stats) {
    if (!stats) return;
    for (var key in stats) {
      if (!Object.prototype.hasOwnProperty.call(stats, key)) continue;
      var target = document.querySelector('[data-salon-stat="' + key + '"]');
      if (target) target.textContent = stats[key];
    }
  }

  function init() {
    initSendTest();
    initRowActions();
    initToggles();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
