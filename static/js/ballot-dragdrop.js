/**
 * Turns the ballot's per-candidate rank inputs (elections/forms.py
 * BallotForm) into a drag-and-drop reorderable list, one per region, on
 * the ballot page.
 *
 * Progressive enhancement, not a replacement: the number inputs are still
 * the real form fields that get submitted — this script only fills them in
 * as cards move, then hides them (see elections.css's `.js-ballot` rule).
 * Without JavaScript the inputs stay visible and typeable, same as before
 * this existed.
 *
 * Each region elects its own representative (see elections/models.py's
 * `regional_results`), so a card never leaves its own region's list —
 * dragging (or the &#9650;/&#9660; buttons) only reorders it against other
 * candidates in that same race. A card's position within its list *is*
 * its submitted rank for that region's race; nothing gets numbered across
 * region boundaries.
 */
(function () {
  var form = document.getElementById("ballot-form");
  var regionLists = Array.prototype.slice.call(document.querySelectorAll(".ballot-region-list"));
  if (!form || regionLists.length === 0) return;

  form.classList.add("js-ballot");

  function renumber() {
    regionLists.forEach(function (list) {
      var cards = Array.prototype.slice.call(list.children);
      cards.forEach(function (card, index) {
        card.querySelector(".ballot-card-input").value = index + 1;
        card.querySelector(".ballot-card-rank").textContent = String(index + 1) + ".";
        card.querySelector(".ballot-card-move-up").disabled = index === 0;
        card.querySelector(".ballot-card-move-down").disabled = index === cards.length - 1;
      });
    });
  }

  document.addEventListener("click", function (event) {
    var moveUp = event.target.closest(".ballot-card-move-up");
    var moveDown = event.target.closest(".ballot-card-move-down");
    var button = moveUp || moveDown;
    if (!button) return;
    var card = button.closest(".ballot-card");
    if (moveUp && !card.previousElementSibling) return;
    if (moveDown && !card.nextElementSibling) return;
    var parent = card.parentElement;
    var sibling = moveUp ? card.previousElementSibling : card.nextElementSibling.nextElementSibling;
    parent.insertBefore(card, sibling);
    renumber();
  });

  var dragged = null;
  var dragImage = null;

  document.addEventListener("dragstart", function (event) {
    var card = event.target.closest(".ballot-card");
    if (!card) return;
    dragged = card;
    event.dataTransfer.effectAllowed = "move";

    // The browser's default drag image is a flat snapshot taken before any
    // class changes land, so it can't itself look "lifted" — instead, hand
    // it a styled clone (shadow, slight tilt) positioned off-screen just
    // long enough to be rasterized, and dim the real card in place as a
    // placeholder for where it'll land.
    dragImage = card.cloneNode(true);
    dragImage.classList.add("ballot-card-dragimage");
    dragImage.style.width = card.getBoundingClientRect().width + "px";
    dragImage.style.position = "fixed";
    dragImage.style.top = "-1000px";
    dragImage.style.left = "-1000px";
    document.body.appendChild(dragImage);
    event.dataTransfer.setDragImage(dragImage, event.offsetX, event.offsetY);

    // Adding the placeholder look has to wait a tick, or it gets captured
    // in the browser's snapshot of `card` too (Firefox especially).
    window.setTimeout(function () {
      card.classList.add("is-dragging");
    }, 0);
  });

  document.addEventListener("dragend", function () {
    if (dragged) dragged.classList.remove("is-dragging");
    if (dragImage) dragImage.remove();
    dragged = null;
    dragImage = null;
  });

  regionLists.forEach(function (list) {
    list.addEventListener("dragover", function (event) {
      // A card only ever reorders within its own region's list — that's a
      // different candidate's race, not a rank a drop there could mean.
      if (!dragged || dragged.dataset.region !== list.dataset.region) return;
      event.preventDefault();
      var siblings = Array.prototype.slice.call(list.children).filter(function (child) {
        return child !== dragged;
      });
      var before = siblings.find(function (child) {
        return event.clientY < child.getBoundingClientRect().top + child.offsetHeight / 2;
      });
      list.insertBefore(dragged, before || null);
      renumber();
    });
  });

  renumber();
})();
