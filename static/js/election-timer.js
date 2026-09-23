/**
 * Realtime countdown for the election page. Only counts down — it doesn't
 * refresh the page when the deadline passes, so a new phase (e.g. voting
 * opening) still needs a manual reload to show up.
 */

(function () {
  var el = document.getElementById("election-countdown");
  if (!el) return;

  var deadline = new Date(el.dataset.deadline).getTime();

  function render() {
    var remaining = deadline - Date.now();
    if (remaining <= 0) {
      el.textContent = "0d 0h 0m 0s";
      clearInterval(timer);
      return;
    }

    var seconds = Math.floor(remaining / 1000);
    var days = Math.floor(seconds / 86400);
    var hours = Math.floor((seconds % 86400) / 3600);
    var minutes = Math.floor((seconds % 3600) / 60);
    seconds = seconds % 60;

    el.textContent = days + "d " + hours + "h " + minutes + "m " + seconds + "s";
  }

  var timer = setInterval(render, 1000);
  render();
})();
