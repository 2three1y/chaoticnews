// Chaotic News: shows today's date in the masthead. Local file, no trackers.
(function () {
  var t = document.getElementById("today");
  if (!t || !Date.prototype.toLocaleDateString) return;
  var d = new Date();
  t.textContent = d.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" });
  t.setAttribute("datetime", d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"));
})();
