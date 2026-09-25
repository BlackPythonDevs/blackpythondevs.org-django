/**
 * Candidate statement popups on the election page: clicking "Read
 * statement" on a candidacy card opens that candidate's full statement in a
 * modal instead of the grid card having to show it inline. Same native
 * Pico-style <dialog> approach as the Community Service Award modals (see
 * service-award-form.js) — toggled via the `open` attribute rather than
 * showModal()/close() — kept as its own file since neither page loads the
 * other's script.
 */
(function () {
  // See service-award-form.js: <main class="container">'s entrance
  // animation keeps it a containing block for `position: fixed`
  // descendants, so these dialogs are moved to be direct children of
  // <body> to actually fix to the viewport.
  document.querySelectorAll("dialog.statement-modal").forEach(function (dialog) {
    document.body.appendChild(dialog);
  });

  function openModal(dialog) {
    document.documentElement.classList.add("modal-is-open");
    dialog.setAttribute("open", "");
  }

  function closeModal(dialog) {
    dialog.removeAttribute("open");
    document.documentElement.classList.remove("modal-is-open");
  }

  document.querySelectorAll("[data-open-modal]").forEach(function (button) {
    button.addEventListener("click", function () {
      var dialog = document.getElementById(button.dataset.openModal);
      if (dialog) openModal(dialog);
    });
  });

  document.querySelectorAll("dialog.statement-modal [data-close-modal]").forEach(function (button) {
    button.addEventListener("click", function () {
      closeModal(button.closest("dialog"));
    });
  });

  // Clicking the backdrop (the dialog itself, not its .card) closes it too.
  document.querySelectorAll("dialog.statement-modal").forEach(function (dialog) {
    dialog.addEventListener("click", function (event) {
      if (event.target === dialog) closeModal(dialog);
    });
  });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    document.querySelectorAll("dialog.statement-modal[open]").forEach(closeModal);
  });
})();
