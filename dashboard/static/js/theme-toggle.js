// OU-MRS Dashboard 2.0 - Theme toggle (Phase 9.8a)
// Default = dark (live trading default per spec). Persists in localStorage.

(function() {
  var KEY = "ou-mrs-theme";
  function apply(t) {
    document.documentElement.setAttribute("data-theme", t);
    try { localStorage.setItem(KEY, t); } catch (e) {}
    var b = document.getElementById("ou-theme-toggle");
    if (b) b.textContent = t === "dark" ? "light mode" : "dark mode";
  }
  function init() {
    var saved;
    try { saved = localStorage.getItem(KEY); } catch (e) { saved = null; }
    apply(saved || "dark");
    var b = document.getElementById("ou-theme-toggle");
    if (!b) {
      b = document.createElement("button");
      b.id = "ou-theme-toggle";
      b.type = "button";
      document.body.appendChild(b);
    }
    b.onclick = function() {
      var c = document.documentElement.getAttribute("data-theme") || "dark";
      apply(c === "dark" ? "light" : "dark");
    };
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else { init(); }
})();
