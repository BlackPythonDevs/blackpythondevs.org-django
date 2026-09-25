/**
 * Community Service Award nomination pages: a confirmation modal before any
 * state-changing submit (creating/editing a nomination, withdrawing one),
 * plus a dedicated modal for reinstating a withdrawn nomination.
 *
 * Both modals are native Pico-style <dialog> elements toggled by the `open`
 * attribute (see https://picocss.com/docs/modal) rather than
 * `showModal()`/`close()`, so a server-rendered reinstate modal already
 * displays correctly with no JS at all — this only adds the
 * confirm-before-submit step and the auto-open/backdrop-lock polish. The
 * overlay CSS itself lives in service-award.css since Pico's own dialog
 * component isn't loaded on this site.
 *
 * Without JS, forms still just post directly and the server still enforces
 * the reinstate check via a full page reload — this only adds a
 * confirmation step in front of that, it doesn't replace it.
 */
(function () {
  function openModal(dialog) {
    document.documentElement.classList.add("modal-is-open");
    dialog.setAttribute("open", "");
  }

  function closeModal(dialog) {
    dialog.removeAttribute("open");
    document.documentElement.classList.remove("modal-is-open");
  }

  document.querySelectorAll("[data-close-modal]").forEach(function (button) {
    button.addEventListener("click", function () {
      closeModal(button.closest("dialog"));
    });
  });

  // Resubmitting a withdrawn nomination (nomination form only) — the server
  // has already rendered this dialog `open`; just lock the scroll behind it.
  var reinstateModal = document.getElementById("reinstate-modal");
  var reinstateField = document.getElementById("reinstate-field");
  var reinstateConfirm = document.getElementById("reinstate-confirm");
  var nominationForm = document.getElementById("service-award-form");
  if (reinstateModal) {
    document.documentElement.classList.add("modal-is-open");
  }
  if (reinstateModal && reinstateField && reinstateConfirm && nominationForm) {
    reinstateConfirm.addEventListener("click", function () {
      reinstateField.value = "true";
      nominationForm.dataset.confirmed = "true";
      closeModal(reinstateModal);
      nominationForm.requestSubmit ? nominationForm.requestSubmit() : nominationForm.submit();
    });
  }

  // Every state-changing submit on the page (submit/save a nomination,
  // withdraw one) asks for plain confirmation first, via one shared modal.
  var confirmModal = document.getElementById("confirm-submit-modal");
  var confirmMessage = document.getElementById("confirm-submit-message");
  var confirmProceed = document.getElementById("confirm-submit-proceed");
  if (!confirmModal || !confirmMessage || !confirmProceed) return;

  var pendingForm = null;

  document.querySelectorAll("form[data-confirm-message]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (form.dataset.confirmed === "true") return;
      event.preventDefault();
      pendingForm = form;
      confirmMessage.textContent = form.dataset.confirmMessage;
      openModal(confirmModal);
    });
  });

  confirmProceed.addEventListener("click", function () {
    closeModal(confirmModal);
    if (!pendingForm) return;
    pendingForm.dataset.confirmed = "true";
    pendingForm.requestSubmit ? pendingForm.requestSubmit() : pendingForm.submit();
    pendingForm = null;
  });
})();
