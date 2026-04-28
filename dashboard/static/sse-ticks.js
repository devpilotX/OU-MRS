/* Phase 9.6: SSE tick consumer.
 * Connects to /sse/ticks, exposes window.OUMRS_LIVE_TICKS,
 * paints a fixed top banner, and updates any element with
 *   data-sse-ltp="BNF|NF|FNF"
 */
(function () {
  if (window.__OUMRS_SSE_LOADED) return;
  window.__OUMRS_SSE_LOADED = true;
  window.OUMRS_LIVE_TICKS = window.OUMRS_LIVE_TICKS || {};

  function fmtINR(n) {
    return Number(n).toLocaleString("en-IN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  function ensureBanner() {
    var b = document.getElementById("sse-tick-banner");
    if (b) return b;
    b = document.createElement("div");
    b.id = "sse-tick-banner";
    b.style.cssText =
      "position:fixed;top:0;left:0;right:0;z-index:99999;" +
      "background:#0a0a0a;color:#0f0;font:12px/1.4 ui-monospace,Menlo,monospace;" +
      "padding:5px 12px;border-bottom:1px solid #1f3d1f;display:flex;" +
      "gap:18px;justify-content:center;align-items:center;flex-wrap:wrap;";
    b.innerHTML =
      '<span style="opacity:.6">LIVE TICKS</span>' +
      '<span data-sse-ltp="BNF">BNF —</span>' +
      '<span data-sse-ltp="NF">NF —</span>' +
      '<span data-sse-ltp="FNF">FNF —</span>' +
      '<span id="sse-state" style="opacity:.7">connecting…</span>';
    document.body.appendChild(b);
    var pad = parseInt(getComputedStyle(document.body).paddingTop, 10) || 0;
    document.body.style.paddingTop = pad + 30 + "px";
    return b;
  }

  function setState(txt, color) {
    var s = document.getElementById("sse-state");
    if (!s) return;
    s.textContent = txt;
    if (color) s.style.color = color;
  }

  function paintTick(t) {
    if (!t || !t.symbol) return;
    window.OUMRS_LIVE_TICKS[t.symbol] = t;
    var els = document.querySelectorAll('[data-sse-ltp="' + t.symbol + '"]');
    for (var i = 0; i < els.length; i++) {
      els[i].textContent = t.symbol + " ₹" + fmtINR(t.ltp);
    }
  }

  function connect() {
    var es = new EventSource("/sse/ticks");
    es.onopen = function () { setState("● live", "#0f0"); };
    es.onerror = function () { setState("⚠ reconnect", "#f60"); };
    es.onmessage = function (ev) {
      try {
        if (!ev.data) return;
        var t = JSON.parse(ev.data);
        paintTick(t);
      } catch (e) { /* ignore */ }
    };
  }

  function init() {
    ensureBanner();
    connect();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
