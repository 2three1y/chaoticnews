// Chaotic News: today's date, 'Updated 12 min ago' times, the fake newsletter button.
// Local file, no trackers. Written by tools/add_story.py (SITE_JS).
(function () {
  var t = document.getElementById("today");
  if (t && Date.prototype.toLocaleDateString) {
    var d = new Date();
    t.textContent = d.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" });
    t.setAttribute("datetime", d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"));
  }
  function ago(iso) {
    var m = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
    if (isNaN(m)) return null;
    if (m < 1) return "just now";
    if (m < 60) return m + " min ago";
    var h = Math.floor(m / 60);
    if (h < 24) return h + (h === 1 ? " hour ago" : " hours ago");
    var dd = Math.floor(h / 24);
    return dd + (dd === 1 ? " day ago" : " days ago");
  }
  document.querySelectorAll("time[data-ago]").forEach(function (el) {
    var a = ago(el.getAttribute("datetime"));
    if (a) el.textContent = el.getAttribute("data-ago") + " " + a;
  });
  document.querySelectorAll("[data-nl]").forEach(function (b) {
    b.addEventListener("click", function () {
      var box = b.closest(".newsletter");
      var st = box && box.querySelector(".nl-status");
      if (st) st.textContent = b.getAttribute("data-nl");
    });
  });
})();
