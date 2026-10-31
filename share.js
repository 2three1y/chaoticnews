// Chaotic News share buttons. Local file, no trackers.
(function () {
  var status = document.getElementById("share-status");
  function say(msg) {
    if (!status) return;
    status.textContent = msg;
    clearTimeout(say.t);
    say.t = setTimeout(function () { status.textContent = ""; }, 5000);
  }
  document.querySelectorAll("[data-copy]").forEach(function (b) {
    if (!navigator.clipboard) return;
    b.hidden = false;
    b.addEventListener("click", function () {
      navigator.clipboard.writeText(b.getAttribute("data-copy")).then(
        function () { say("Link copied."); },
        function () { say("Couldn't copy the link."); });
    });
  });
  document.querySelectorAll("[data-share]").forEach(function (b) {
    if (!navigator.share) return;
    b.hidden = false;
    b.addEventListener("click", function () {
      navigator.share({ title: b.getAttribute("data-title"), url: b.getAttribute("data-share") }).catch(function () {});
    });
  });
})();
