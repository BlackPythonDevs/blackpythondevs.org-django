/**
 * Live "@" autocomplete for the checklist widget's comment/note textareas
 * (templates/checklists/includes/widget.html) — a small suggestions list
 * appears as soon as you type "@" and narrows on the characters you keep
 * typing, backed by MentionSuggestionsView (views.py) at the widget's own
 * `data-mention-url`.
 *
 * Progressive enhancement, not a replacement: mentions.py's own
 * `@username` parsing (mentions.py's find_mentioned_users/render_mentions)
 * works from plain typed text regardless of whether this ever loads or a
 * request fails — this script is purely a typing aid.
 *
 * Every listener is delegated on `document`, the same reasoning as
 * checklist-dragdrop.js: htmx replaces the whole widget on every action, so
 * a listener bound to a specific textarea would go dead after the first
 * swap.
 */
(function () {
  var DEBOUNCE_MS = 150;

  var debounceTimer = null;
  var dropdown = null;
  var activeTextarea = null;
  var activeMatches = [];
  var activeIndex = -1;

  function mentionUrl() {
    var widget = document.querySelector(".checklist-widget");
    return widget ? widget.dataset.mentionUrl : null;
  }

  // The "@word" immediately before the caret, if the caret is inside one —
  // null otherwise, which is how a plain keystroke elsewhere in the text
  // (or no "@" at all) closes the dropdown.
  function mentionMatchBeforeCaret(textarea) {
    var text = textarea.value.slice(0, textarea.selectionStart);
    return text.match(/(?:^|\s)@(\w*)$/);
  }

  function closeDropdown() {
    if (dropdown) dropdown.remove();
    dropdown = null;
    activeTextarea = null;
    activeMatches = [];
    activeIndex = -1;
  }

  function openDropdown(textarea) {
    dropdown = document.createElement("ul");
    dropdown.className = "checklist-mention-suggestions";
    var rect = textarea.getBoundingClientRect();
    dropdown.style.top = window.scrollY + rect.bottom + "px";
    dropdown.style.left = window.scrollX + rect.left + "px";
    dropdown.style.width = Math.min(Math.max(rect.width, 220), 320) + "px";
    document.body.appendChild(dropdown);
    activeTextarea = textarea;
  }

  function rebuildList() {
    if (!dropdown) return;
    dropdown.innerHTML = "";
    activeMatches.forEach(function (match, index) {
      var item = document.createElement("li");
      item.textContent = match.label && match.label !== match.username ? "@" + match.username + " — " + match.label : "@" + match.username;
      if (index === activeIndex) item.classList.add("is-active");
      // mousedown (not click) fires before the textarea would blur, and
      // preventDefault keeps focus from ever leaving it.
      item.addEventListener("mousedown", function (event) {
        event.preventDefault();
        applyMatch(match);
      });
      dropdown.appendChild(item);
    });
  }

  function showMatches(textarea, matches) {
    if (matches.length === 0) {
      closeDropdown();
      return;
    }
    if (!dropdown || activeTextarea !== textarea) {
      closeDropdown();
      openDropdown(textarea);
    }
    activeMatches = matches;
    activeIndex = 0;
    rebuildList();
  }

  function applyMatch(match) {
    var textarea = activeTextarea;
    if (!textarea) return;
    var caret = textarea.selectionStart;
    var mentionMatch = mentionMatchBeforeCaret(textarea);
    if (!mentionMatch) return closeDropdown();

    var leadingWhitespace = mentionMatch[0].length - mentionMatch[0].trimStart().length;
    var start = caret - mentionMatch[0].length + leadingWhitespace;
    var replacement = "@" + match.username + " ";
    textarea.value = textarea.value.slice(0, start) + replacement + textarea.value.slice(caret);

    var newCaret = start + replacement.length;
    textarea.setSelectionRange(newCaret, newCaret);
    textarea.focus();
    closeDropdown();
  }

  function fetchMatches(textarea, query) {
    var url = mentionUrl();
    if (!url) return;
    fetch(url + "?q=" + encodeURIComponent(query))
      .then(function (response) {
        return response.ok ? response.json() : [];
      })
      .then(function (matches) {
        // The caret may have moved off any "@word" (or the widget swapped
        // out from under us) while this request was in flight.
        if (document.activeElement !== textarea || !mentionMatchBeforeCaret(textarea)) return;
        showMatches(textarea, matches);
      })
      .catch(function () {});
  }

  document.addEventListener("input", function (event) {
    var textarea = event.target;
    if (!textarea.matches || !textarea.matches(".checklist-widget textarea[name='body']")) return;

    var mentionMatch = mentionMatchBeforeCaret(textarea);
    window.clearTimeout(debounceTimer);
    if (!mentionMatch) {
      closeDropdown();
      return;
    }
    var query = mentionMatch[1];
    debounceTimer = window.setTimeout(function () {
      fetchMatches(textarea, query);
    }, DEBOUNCE_MS);
  });

  document.addEventListener("keydown", function (event) {
    if (!dropdown || activeMatches.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      activeIndex = (activeIndex + 1) % activeMatches.length;
      rebuildList();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      activeIndex = (activeIndex - 1 + activeMatches.length) % activeMatches.length;
      rebuildList();
    } else if (event.key === "Enter" || event.key === "Tab") {
      event.preventDefault();
      applyMatch(activeMatches[activeIndex]);
    } else if (event.key === "Escape") {
      closeDropdown();
    }
  });

  // Capture phase: blur doesn't bubble. A delay gives a suggestion's own
  // mousedown handler (which prevents the blur outright) a chance to run
  // first; this is only the fallback for tabbing or clicking away entirely.
  document.addEventListener(
    "blur",
    function () {
      window.setTimeout(closeDropdown, 100);
    },
    true
  );

  document.body.addEventListener("htmx:afterSwap", closeDropdown);
})();
