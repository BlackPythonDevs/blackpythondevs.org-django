/**
 * Dark/light theme toggle. The stored preference is applied inline in <head>
 * before first paint; this only wires up the button and keeps the icon in sync.
 */
(function () {
  var btn = document.getElementById("theme-toggle");
  if (!btn) return;

  var icon = btn.querySelector("i");
  var osDark = window.matchMedia("(prefers-color-scheme:dark)");

  function effective() {
    var stored = localStorage.getItem("theme");
    if (stored === "light" || stored === "dark") return stored;
    return osDark.matches ? "dark" : "light";
  }

  function updateIcon() {
    if (icon) icon.className = effective() === "dark" ? "iconoir-sun-light" : "iconoir-half-moon";
  }

  updateIcon();

  btn.addEventListener("click", function (e) {
    e.stopPropagation();
    var doc = document.documentElement;
    doc.classList.add("theme-transition");
    var next = effective() === "dark" ? "light" : "dark";
    doc.setAttribute("data-theme", next);
    localStorage.setItem("theme", next);
    updateIcon();
    setTimeout(function () {
      doc.classList.remove("theme-transition");
    }, 600);
  });

  osDark.addEventListener("change", updateIcon);
})();
