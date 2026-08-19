/*
 * The notification bell in the admin navbar.
 *
 * A booking or an enquiry already sends an email and already moves a number
 * on the dashboard. Both are missed the same way: the inbox is in another
 * tab, and the dashboard number only changes when the page is reloaded. This
 * tells somebody who is *already in the admin*, on whatever screen they
 * happen to be on, that something just came in — and makes a sound, because
 * a silent badge in a background tab is the thing that was already there.
 *
 * Polling, not push. Django here is WSGI with no channel layer, so a socket
 * would mean adding Channels, Redis and a second process to the deploy for a
 * salon that takes a handful of bookings a day. One small POST every 25
 * seconds costs less than any of that. See POLL_MS.
 *
 * The sound is synthesised rather than shipped as a file: two short notes
 * through the Web Audio API, no asset to serve, no format to pick between
 * browsers, and nothing to go missing behind a static-files misconfiguration.
 *
 * Plain DOM and no framework, matching static/admin/salon-ajax.js. Read that
 * file's header first — the config block, the CSRF token and the signed-out
 * response shape are all shared with it.
 */
(function () {
  "use strict";

  var CONFIG_ID = "salon-ajax-config";

  /* Long enough that ten open tabs are not a load problem, short enough that
     "somebody just booked" still feels like news. The bell also polls the
     moment a hidden tab is looked at again, which is what actually covers the
     case of coming back to the admin after an hour. */
  var POLL_MS = 25000;

  /* Where the highest notification id we have already seen is remembered.
     sessionStorage, not a variable: every click in the admin is a full page
     load, and a variable would re-baseline on each one — meaning either a
     chime on every navigation, or (if we baselined silently) no chime for
     anything that arrived during one. */
  var SEEN_KEY = "salon-notify-last-id";

  /* Whether the chime is wanted at all. localStorage, not sessionStorage: a
     preference about noise should outlive the tab it was set in. */
  var SOUND_KEY = "salon-notify-sound";

  var state = {
    items: [],
    unread: 0,
    open: false,
    loading: false,
  };

  var audio = null;

  /* A chime that was owed but could not be played, because the browser had
     not yet been given a gesture to authorise audio in this document.

     This flag is the whole reason the sound is reliable. Without it, a
     notification arriving before the first click is silent *and* its id is
     still recorded as seen — so it never chimes, not then and not later. With
     it, the sound simply waits for the next click anywhere on the page. */
  var pendingChime = false;

  // --- config ------------------------------------------------------------

  function config() {
    var block = document.getElementById(CONFIG_ID);
    if (!block) return null;
    try {
      return JSON.parse(block.textContent);
    } catch (e) {
      return null;
    }
  }

  var settings = config();
  var endpoints = (settings && settings.notifications) || null;
  var csrfToken = (settings && settings.csrfToken) || "";

  function post(url, body, keepalive) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      /* keepalive lets a request outlive the page that started it. Clicking
         an entry marks it read and navigates in the same gesture, and without
         this the browser cancels the POST as it tears the page down — the
         count would come back wrong on the very next screen. */
      keepalive: !!keepalive,
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(body || {}),
    }).then(function (response) {
      /* 401 is a session that has expired while the tab sat open. There is
         nothing useful to say about it from a bell — the next thing the
         person clicks will send them to the login page anyway — so the poll
         goes quiet rather than throwing a banner over their work. */
      if (response.status === 401) return null;
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    });
  }

  // --- the sound ---------------------------------------------------------

  /*
   * Audio and the autoplay rule.
   *
   * A browser will not let a page make a sound until that page has been
   * interacted with — and every navigation in the admin is a fresh document,
   * so "has been interacted with" resets on every screen. There is no way
   * around that and no reason to want one; it is the rule that stops pages
   * making noise at people unprompted.
   *
   * What there *is* a way around is losing the chime to it. Three things
   * together make the sound reliable:
   *
   *   1. The context is built eagerly, at load. It comes up suspended, which
   *      costs nothing, and means `chime()` always has something to resume
   *      rather than nothing to play.
   *   2. Gesture listeners stay attached until the context actually reaches
   *      "running". A single `{once: true}` listener spends itself on the
   *      first gesture, and if resume() has not completed by then there is
   *      no second attempt.
   *   3. A chime that could not be played is remembered, not dropped. It
   *      sounds the moment audio is authorised.
   */
  function ensureContext() {
    if (audio) return audio;
    var Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return null;
    try {
      audio = new Ctx();
    } catch (e) {
      audio = null;
    }
    return audio;
  }

  function running() {
    return !!audio && audio.state === "running";
  }

  /* Run whatever the page owes, if it is now allowed to. Safe to call as
     often as you like — it is a no-op when nothing is owed. */
  function flushPending() {
    if (!pendingChime || !running()) return;
    pendingChime = false;
    play();
  }

  function unlock() {
    var context = ensureContext();
    if (!context) return;
    if (context.state === "running") {
      flushPending();
      return;
    }
    /* resume() outside a gesture leaves the context suspended rather than
       throwing, so `flushPending` checks the state again rather than
       trusting that the promise resolving means anything. */
    context.resume().then(flushPending, function () {});
  }

  function note(startAt, frequency, duration) {
    var oscillator = audio.createOscillator();
    var gain = audio.createGain();

    // A sine, not the default sawtooth: this plays in a room with customers
    // in it, and it should read as a doorbell rather than an error.
    oscillator.type = "sine";
    oscillator.frequency.value = frequency;

    /* An envelope, because a bare gain of 1 that stops dead produces an
       audible click at both ends — the waveform is cut mid-cycle. Ramping up
       over 15ms and decaying to near-silence is what makes this a note. */
    gain.gain.setValueAtTime(0.0001, startAt);
    gain.gain.exponentialRampToValueAtTime(0.16, startAt + 0.015);
    gain.gain.exponentialRampToValueAtTime(0.0001, startAt + duration);

    oscillator.connect(gain);
    gain.connect(audio.destination);
    oscillator.start(startAt);
    oscillator.stop(startAt + duration + 0.02);
  }

  function play() {
    if (!running()) return;
    var now = audio.currentTime;
    note(now, 880, 0.12); // A5
    note(now + 0.13, 1174.66, 0.22); // D6 — a rising pair, not an alarm
  }

  function soundOn() {
    try {
      return localStorage.getItem(SOUND_KEY) !== "off";
    } catch (e) {
      return true;
    }
  }

  function setSoundOn(on) {
    try {
      localStorage.setItem(SOUND_KEY, on ? "on" : "off");
    } catch (e) {
      /* Private mode. The setting holds for this page view only. */
    }
  }

  function chime() {
    if (!soundOn()) return;
    if (running()) {
      play();
      return;
    }
    // Owed, and paid on the next gesture. See the comment on pendingChime.
    pendingChime = true;
    unlock();
  }

  // --- rendering ---------------------------------------------------------

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    // textContent, never innerHTML: `title` and `summary` are whatever a
    // stranger typed into a public form.
    if (text != null) node.textContent = text;
    return node;
  }

  function ago(iso) {
    var then = new Date(iso).getTime();
    if (isNaN(then)) return "";
    var seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
    if (seconds < 60) return "just now";
    var minutes = Math.round(seconds / 60);
    if (minutes < 60) return minutes + "m ago";
    var hours = Math.round(minutes / 60);
    if (hours < 24) return hours + "h ago";
    return Math.round(hours / 24) + "d ago";
  }

  function icon(kind) {
    return kind === "enquiry" ? "fa-envelope" : "fa-calendar-check";
  }

  function badge() {
    return document.querySelector(".salon-bell-badge");
  }

  function paintBadge() {
    var node = badge();
    if (!node) return;
    node.textContent = state.unread > 99 ? "99+" : String(state.unread);
    node.hidden = state.unread === 0;

    var button = document.querySelector(".salon-bell-toggle");
    if (button) {
      button.setAttribute(
        "aria-label",
        state.unread === 0
          ? "Notifications"
          : state.unread + " unread notifications"
      );
    }
  }

  function paintList() {
    var list = document.querySelector(".salon-bell-list");
    if (!list) return;
    list.textContent = "";

    if (!state.items.length) {
      list.appendChild(
        el("div", "salon-bell-empty", "Nothing new. Bookings and enquiries show up here.")
      );
      return;
    }

    state.items.forEach(function (item) {
      /* An <a> when there is somewhere to go and a <div> when there is not.
         A target can be deleted while its notification is still in the list;
         an anchor with no href is a link that silently does nothing, which is
         worse than an entry that plainly is not one. */
      var row = document.createElement(item.url ? "a" : "div");
      row.className = "salon-bell-item" + (item.unread ? " is-unread" : "");
      if (item.url) row.href = item.url;
      row.setAttribute("data-notification-id", item.id);

      var mark = el("span", "salon-bell-dot");
      mark.setAttribute("aria-hidden", "true");
      row.appendChild(mark);

      var body = el("span", "salon-bell-body");
      var head = el("span", "salon-bell-head");
      var glyph = el("i", "fas " + icon(item.kind) + " salon-bell-kind");
      glyph.setAttribute("aria-hidden", "true");
      head.appendChild(glyph);
      head.appendChild(el("span", "salon-bell-title", item.title));
      body.appendChild(head);
      if (item.summary) {
        body.appendChild(el("span", "salon-bell-summary", item.summary));
      }
      body.appendChild(el("span", "salon-bell-time", ago(item.at)));
      row.appendChild(body);

      list.appendChild(row);
    });
  }

  function paintSound() {
    var button = document.querySelector(".salon-bell-sound");
    if (!button) return;
    var on = soundOn();
    var label = on ? "Sound on — click to mute" : "Sound off — click to unmute";

    button.textContent = "";
    var glyph = el("i", "fas " + (on ? "fa-volume-high" : "fa-volume-xmark"));
    glyph.setAttribute("aria-hidden", "true");
    button.appendChild(glyph);

    button.classList.toggle("is-muted", !on);
    button.title = label;
    button.setAttribute("aria-label", label);
    button.setAttribute("aria-pressed", on ? "true" : "false");
  }

  function paint() {
    paintBadge();
    paintList();
  }

  // --- data --------------------------------------------------------------

  function seenId() {
    try {
      return parseInt(sessionStorage.getItem(SEEN_KEY), 10) || 0;
    } catch (e) {
      return 0;
    }
  }

  function rememberSeen(id) {
    try {
      sessionStorage.setItem(SEEN_KEY, String(id));
    } catch (e) {
      /* Private mode. The bell still works; it just may chime once more than
         it strictly needed to after a navigation. */
    }
  }

  function absorb(data, options) {
    if (!data || !data.ok) return;
    state.items = data.items || [];
    state.unread = data.unread || 0;

    var newest = state.items.reduce(function (highest, item) {
      return item.id > highest ? item.id : highest;
    }, 0);

    /* The chime fires on an id we have never seen, not on the count going up:
       the count also rises when another tab marks something unread-again, and
       it falls to zero the moment this tab reads everything — neither is an
       arrival. Suppressed when `silent`, which is how marking something read
       avoids ringing at the person who just clicked it. */
    var previous = seenId();
    if (!options || !options.silent) {
      if (previous && newest > previous) chime();
    }
    if (newest > previous) rememberSeen(newest);

    paint();
  }

  function refresh(options) {
    if (!endpoints || state.loading) return Promise.resolve();
    state.loading = true;
    return post(endpoints.feed, {})
      .then(function (data) {
        absorb(data, options);
      })
      .catch(function () {
        /* A failed poll is a network blip or a restarting dev server. The
           badge keeps whatever it last knew and the next tick tries again. */
      })
      .then(function () {
        state.loading = false;
      });
  }

  function markRead(id, keepalive) {
    if (!endpoints) return Promise.resolve();
    return post(endpoints.read, { id: id }, keepalive)
      .then(function (data) {
        absorb(data, { silent: true });
      })
      .catch(function () {});
  }

  function markAllRead() {
    if (!endpoints) return Promise.resolve();
    return post(endpoints.read, { all: true })
      .then(function (data) {
        absorb(data, { silent: true });
      })
      .catch(function () {});
  }

  // --- the panel ---------------------------------------------------------

  function setOpen(open) {
    var wrapper = document.querySelector(".salon-bell");
    var button = document.querySelector(".salon-bell-toggle");
    if (!wrapper || !button) return;
    state.open = open;
    wrapper.classList.toggle("is-open", open);
    button.setAttribute("aria-expanded", open ? "true" : "false");
    // Opening is the moment the list is most likely to be stale, and the
    // moment somebody is looking straight at it.
    if (open) refresh({ silent: true });
  }

  function build() {
    var cluster = document.querySelector(".app-header .navbar-nav.ms-auto");
    if (!cluster || document.querySelector(".salon-bell")) return false;

    var item = el("li", "nav-item salon-bell");

    var button = el("a", "nav-link salon-bell-toggle");
    button.href = "#";
    button.setAttribute("role", "button");
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("aria-label", "Notifications");
    var bell = el("i", "fas fa-bell");
    bell.setAttribute("aria-hidden", "true");
    button.appendChild(bell);
    var count = el("span", "salon-bell-badge");
    count.hidden = true;
    button.appendChild(count);
    item.appendChild(button);

    var panel = el("div", "salon-bell-panel");
    var header = el("div", "salon-bell-header");
    header.appendChild(el("span", "salon-bell-heading", "Notifications"));

    /* The mute switch, and the answer to "why can I not hear anything".
       Turning sound on plays the chime straight away: the click is itself
       the gesture the browser wants, so this both authorises audio for the
       page and proves out loud that it works. Without something like it the
       feature is untestable from the outside — silence looks the same
       whether it is muted, blocked, or broken. */
    var sound = el("button", "salon-bell-sound");
    sound.type = "button";
    header.appendChild(sound);

    var readAll = el("button", "salon-bell-readall", "Mark all read");
    readAll.type = "button";
    header.appendChild(readAll);
    panel.appendChild(header);
    panel.appendChild(el("div", "salon-bell-list"));
    item.appendChild(panel);

    button.addEventListener("click", function (event) {
      event.preventDefault();
      setOpen(!state.open);
    });

    sound.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      var next = !soundOn();
      setSoundOn(next);
      paintSound();
      if (next) {
        // Queue it and unlock, rather than calling play() directly: resume()
        // is asynchronous even inside a gesture, so playing immediately can
        // schedule notes against a clock that is not yet running.
        pendingChime = true;
        unlock();
      }
    });

    readAll.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      markAllRead();
    });

    /*
     * Clicking an entry marks it read and then navigates, in one gesture.
     * The POST is not awaited: waiting would put a visible pause between the
     * click and the page, and the badge is decremented locally anyway so the
     * number is already right on screen before the server has answered. What
     * makes it survive the navigation is `keepalive` on the request — see
     * post(). The response is discarded in that case, which is fine: the next
     * page polls for itself within a second of loading.
     */
    panel.addEventListener("click", function (event) {
      var target = event.target;
      var row = target && target.closest ? target.closest(".salon-bell-item") : null;
      if (!row) return;
      var id = row.getAttribute("data-notification-id");
      if (!id) return;

      var wasUnread = row.classList.contains("is-unread");
      row.classList.remove("is-unread");
      if (wasUnread && state.unread > 0) {
        state.unread -= 1;
        paintBadge();
      }

      var leaving = row.tagName === "A" && row.href;
      if (!leaving) event.preventDefault();
      markRead(id, leaving);
    });

    cluster.insertBefore(item, themeToggleItem(cluster) || cluster.lastElementChild);
    return true;
  }

  /* Left of the light/dark switch when there is one. static/admin/
     theme-toggle.js is loaded by Jazzmin's `custom_js`, which the template
     puts *above* `{% block extrajs %}`, so by the time this runs its button
     is already in the navbar. The fallback still works if that ever changes. */
  function themeToggleItem(cluster) {
    var toggle = cluster.querySelector(".salon-theme-toggle");
    return toggle ? toggle.closest("li") : null;
  }

  function closeOnOutsideClick() {
    document.addEventListener("click", function (event) {
      if (!state.open) return;
      var target = event.target;
      if (target && target.closest && target.closest(".salon-bell")) return;
      setOpen(false);
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && state.open) setOpen(false);
    });
  }

  // --- lifecycle ---------------------------------------------------------

  var GESTURES = ["pointerdown", "keydown", "touchstart"];

  function onGesture() {
    unlock();
    if (!running()) return;
    // Nothing left to unlock, so stop listening to every click on the page.
    GESTURES.forEach(function (name) {
      document.removeEventListener(name, onGesture, { capture: true });
    });
  }

  function init() {
    if (!endpoints) return;
    if (!build()) return;
    closeOnOutsideClick();
    paintSound();

    /* Built now, while nothing depends on it, so that the first arrival has
       a context to resume rather than one to construct. It comes up
       suspended and stays that way until a gesture; that is fine and costs
       nothing. */
    ensureContext();

    /* Deliberately not `{once: true}`. Any gesture is a chance to get the
       context running and to pay off a chime that is owed, and the first one
       is not guaranteed to succeed — a resume() started during a gesture can
       still be pending when that gesture ends. These stay attached until the
       context is running, then take themselves off. */
    GESTURES.forEach(function (name) {
      document.addEventListener(name, onGesture, { capture: true, passive: true });
    });

    refresh();
    setInterval(function () {
      if (document.hidden) return; // A background tab is not watching.
      refresh();
    }, POLL_MS);

    // Coming back to the tab is the one moment the list is guaranteed stale.
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) refresh();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
