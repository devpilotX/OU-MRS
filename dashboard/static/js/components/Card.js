// OU-MRS Dashboard 2.0 - Card component (Phase 9.8a)
// Vanilla JS, no framework.
// Usage: new OuCard("#my-el", { title, metric, supporting: [], status: "ou-profit" });

(function() {
  function escape(s) {
    if (s == null) return "";
    return String(s).replace(/[&<>"']/g, function(c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c];
    });
  }
  function OuCard(el, opts) {
    this.el = typeof el === "string" ? document.querySelector(el) : el;
    this.opts = opts || {};
    this.render();
  }
  OuCard.prototype.render = function() {
    var o = this.opts, sup = o.supporting || [];
    if (!this.el) return;
    this.el.classList.add("ou-card");
    if (o.status) {
      this.el.classList.remove("ou-profit", "ou-loss", "ou-warn", "ou-critical", "ou-idle");
      this.el.classList.add(o.status);
    }
    var html = "";
    if (o.title) html += '<div class="ou-card-header">' + escape(o.title) + '</div>';
    if (o.metric != null) html += '<div class="ou-card-metric">' + escape(o.metric) + '</div>';
    if (sup.length) {
      html += '<div class="ou-card-supporting">';
      for (var i = 0; i < sup.length; i++) html += "<span>" + escape(sup[i]) + "</span>";
      html += "</div>";
    }
    this.el.innerHTML = html;
  };
  OuCard.prototype.update = function(opts) {
    for (var k in opts) this.opts[k] = opts[k];
    this.render();
  };
  window.OuCard = OuCard;
})();
