/* OU-MRS Live Dashboard - Phase 9.8h.J
 * Single-file vanilla SPA. Reads canonical /api/* responses.
 * Designed for 100% accuracy: no phantom fields, no fake placeholders.
 */
(() => {
  "use strict";

  const $ = (s, p = document) => p.querySelector(s);
  const $$ = (s, p = document) => Array.from(p.querySelectorAll(s));
  const EMDASH = "\u2014";
  const fmtInr = (n, d=0) => {
    if (n == null || Number.isNaN(Number(n))) return EMDASH;
    const num = Number(n);
    const sign = num >= 0 ? "+" : "\u2212";
    return sign + "\u20b9" + Math.abs(num).toLocaleString("en-IN", { maximumFractionDigits: d });
  };
  const fmtPct = (n, d=1) => (n == null || Number.isNaN(Number(n))) ? EMDASH : ((Number(n) >= 0 ? "+" : "") + Number(n).toFixed(d) + "%");
  const fmtNum = (n, d=2) => (n == null || Number.isNaN(Number(n))) ? EMDASH : Number(n).toFixed(d);
  const fmtTs = s => { if (!s) return EMDASH; try { return String(s).replace("T", " ").slice(0, 16); } catch { return String(s); } };
  const symFromEntry = (e) => {
    const n = Number(e || 0);
    if (n >= 40000) return "BNF";
    if (n >= 20000) return "NF";
    if (n >= 8000) return "MCN";
    return "?";
  };
  const todayIso = () => {
    const d = new Date();
    return d.getFullYear() + "-" + String(d.getMonth()+1).padStart(2,"0") + "-" + String(d.getDate()).padStart(2,"0");
  };
  async function getJ(url) {
    try {
      const r = await fetch(url, { credentials: "same-origin" });
      if (!r.ok) return null;
      return await r.json();
    } catch { return null; }
  }

  // ---- theme ----
  const themeBtn = $("#theme-toggle");
  function applyTheme(t) {
    document.documentElement.setAttribute("data-theme", t);
    try { localStorage.setItem("ou-mrs-theme", t); } catch {}
    if (themeBtn) {
      themeBtn.textContent = t === "dark" ? "\u263c" : "\u263e";
      themeBtn.title = "Switch to " + (t === "dark" ? "light" : "dark") + " theme";
    }
  }
  applyTheme(localStorage.getItem("ou-mrs-theme") || "dark");
  if (themeBtn) themeBtn.onclick = () => applyTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark");

  // ---- tabs ----
  let currentTab = "overview";
  $$(".tabs .tab").forEach(b => {
    b.onclick = () => {
      currentTab = b.dataset.tab;
      $$(".tabs .tab").forEach(x => x.classList.toggle("active", x === b));
      $$("section.section").forEach(s => s.classList.toggle("active", s.dataset.section === currentTab));
      refreshAll();
    };
  });

  // ---- kpi card ----
  function kpiHtml({ label, value, sub, tone }) {
    const t = tone ? " tone-" + tone : "";
    const vtone = (tone === "profit" || tone === "loss" || tone === "warn" || tone === "ok" || tone === "err") ? " tone-" + tone : "";
    return `<div class="kpi${t}"><div class="kpi-label">${label}</div><div class="kpi-value${vtone}">${value}</div><div class="kpi-sub">${(sub||[]).map(s => `<span>${s}</span>`).join("")}</div></div>`;
  }
  function severityToTone(sev) { return ({ ok: "ok", warn: "warn", err: "err", info: "info" })[sev] || "info"; }

  // ---- trades table ----
  function renderTrades(tbody, arr, opts={}) {
    if (!tbody) return;
    if (!arr.length) { tbody.innerHTML = `<tr><td colspan="${opts.cols||5}" style="text-align:center;color:var(--text-muted);padding:24px;">No trades match the current filters.</td></tr>`; return; }
    tbody.innerHTML = arr.map(t => {
      const sym = symFromEntry(t.entry);
      const pnl = Number(t.pnl || 0);
      const cls = pnl >= 0 ? "pnl-pos" : "pnl-neg";
      if (opts.compact) {
        return `<tr><td>${fmtTs(t.entry_ts).slice(5)}</td><td>${sym}</td><td>${t.side||""}</td><td class="${cls}">${fmtInr(pnl)}</td><td>${t.reason||""}</td></tr>`;
      }
      return `<tr><td>${fmtTs(t.entry_ts)}</td><td>${fmtTs(t.exit_ts)}</td><td>${sym}</td><td>${t.side||""}</td><td>${t.qty||""}</td><td>${t.entry||""}</td><td>${t.exit||""}</td><td class="${cls}">${fmtInr(pnl)}</td><td>${fmtInr(t.cum_pnl||0)}</td><td>${t.reason||""}</td></tr>`;
    }).join("");
  }

  // ---- svg charts ----
  function svgLine(container, points, opts={}) {
    if (!container) return;
    const w = container.clientWidth || 600;
    const h = container.clientHeight || 200;
    const pad = { t: 10, r: 12, b: 22, l: 56 };
    if (!points.length) { container.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted);font-size:12px;">No data yet.</div>`; return; }
    const xs = points.map((_, i) => i);
    const ys = points.map(p => Number(p.y));
    const xMax = Math.max(1, xs.length - 1);
    let yMin = Math.min(...ys), yMax = Math.max(...ys);
    if (opts.areaBase != null) { yMin = Math.min(yMin, opts.areaBase); yMax = Math.max(yMax, opts.areaBase); }
    if (yMin === yMax) { yMin -= 1; yMax += 1; }
    const sx = i => pad.l + (i / xMax) * (w - pad.l - pad.r);
    const sy = v => pad.t + (1 - (v - yMin) / (yMax - yMin)) * (h - pad.t - pad.b);
    const linePath = "M" + xs.map(i => sx(i) + "," + sy(ys[i])).join(" L");
    let area = "";
    if (opts.area) {
      const base = opts.areaBase != null ? opts.areaBase : yMin;
      area = `<path d="${linePath} L${sx(xs.length-1)},${sy(base)} L${sx(0)},${sy(base)} Z" fill="${opts.areaFill || "currentColor"}" fill-opacity=".15" stroke="none"/>`;
    }
    let grid = "";
    for (let i = 0; i <= 3; i++) {
      const yv = yMin + (yMax - yMin) * (i/3);
      const yy = sy(yv);
      grid += `<line x1="${pad.l}" y1="${yy}" x2="${w-pad.r}" y2="${yy}" class="chart-grid-line"/>`;
      grid += `<text x="${pad.l - 6}" y="${yy + 3}" class="chart-axis-text" text-anchor="end">${opts.yfmt ? opts.yfmt(yv) : yv.toFixed(0)}</text>`;
    }
    const idxs = [0, Math.floor((xs.length-1)/2), xs.length-1].filter((v,i,a) => a.indexOf(v) === i);
    const xlbl = idxs.map(i => `<text x="${sx(i)}" y="${h - 6}" class="chart-axis-text" text-anchor="middle">${points[i].xLabel || ""}</text>`).join("");
    container.innerHTML = `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">${grid}${area}<path d="${linePath}" class="${opts.lineClass || "chart-line"}"/>${xlbl}</svg>`;
  }
  function svgBars(container, points, opts={}) {
    if (!container) return;
    const w = container.clientWidth || 600;
    const h = container.clientHeight || 200;
    const pad = { t: 10, r: 12, b: 22, l: 56 };
    if (!points.length) { container.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted);font-size:12px;">No data yet.</div>`; return; }
    const ys = points.map(p => Number(p.y));
    let yMin = Math.min(0, ...ys), yMax = Math.max(0, ...ys);
    if (yMin === yMax) yMax += 1;
    const slot = (w - pad.l - pad.r) / Math.max(points.length, 1);
    const bw = Math.max(2, slot - 2);
    const sx = i => pad.l + i * slot;
    const sy = v => pad.t + (1 - (v - yMin) / (yMax - yMin)) * (h - pad.t - pad.b);
    const zero = sy(0);
    const bars = points.map((p, i) => {
      const y = sy(p.y);
      const top = Math.min(y, zero), height = Math.abs(y - zero);
      const cls = p.y >= 0 ? "chart-bar pos" : "chart-bar neg";
      return `<rect x="${sx(i)+1}" y="${top}" width="${bw}" height="${height}" class="${cls}"/>`;
    }).join("");
    let grid = "";
    for (let i = 0; i <= 3; i++) {
      const yv = yMin + (yMax - yMin) * (i/3);
      const yy = sy(yv);
      grid += `<line x1="${pad.l}" y1="${yy}" x2="${w-pad.r}" y2="${yy}" class="chart-grid-line"/>`;
      grid += `<text x="${pad.l - 6}" y="${yy + 3}" class="chart-axis-text" text-anchor="end">${opts.yfmt ? opts.yfmt(yv) : yv.toFixed(0)}</text>`;
    }
    const idxs = [0, Math.floor((points.length-1)/2), points.length-1].filter((v,i,a) => a.indexOf(v) === i);
    const xlbl = idxs.map(i => `<text x="${sx(i)+bw/2}" y="${h - 6}" class="chart-axis-text" text-anchor="middle">${points[i].xLabel || ""}</text>`).join("");
    container.innerHTML = `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">${grid}${bars}${xlbl}</svg>`;
  }

  // ---- shared state ----
  const state = { status: null, trades: null, tradesArr: [], filters: { symbol: "", side: "", reason: "", search: "" } };

  // ---- overview ----
  async function refreshOverview() {
    const [status, trades, dd] = await Promise.all([
      getJ("/api/status"), getJ("/api/trades"), getJ("/api/drawdown"),
    ]);
    state.status = status;
    state.trades = trades;
    state.tradesArr = (trades && trades.trades) || [];
    const arr = state.tradesArr;
    const today = todayIso();
    const todayTrades = arr.filter(t => (t.entry_ts || "").startsWith(today));
    const todayPnl = todayTrades.reduce((a, t) => a + (Number(t.pnl) || 0), 0);
    const cumPnl = (trades && trades.total_pnl != null) ? Number(trades.total_pnl) : arr.reduce((a, t) => a + (Number(t.pnl) || 0), 0);
    const winRate = (trades && trades.win_rate != null) ? Number(trades.win_rate) : 0;
    const daysTraded = new Set(arr.map(t => (t.entry_ts || "").slice(0, 10)).filter(Boolean)).size;
    const expectancy = arr.length > 0 ? cumPnl / arr.length : 0;
    let curDd = 0;
    if (dd && dd.rows && dd.rows.length) curDd = Number(dd.rows[dd.rows.length-1].dd_pct || 0);

    const cumTone = cumPnl > 0 ? "profit" : cumPnl < 0 ? "loss" : "info";
    const todayTone = todayPnl > 0 ? "profit" : todayPnl < 0 ? "loss" : "info";
    const botSev = severityToTone((status && status.bot_status_severity) || "info");
    const ddTone = curDd <= -5 ? "loss" : curDd <= -2 ? "warn" : "info";

    const grid = $("#kpi-grid");
    if (grid) grid.innerHTML = [
      kpiHtml({ label: "Cumulative P&L", value: fmtInr(cumPnl), sub: [`days: ${daysTraded}`, "all-time"], tone: cumTone }),
      kpiHtml({ label: "Today's P&L", value: fmtInr(todayPnl), sub: [`trades: ${todayTrades.length}`, today.slice(5)], tone: todayTone }),
      kpiHtml({ label: "Win rate", value: fmtPct(winRate * 100), sub: [`n=${arr.length}`, "closed trades"], tone: winRate >= 0.5 ? "profit" : "warn" }),
      kpiHtml({ label: "Expectancy", value: fmtInr(expectancy), sub: ["per trade"], tone: expectancy > 0 ? "profit" : "loss" }),
      kpiHtml({ label: "Bot status", value: (status && status.bot_status) || EMDASH, sub: [(status && status.bot_status_reason) || EMDASH, `hb: ${status && status.heartbeat_age_s != null ? Math.round(status.heartbeat_age_s) + "s" : EMDASH}`], tone: botSev }),
      kpiHtml({ label: "Drawdown", value: fmtPct(curDd), sub: ["from peak"], tone: ddTone }),
    ].join("");

    const modeBadge = $("#mode-badge");
    if (modeBadge) { modeBadge.textContent = (status && status.mode) || EMDASH; modeBadge.className = "badge " + ((status && status.live_mode) ? "badge-live" : "badge-paper"); }
    const botPill = $("#bot-status-pill");
    if (botPill) { botPill.textContent = (status && status.bot_status) || EMDASH; botPill.className = "pill pill-" + botSev; }
    const mktPill = $("#market-status-pill");
    if (mktPill) { mktPill.textContent = ((status && status.market_status) || EMDASH).toUpperCase(); mktPill.className = "pill pill-" + (status && status.market_status === "open" ? "ok" : status && status.market_status === "pre_open" ? "info" : "muted"); }

    renderTrades($("#overview-trades-tbody"), arr.slice(-5).reverse(), { compact: true, cols: 5 });

    let cum = 0;
    const pts = arr.map((t, i) => { cum += Number(t.pnl || 0); return { y: cum, xLabel: (i === 0 || i === arr.length - 1) ? fmtTs(t.entry_ts).slice(5, 10) : "" }; });
    svgLine($("#overview-sparkline"), pts, { area: true, areaBase: 0, areaFill: "var(--profit)", lineClass: "chart-line line-eq", yfmt: v => "\u20b9" + (v/1000).toFixed(0) + "k" });
  }

  // ---- trades tab ----
  function applyTradesFilters() {
    return state.tradesArr.filter(t => {
      const sym = symFromEntry(t.entry);
      if (state.filters.symbol && sym !== state.filters.symbol) return false;
      if (state.filters.side && t.side !== state.filters.side) return false;
      if (state.filters.reason && t.reason !== state.filters.reason) return false;
      if (state.filters.search) {
        const q = state.filters.search.toLowerCase();
        if (!JSON.stringify(t).toLowerCase().includes(q)) return false;
      }
      return true;
    });
  }
  async function refreshTrades() {
    if (!state.tradesArr.length) { const trades = await getJ("/api/trades"); state.trades = trades; state.tradesArr = (trades && trades.trades) || []; }
    const reasonSel = $("#filter-reason");
    if (reasonSel && reasonSel.options.length <= 1) {
      const uniq = Array.from(new Set(state.tradesArr.map(t => t.reason).filter(Boolean))).sort();
      for (const r of uniq) { const o = document.createElement("option"); o.value = o.textContent = r; reasonSel.appendChild(o); }
    }
    const out = applyTradesFilters();
    const totalPnl = out.reduce((a, t) => a + Number(t.pnl || 0), 0);
    const fs = $("#filter-stats");
    if (fs) fs.textContent = `${out.length} of ${state.tradesArr.length} trades \u00b7 sum P&L: ${fmtInr(totalPnl)}`;
    renderTrades($("#trades-full tbody"), out.slice().reverse(), { cols: 10 });
  }
  function bindFilters() {
    const sym = $("#filter-symbol"); if (sym) sym.onchange = e => { state.filters.symbol = e.target.value; refreshTrades(); };
    const side = $("#filter-side"); if (side) side.onchange = e => { state.filters.side = e.target.value; refreshTrades(); };
    const reason = $("#filter-reason"); if (reason) reason.onchange = e => { state.filters.reason = e.target.value; refreshTrades(); };
    const search = $("#filter-search"); if (search) search.oninput = e => { state.filters.search = e.target.value; refreshTrades(); };
  }

  // ---- live tab ----
  async function refreshLive() {
    const syms = ["BNF", "MCN", "NF"];
    const [states, portfolio, regime] = await Promise.all([
      Promise.all(syms.map(s => getJ("/api/live/state?symbol=" + s))),
      getJ("/api/portfolio"),
      getJ("/api/regime"),
    ]);
    const liveGrid = $("#live-grid");
    if (liveGrid) liveGrid.innerHTML = syms.map((sym, i) => {
      const d = states[i];
      if (!d || !d.ok) {
        return `<div class="live-card"><div class="live-card-head"><div class="live-card-sym">${sym}</div><div class="live-card-tag" style="color:var(--muted)">${(d && d.reason) || "no data"}</div></div><div class="live-card-ltp">${EMDASH}</div><div class="live-card-grid"><div><div class="lbl">message</div><div class="val">${(d && d.message) || EMDASH}</div></div></div></div>`;
      }
      const ltp = d.ltp != null ? d.ltp : (d.last_price != null ? d.last_price : (d.price != null ? d.price : null));
      const z = d.z_score != null ? d.z_score : (d.zscore != null ? d.zscore : (d.z != null ? d.z : null));
      const pos = d.position != null ? d.position : (d.pos != null ? d.pos : 0);
      const ageStr = d.age_sec != null ? Math.round(d.age_sec) + "s ago" : EMDASH;
      const tag = d.stale ? "STALE" : (d.is_lite ? "LITE" : "LIVE");
      const tagCol = d.stale ? "var(--loss)" : (d.is_lite ? "var(--warn)" : "var(--ok)");
      const lots = d.lots_open != null ? d.lots_open : (d.lots != null ? d.lots : null);
      return `<div class="live-card"><div class="live-card-head"><div class="live-card-sym">${sym}</div><div class="live-card-tag" style="color:${tagCol}">${tag} \u00b7 ${ageStr}</div></div><div class="live-card-ltp">${ltp != null ? Number(ltp).toLocaleString("en-IN", { maximumFractionDigits: 2 }) : EMDASH}</div><div class="live-card-grid"><div><div class="lbl">z-score</div><div class="val">${z != null ? fmtNum(z, 2) : EMDASH}</div></div><div><div class="lbl">position</div><div class="val">${pos ? pos : "flat"}</div></div><div><div class="lbl">lots open</div><div class="val">${lots != null ? lots : EMDASH}</div></div><div><div class="lbl">regime</div><div class="val">${(regime && regime.current) || EMDASH}</div></div></div></div>`;
    }).join("");
    const pg = $("#portfolio-grid");
    if (pg) {
      const rows = [];
      if (portfolio && portfolio.ok) {
        const rms = portfolio.rms || {};
        const pos = portfolio.position || {};
        rows.push(["Equity", rms.equity != null ? fmtInr(rms.equity) : EMDASH]);
        rows.push(["Day P&L", rms.day_pnl != null ? fmtInr(rms.day_pnl) : EMDASH]);
        rows.push(["Max DD today", rms.max_dd_today != null ? fmtPct(rms.max_dd_today) : EMDASH]);
        rows.push(["Open positions", Array.isArray(pos) ? pos.length : (Object.keys(pos).length || 0)]);
        rows.push(["Snapshot age", portfolio.age_sec != null ? Math.round(portfolio.age_sec) + "s" : EMDASH]);
        rows.push(["Stale", portfolio.stale ? "YES" : "no"]);
        rows.push(["Updated at", portfolio.ts || EMDASH]);
      } else {
        rows.push(["Status", (portfolio && portfolio.reason) || "no data"]);
        rows.push(["Message", (portfolio && portfolio.message) || EMDASH]);
      }
      pg.innerHTML = rows.map(([k, v]) => `<div><div class="lbl">${k}</div><div class="val">${v}</div></div>`).join("");
    }
  }

  // ---- performance tab ----
  async function refreshPerformance() {
    const [dd, daily, rolling] = await Promise.all([
      getJ("/api/drawdown"), getJ("/api/daily-pnl"), getJ("/api/rolling-metrics"),
    ]);
    const ddRows = (dd && dd.rows) || [];
    const eqPts = ddRows.map((r, i) => ({ y: Number(r.equity || 0), xLabel: (i === 0 || i === ddRows.length - 1) ? String(r.date || "").slice(5) : "" }));
    svgLine($("#equity-chart"), eqPts, { area: true, areaFill: "var(--profit)", lineClass: "chart-line line-eq", yfmt: v => "\u20b9" + (v / 1e5).toFixed(1) + "L" });
    const ddPts = ddRows.map((r, i) => ({ y: Number(r.dd_pct || 0), xLabel: (i === 0 || i === ddRows.length - 1) ? String(r.date || "").slice(5) : "" }));
    svgLine($("#drawdown-chart"), ddPts, { area: true, areaBase: 0, areaFill: "var(--loss)", lineClass: "chart-line line-dd", yfmt: v => v.toFixed(1) + "%" });
    const dRows = ((daily && daily.rows) || []).slice(-30);
    const dPts = dRows.map((r, i) => ({ y: Number(r.pnl || 0), xLabel: (i === 0 || i === dRows.length - 1) ? String(r.date || "").slice(5) : "" }));
    svgBars($("#daily-pnl-chart"), dPts, { yfmt: v => "\u20b9" + (v / 1000).toFixed(0) + "k" });
    const rm = rolling || {};
    const cards = [
      ["Sharpe (rolling)", rm.sharpe != null ? fmtNum(rm.sharpe, 2) : EMDASH],
      ["Sortino", rm.sortino != null ? fmtNum(rm.sortino, 2) : EMDASH],
      ["Win rate 30d", rm.win_rate_30d != null ? fmtPct(rm.win_rate_30d * 100) : EMDASH],
      ["Avg trade", rm.avg_trade != null ? fmtInr(rm.avg_trade) : EMDASH],
      ["Profit factor", rm.profit_factor != null ? fmtNum(rm.profit_factor, 2) : EMDASH],
      ["Max DD", rm.max_dd_pct != null ? fmtPct(rm.max_dd_pct) : EMDASH],
    ];
    const rg = $("#rolling-metrics");
    if (rg) rg.innerHTML = cards.map(([k, v]) => `<div class="health-card"><div class="h-label">${k}</div><div class="h-value">${v}</div></div>`).join("");
  }

  // ---- system tab ----
  async function refreshSystem() {
    const [health, market, regime, strategy, log] = await Promise.all([
      getJ("/api/health"), getJ("/api/market-status"), getJ("/api/regime"), getJ("/api/strategy"), getJ("/api/log?n=40"),
    ]);
    const status = state.status || await getJ("/api/status");
    const hc = [
      ["CPU", health && health.cpu_percent != null ? health.cpu_percent.toFixed(1) + "%" : EMDASH],
      ["Memory", health && health.memory_percent != null ? health.memory_percent.toFixed(1) + "%" : EMDASH],
      ["Disk", health && health.disk_percent != null ? health.disk_percent.toFixed(1) + "%" : EMDASH],
      ["Uptime", health && health.uptime_seconds != null ? Math.round(health.uptime_seconds / 3600) + "h" : EMDASH],
    ];
    const hcEl = $("#health-cards"); if (hcEl) hcEl.innerHTML = hc.map(([k, v]) => `<div class="health-card"><div class="h-label">${k}</div><div class="h-value">${v}</div></div>`).join("");
    const hbRows = [
      ["Service", (status && status.bot_state) || EMDASH],
      ["Timer", (status && status.timer_state) || EMDASH],
      ["Status", (status && status.bot_status) || EMDASH],
      ["Reason", (status && status.bot_status_reason) || EMDASH],
      ["Latest heartbeat", status && status.latest_heartbeat ? String(status.latest_heartbeat).slice(0, 100) : EMDASH],
      ["HB age (s)", status && status.heartbeat_age_s != null ? Math.round(status.heartbeat_age_s) : EMDASH],
      ["HB count today", (status && status.heartbeat_count_today != null) ? status.heartbeat_count_today : EMDASH],
      ["Server time", status && status.server_time ? fmtTs(status.server_time) : EMDASH],
      ["Capital (\u20b9)", status && status.capital ? Number(status.capital).toLocaleString("en-IN") : EMDASH],
      ["Mode", (status && status.mode) || EMDASH],
    ];
    const hbEl = $("#heartbeat-info"); if (hbEl) hbEl.innerHTML = hbRows.map(([k, v]) => `<div class="kv-k">${k}</div><div class="kv-v">${v}</div>`).join("");
    const rRows = [
      ["Current regime", (regime && regime.current) || EMDASH],
      ["ADX", regime && regime.current_adx != null ? fmtNum(regime.current_adx, 2) : EMDASH],
      ["Market status", market && market.status ? market.status.toUpperCase() + " \u2014 " + market.reason : EMDASH],
      ["IST now", market && market.now_ist ? fmtTs(market.now_ist) : EMDASH],
    ];
    const rEl = $("#regime-info"); if (rEl) rEl.innerHTML = rRows.map(([k, v]) => `<div class="kv-k">${k}</div><div class="kv-v">${v}</div>`).join("");
    const sRows = [
      ["Capital", strategy && strategy.capital ? "\u20b9" + Number(strategy.capital).toLocaleString("en-IN") : EMDASH],
      ["Tier", (strategy && strategy.capital_tier) || EMDASH],
      ["Z entry", strategy && strategy.z_entry != null ? strategy.z_entry : EMDASH],
      ["Z stop", strategy && strategy.z_stop != null ? strategy.z_stop : EMDASH],
      ["Window", strategy && strategy.window != null ? strategy.window : EMDASH],
      ["Live mode", strategy && strategy.live_mode ? "YES" : "no"],
      ["Symbols", strategy && Array.isArray(strategy.symbols) ? strategy.symbols.map(s => `${s.key}=${s.symbol} (lot ${s.lot_size}, max ${s.max_lots})`).join(" \u00b7 ") : EMDASH],
    ];
    const sEl = $("#strategy-info"); if (sEl) sEl.innerHTML = sRows.map(([k, v]) => `<div class="kv-k">${k}</div><div class="kv-v">${v}</div>`).join("");
    let logText = "";
    if (Array.isArray(log)) logText = log.join("\n");
    else if (log && Array.isArray(log.lines)) logText = log.lines.join("\n");
    else if (log && typeof log.tail === "string") logText = log.tail;
    else if (typeof log === "string") logText = log;
    else logText = "(no log)";
    const lp = $("#log-tail"); if (lp) lp.textContent = logText;
  }

  async function refreshAll() {
    try {
      await refreshOverview();
      if (currentTab === "trades") await refreshTrades();
      else if (currentTab === "live") await refreshLive();
      else if (currentTab === "performance") await refreshPerformance();
      else if (currentTab === "system") await refreshSystem();
      const rs = $("#refresh-status");
      if (rs) rs.textContent = "updated " + new Date().toLocaleTimeString("en-IN", { hour12: false });
    } catch (e) {
      const rs = $("#refresh-status");
      if (rs) rs.textContent = "error " + new Date().toLocaleTimeString("en-IN", { hour12: false });
    }
  }

  bindFilters();
  refreshAll();
  setInterval(refreshAll, 5000);
})();
