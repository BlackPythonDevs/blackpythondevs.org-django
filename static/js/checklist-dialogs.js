/**
 * Opens/closes the per-task modal <dialog> in the checklist widget
 * (templates/checklists/includes/widget.html).
 *
 * Listeners are delegated on `document` because htmx replaces the whole
 * widget on every action. Saving details or adding a comment happens inside
 * the dialog, so the swap would otherwise close it: the open task's id is
 * remembered before the request and its dialog reopened after the swap.
 */
(function () {
  var openId = null;

  document.addEventListener("click", function (event) {
    var opener = event.target.closest(".checklist-task-open");
    if (opener) {
      var dialog = document.getElementById(opener.getAttribute("data-dialog"));
      if (dialog) dialog.showModal();
      return;
    }
    var closer = event.target.closest(".checklist-task-close");
    if (closer) {
      closer.closest("dialog").close();
      return;
    }
    // A click on the backdrop lands on the <dialog> element itself.
    if (event.target.matches && event.target.matches("dialog.checklist-task-dialog")) {
      event.target.close();
    }
  });

  document.body.addEventListener("htmx:beforeRequest", function () {
    var open = document.querySelector("dialog.checklist-task-dialog[open]");
    openId = open ? open.id : null;
  });

  document.body.addEventListener("htmx:afterSwap", function () {
    if (!openId) return;
    var dialog = document.getElementById(openId);
    openId = null;
    if (dialog && !dialog.open) dialog.showModal();
  });
})();
