// "Copy to clipboard" for invite links shown in the InviteLink admin (the
// change form's readonly field and the message shown right after creating
// one). Delegated on document so it works no matter how many copies of the
// widget end up on the page.
document.addEventListener("click", function (event) {
  const button = event.target.closest(".invite-copy-button");
  if (!button) return;

  const input = button.previousElementSibling;
  const url = window.location.origin + input.value;

  navigator.clipboard.writeText(url).then(function () {
    const original = button.textContent;
    button.textContent = "Copied!";
    setTimeout(function () {
      button.textContent = original;
    }, 1500);
  });
});
