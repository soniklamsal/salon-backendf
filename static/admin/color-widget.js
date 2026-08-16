/*
 * Keeps a native colour picker and its hex text field in step.
 *
 * The two inputs are siblings inside `.salon-color`; the picker carries the
 * swatch, the text field carries the actual stored value. The text field stays
 * because the model accepts any CSS colour, not only the 7-character hex a
 * <input type="color"> can represent — "black", "rgb(10 10 10)" and
 * "transparent" are all valid here and none of them can be shown in a picker.
 *
 * So the sync is deliberately one-and-a-half-way:
 *   picker changes -> always write the hex into the text field;
 *   text changes   -> update the picker only when the value IS 7-char hex,
 *                     otherwise leave the swatch alone rather than silently
 *                     rewriting what someone typed.
 */
(function () {
  "use strict";

  var HEX = /^#[0-9a-f]{6}$/i;

  function wire(wrapper) {
    var picker = wrapper.querySelector('input[type="color"]');
    var text = wrapper.querySelector('input[type="text"]');
    if (!picker || !text) return;

    if (HEX.test(text.value.trim())) {
      picker.value = text.value.trim().toLowerCase();
    }

    picker.addEventListener("input", function () {
      text.value = picker.value;
      // Django's "you have unsaved changes" guard listens for this.
      text.dispatchEvent(new Event("change", { bubbles: true }));
    });

    text.addEventListener("input", function () {
      var value = text.value.trim();
      if (HEX.test(value)) picker.value = value.toLowerCase();
    });
  }

  function init() {
    document.querySelectorAll(".salon-color").forEach(wire);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
