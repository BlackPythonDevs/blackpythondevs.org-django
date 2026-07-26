/**
 * Main JS file for BPD behaviours.
 *
 * Ported from the static site; the jQuery-based language switcher was dropped
 * since the Django site is single-locale for now.
 */

// Menu on small screens
document.querySelectorAll(".menu-toggle").forEach(function (toggle) {
  toggle.addEventListener("click", function (e) {
    document.body.classList.toggle("menu--opened");
    e.preventDefault();
  });
});
