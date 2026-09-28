/**
 * Turns the checklist widget's task list (templates/checklists/includes/
 * widget.html) into a drag-and-drop reorderable list, one per widget on the
 * page.
 *
 * Progressive enhancement, not a replacement: without JavaScript the list is
 * just a plain, static <ol> — there's no server round trip to fall back to
 * for reordering, so the move-up/move-down buttons and drag handles are
 * this feature's only entry points, both added by this script.
 *
 * Unlike the ballot page (static/js/ballot-dragdrop.js), a task's hidden
 * `task_id` input travels with its <li> in the DOM (see widget.html's
 * `form="checklist-reorder-form"` attribute), so reordering the cards is
 * enough — there's nothing to renumber into the inputs themselves. Each
 * move submits the shared reorder form immediately (via htmx — see the
 * form's hx-post attribute), matching the widget's existing
 * instant-persistence UX (the toggle checkboxes do the same).
 *
 * Every listener here is delegated on `document` rather than bound to the
 * `<ol>`/cards directly, because htmx replaces the whole widget (including
 * its task list) on every action (hx-swap="outerHTML") — a listener
 * attached to the old, now-discarded list would silently stop firing.
 * `htmx:afterSwap` re-runs the up/down disabled-state pass for the same
 * reason: the freshly rendered buttons don't carry that state themselves.
 */
(function () {
  function reorderForm(list) {
    var firstInput = list.querySelector("input[form]");
    if (!firstInput) return null;
    return document.getElementById(firstInput.getAttribute("form"));
  }

  function refreshButtons(list) {
    var cards = Array.prototype.slice.call(list.children);
    cards.forEach(function (card, index) {
      card.querySelector(".checklist-task-move-up").disabled = index === 0;
      card.querySelector(".checklist-task-move-down").disabled = index === cards.length - 1;
    });
  }

  function refreshAllLists() {
    Array.prototype.slice.call(document.querySelectorAll(".checklist-task-list")).forEach(refreshButtons);
  }

  document.addEventListener("click", function (event) {
    var moveUp = event.target.closest(".checklist-task-move-up");
    var moveDown = event.target.closest(".checklist-task-move-down");
    var button = moveUp || moveDown;
    if (!button) return;
    var card = button.closest(".checklist-task-card");
    if (moveUp && !card.previousElementSibling) return;
    if (moveDown && !card.nextElementSibling) return;
    var list = card.parentElement;
    var sibling = moveUp ? card.previousElementSibling : card.nextElementSibling.nextElementSibling;
    list.insertBefore(card, sibling);
    refreshButtons(list);
    var form = reorderForm(list);
    if (form) form.requestSubmit();
  });

  var dragged = null;
  var dragImage = null;

  document.addEventListener("dragstart", function (event) {
    var card = event.target.closest(".checklist-task-card");
    if (!card) return;
    dragged = card;
    event.dataTransfer.effectAllowed = "move";

    dragImage = card.cloneNode(true);
    dragImage.classList.add("checklist-task-card-dragimage");
    dragImage.style.width = card.getBoundingClientRect().width + "px";
    dragImage.style.position = "fixed";
    dragImage.style.top = "-1000px";
    dragImage.style.left = "-1000px";
    document.body.appendChild(dragImage);
    event.dataTransfer.setDragImage(dragImage, event.offsetX, event.offsetY);

    window.setTimeout(function () {
      card.classList.add("is-dragging");
    }, 0);
  });

  document.addEventListener("dragend", function () {
    if (dragged) {
      var list = dragged.parentElement;
      dragged.classList.remove("is-dragging");
      refreshButtons(list);
      var form = reorderForm(list);
      if (form) form.requestSubmit();
    }
    if (dragImage) dragImage.remove();
    dragged = null;
    dragImage = null;
  });

  document.addEventListener("dragover", function (event) {
    if (!dragged) return;
    var list = event.target.closest(".checklist-task-list");
    if (!list || dragged.parentElement !== list) return;
    event.preventDefault();
    var siblings = Array.prototype.slice.call(list.children).filter(function (child) {
      return child !== dragged;
    });
    var before = siblings.find(function (child) {
      return event.clientY < child.getBoundingClientRect().top + child.offsetHeight / 2;
    });
    list.insertBefore(dragged, before || null);
  });

  refreshAllLists();
  document.body.addEventListener("htmx:afterSwap", refreshAllLists);
})();
