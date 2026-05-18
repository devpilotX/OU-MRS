// DPR_v1 -- crisp chart rendering on HiDPI displays
(function(){
  if (typeof Chart !== "undefined") {
    Chart.defaults.devicePixelRatio = Math.max(window.devicePixelRatio || 1, 2);
    Chart.defaults.responsive = true;
    Chart.defaults.maintainAspectRatio = false;
    Chart.defaults.font.family = "Inter, system-ui, -apple-system, sans-serif";
    Chart.defaults.font.size = 11;
    Chart.defaults.animation.duration = 400;
  }
})();

const $ = s => document.querySelector(s);
const fmtMoney = v => v==null||isNaN(v) ? "--" : (v<0?"-":"") + "₹" + Math.abs(Math.round(v)).toLocaleString("en-IN");
const fmtPct = v => v==null ? "--" : (v*100).toFixed(2) + "%";
let equityChart=null, pnlChart=null, ddChart=null;

async function fetchJSON(url){const r=await fetch(url,{credentials:"same-origin"});if(r.status===401){location.href="/login";return null;}return r.json();}
function humanDur(s){if(!s)return"--";const h=Math.floor(s/3600),m=Math.floor((s%3600)/60);if(h>24)return Math.floor(h/24)+"d "+(h%24)+"h";if(h>0)return h+"h "+m+"m";return m+"m";}
function escHtml(s){return(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}

async function refreshStatus(){
  const t0 = performance.now();
  const s = await fetchJSON('/api/status'); if(!s) return;
  if (typeof recordLatency === 'function') recordLatency('status', performance.now() - t0);
  const lbl = s.bot_status || (s.bot_state || '--').toUpperCase();
  const sev = s.bot_status_severity || (s.bot_state === 'active' ? 'ok' : '');
  const el = $('#bot-status');
  el.textContent = lbl;
  el.className = 'kpi-value bot-sev-' + sev;
  $('#bot-sub').textContent = s.bot_status_reason || ('Timer: ' + (s.timer_state || '--'));
  $('#capital').textContent = fmtMoney(s.capital);
  $('#mode-label').textContent = s.live_mode ? 'LIVE' : 'Paper';
  const mc = $('#mode-chip'); if(mc){ mc.textContent = s.live_mode ? 'LIVE' : 'Paper'; mc.className = 'chip ' + (s.live_mode ? 'err' : 'info'); }
  const tbm = $('#tb-mode'); if(tbm){ tbm.textContent = s.live_mode ? 'LIVE' : 'PAPER'; tbm.className = 'tb-mode tb-mode-' + (s.live_mode ? 'live' : 'paper'); }
  const hbi = $('#heartbeat-info'); if(hbi) hbi.textContent = 'Heartbeats today: ' + (s.heartbeat_count_today || 0);
  const stEl = $('#server-time'); if(stEl) stEl.textContent = new Date(s.server_time).toLocaleTimeString();
  if(s.next_run_usec){ const us = parseInt(s.next_run_usec); if(us > 0){ const dt = new Date(us/1000); const sched = $('#schedule-time'); if(sched) sched.textContent = dt.toLocaleString('en-IN',{weekday:'short',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'}); } }
}


function _ecGaugeColor(pct, mode){
  if (mode === 'progress') {
    if (pct >= 0.80) return 'ok';
    if (pct >= 0.40) return 'warn';
    return 'err';
  }
  if (pct >= 0.80) return 'err';
  if (pct >= 0.60) return 'warn';
  return 'ok';
}

function _ecGaugeUpdate(id, pct, sev, valStr){
  const fg = document.querySelector('#ec-gauge-' + id + ' .ec-gauge-fg');
  const valEl = document.querySelector('#ec-gauge-' + id + ' .ec-gauge-val');
  if (!fg || !valEl) return;
  const C = 125.66;
  fg.setAttribute('stroke-dashoffset', String(C * (1 - Math.max(0, Math.min(1, pct)))));
  fg.setAttribute('class', 'ec-gauge-fg ec-gauge-' + sev);
  valEl.textContent = valStr;
  valEl.className = 'ec-gauge-val ec-' + sev;
}

async function refreshChallenge(){ /* legacy noop - Risk panel now self-polls via P98F IIFE */ }
async function refreshHealth(){
  const h=await fetchJSON("/api/health");if(!h)return;
  const c=$("#health-chip")||document.createElement("span");
  if(h.error){c.textContent="health err";c.className="chip err";return;}
  c.textContent=`CPU ${Math.round(h.cpu_percent)}% · RAM ${Math.round(h.memory_percent)}% · DISK ${Math.round(h.disk_percent)}%`;
  c.className="chip "+(h.cpu_percent>80||h.memory_percent>85?"warn":"ok");
  $("#uptime-val").textContent=humanDur(h.uptime_seconds);
  $("#uptime-sub").textContent="Boot "+new Date(Date.now()-h.uptime_seconds*1000).toLocaleDateString();
}

async function refreshMarket(){
  const t0=performance.now();
  const m=await fetchJSON("/api/market-status");if(!m)return;
  recordLatency("market-status", performance.now()-t0);
  const c=$("#market-chip")||document.createElement("span");c.textContent="Market: "+m.status.toUpperCase().replace("_"," ");
  c.className="chip "+(m.status==="open"?"ok":m.status==="pre_open"?"warn":"");
  applyCadence(m.status === "open" || m.status === "pre_open");
}

async function refreshStrategy(){
  const s=await fetchJSON("/api/strategy");if(!s)return; window.__CAPITAL__ = Number(s.capital)||3750000;
  // 8o.3a: multi-symbol render + capital tier chip
  const symList=(s.symbols||[]).map(x=>`<span class="strat-sym">${x.key}</span><span class="strat-lot">${x.lot_size}L · max ${x.max_lots}</span>`).join("&nbsp;&nbsp;");
  const tierChip=s.capital_tier?`<span class="strat-tier">${s.capital_tier}</span>`:"";
  $("#strategy-detail").innerHTML=`<div>📊 ${symList||s.symbol||"--"}</div><div>💰 Rs ${(s.capital||0).toLocaleString("en-IN")} ${tierChip}</div><div>📏 z_e ${s.z_entry} · z_s ${s.z_stop} · w ${s.window}</div>`;
}

async function refreshTrades(){
  const d=await fetchJSON("/api/trades");if(!d)return;
  const livePnl=d.total_pnl||0;
  // Phase 9.8e B6: Top KPI is ALL-TIME (csv backtest + jsonl live + unrealized) from /api/risk
  let allTimePnl=livePnl;
  try {
    const r=await fetchJSON("/api/risk");
    if(r && typeof r.cumulative_pnl==="number") allTimePnl=r.cumulative_pnl;
  } catch(e){}
  const el=$("#total-pnl");el.textContent=fmtMoney(allTimePnl);
  el.className="kpi-value "+(allTimePnl>0?"positive":allTimePnl<0?"negative":"");
  $("#pnl-pct").textContent=fmtPct(allTimePnl/(window.__CAPITAL__||3750000));
  $("#trade-count").textContent=d.count;
  $("#win-rate").textContent="Win: "+fmtPct(d.win_rate);
  $("#trade-summary").textContent=`${d.count} trades · ${fmtMoney(livePnl)} · win ${fmtPct(d.win_rate)}`;
  renderTradeTable(d.trades||[]);
}

function renderTradeTable(trades){
  const filter=$("#trade-filter").value;
  const tbody=$("#trades-table tbody");tbody.innerHTML="";
  if(!trades.length){tbody.innerHTML='<tr><td colspan="11" style="text-align:center;color:var(--muted);padding:40px">No trades yet -- bot is watching the market 👀</td></tr>';return;}
  let cum=0;const cums=trades.map(t=>{cum+=Number(t.pnl||0);return cum;});
  trades.slice().reverse().forEach((t,idxRev)=>{
    const i=trades.length-1-idxRev;
    if(filter!=="all"&&(t.reason||"")!==filter)return;
    const p=Number(t.pnl||0),c=cums[i];
    const tr=document.createElement("tr");
    tr.innerHTML=`<td>${i+1}</td><td>${(t.entry_ts||"").slice(0,16).replace("T"," ")||"--"}</td><td>${(t.exit_ts||"").slice(0,16).replace("T"," ")||"--"}</td><td class="side-${(t.side||"").toLowerCase()}">${t.side||"--"}</td><td>${t.qty||"--"}</td><td>${t.entry!=null?Number(t.entry).toFixed(1):"--"}</td><td>${t.exit!=null?Number(t.exit).toFixed(1):"--"}</td><td>${t.bars_held||"--"}</td><td class="${p>0?"pos":p<0?"neg":""}">${fmtMoney(p)}</td><td class="${c>0?"pos":c<0?"neg":""}">${fmtMoney(c)}</td><td><span class="reason-badge reason-${t.reason||"TIME"}">${t.reason||"--"}</span></td>`;
    tbody.appendChild(tr);
  });
}

async function refreshLog(){
  const fileSel = $("#log-file");
  const file = fileSel ? fileSel.value : "";
  const q = ($("#log-search") && $("#log-search").value) || "";
  const level = ($("#log-level") && $("#log-level").value) || "";
  const symbol = ($("#log-symbol") && $("#log-symbol").value) || "";
  const errOnly = $("#log-errors-only") && $("#log-errors-only").checked;
  const params = new URLSearchParams({n: "200"});
  if(file) params.set("file", file);
  if(q) params.set("q", q);
  if(level || errOnly) params.set("level", errOnly ? "ERROR" : level);
  if(symbol) params.set("symbol", symbol);
  const d = await fetchJSON("/api/log?" + params.toString());
  if(!d) return;
  const pre = $("#log-view");
  let lines = d.lines || [];
  pre.innerHTML = lines.map(l => {
    let cls = "log-info";
    if(/\[ERROR\]|\[CRITICAL\]|exception|traceback|failed/i.test(l)) cls = "log-err";
    else if(/\[WARN/i.test(l)) cls = "log-warn";
    else if(/heartbeat/i.test(l)) cls = "log-hb";
    return `<span class="${cls}">${escHtml(l)}</span>`;
  }).join("\n");
  if(d.source) $("#log-source").textContent = `${d.source} - ${d.filtered}/${d.total} lines`;
  const sticky = $("#log-sticky");
  if(sticky){
    const errs = d.sticky_errors || [];
    if(!errs.length){ sticky.style.display = "none"; sticky.innerHTML = ""; }
    else {
      sticky.style.display = "block";
      sticky.innerHTML = `<div class="log-sticky-hdr">Recent errors (${errs.length})</div>` + errs.map(l => `<div class="log-sticky-line">${escHtml(l)}</div>`).join("");
    }
  }
  const dl = $("#log-download");
  if(dl && d.source) dl.href = "/api/logs/download?file=" + encodeURIComponent(d.source);
  if($("#log-autoscroll").checked) pre.scrollTop = pre.scrollHeight;
}

async function initLogControls(){
  const sel = $("#log-file");
  if(sel){
    const d = await fetchJSON("/api/logs/list");
    if(d && d.files){
      sel.innerHTML = '<option value="">Latest</option>' + d.files.map(f => `<option value="${escHtml(f.name)}">${escHtml(f.name)} (${(f.size/1024).toFixed(1)} KB)</option>`).join("");
    }
    sel.onchange = () => refreshLog();
  }
  const q = $("#log-search");
  if(q){
    let t = null;
    q.oninput = () => { clearTimeout(t); t = setTimeout(refreshLog, 250); };
  }
  const lev = $("#log-level"); if(lev) lev.onchange = () => refreshLog();
  const sym = $("#log-symbol"); if(sym) sym.onchange = () => refreshLog();
  const cp = $("#log-copy");
  if(cp) cp.onclick = () => {
    const txt = $("#log-view").innerText;
    navigator.clipboard.writeText(txt).then(() => {
      cp.textContent = "Copied";
      setTimeout(() => { cp.textContent = "Copy"; }, 1500);
    });
  };
}

async function refreshMetrics(){
  const m = await fetchJSON("/api/metrics");
  if (!m) return;
  const el = document.getElementById("metrics-view");
  if (!el) return;
  const fmt = (v, kind) => {
    if (v == null || isNaN(Number(v))) return "--";
    const n = Number(v);
    if (kind === "pct")   return (n >= 0 ? "+" : "") + n.toFixed(2) + "%";
    if (kind === "money") return "Rs " + Math.round(n).toLocaleString("en-IN");
    if (kind === "x")     return n.toFixed(2) + "x";
    if (kind === "ratio") return n.toFixed(2);
    if (kind === "wr")    return (n * 100).toFixed(1) + "%";
    return String(n);
  };
  const grade = (val, passT, warnT, higherIsBetter) => {
    if (val == null || isNaN(Number(val))) return "neutral";
    const v = Number(val);
    const hib = higherIsBetter !== false;
    if (hib) {
      if (v >= passT) return "pass";
      if (v >= warnT) return "warn";
      return "fail";
    }
    if (v <= passT) return "pass";
    if (v <= warnT) return "warn";
    return "fail";
  };
  const cards = [
    { label: "SHARPE",        value: fmt(m.sharpe,           "ratio"), target: "Target >= 3.0",     grade: grade(m.sharpe,           3.0,  1.5,  true),  sub: "risk-adjusted return" },
    { label: "SORTINO",       value: fmt(m.sortino,          "ratio"), target: "Target >= 4.0",     grade: grade(m.sortino,          4.0,  2.0,  true),  sub: "downside-adjusted" },
    { label: "PROFIT FACTOR", value: fmt(m.profit_factor,    "x"),     target: "Target >= 1.5",     grade: grade(m.profit_factor,    1.5,  1.2,  true),  sub: "gross win / gross loss" },
    { label: "WIN RATE",      value: fmt(m.win_rate,         "wr"),    target: "Benchmark 60%",     grade: grade(m.win_rate,         0.60, 0.50, true),  sub: (m.trades||0) + " trades" },
    { label: "MAX DRAWDOWN",  value: fmt(m.max_drawdown_pct, "pct"),   target: "ELITE ceiling -10%", grade: grade(m.max_drawdown_pct, -5, -10, true), sub: "peak to trough" },
    { label: "TOTAL RETURN",  value: fmt(m.return_pct,       "pct"),   target: (m.trading_days||0) + " trading days", grade: grade(m.return_pct, 0, -2, true), sub: fmt(m.total_pnl, "money") },
  ];
  el.className = "metric-cards-grid";
  el.innerHTML = cards.map(c => (
    '<div class="metric-card metric-' + c.grade + '">' +
      '<div class="metric-label">' + c.label + '</div>' +
      '<div class="metric-value">' + c.value + '</div>' +
      '<div class="metric-target">' + c.target + '</div>' +
      '<div class="metric-foot">' +
        '<span class="metric-pill metric-pill-' + c.grade + '">' + c.grade.toUpperCase() + '</span>' +
        '<span class="metric-sub">' + c.sub + '</span>' +
      '</div>' +
    '</div>'
  )).join("");
}

function chartCommon(dark){const grid=dark?"rgba(139,148,158,0.08)":"rgba(100,116,139,0.08)";const axis=dark?"#8b94a8":"#64748b";return{grid,axis};}

async function refreshEquity(){
  const d=await fetchJSON("/api/equity");if(!d||!d.rows||!d.rows.length)return;
  const labels=d.rows.map(r=>r.date||r.ts||"");
  const equity=d.rows.map(r=>Number(r.equity||0));
  const cap=(window.__CAPITAL__||3750000),baseline=new Array(equity.length).fill(cap);
  const minV=Math.min(...equity,cap),maxV=Math.max(...equity,cap),pad=(maxV-minV)*.15||5000;
  const finalEq=equity[equity.length-1],pnl=finalEq-cap;
  ($("#equity-range")||document.createElement("span")).textContent=`${labels[0]} → ${labels[labels.length-1]}  ·  Final ₹${Math.round(finalEq).toLocaleString("en-IN")} (${pnl>=0?"+":""}${(pnl/cap*100).toFixed(2)}%)`;
  if(equityChart)equityChart.destroy();
  const dark=document.documentElement.getAttribute("data-theme")!=="light";const{grid,axis}=chartCommon(dark);
  equityChart=new Chart(($("#equity-chart")||document.createElement("canvas")).getContext("2d"),{type:"line",data:{labels,datasets:[{label:"Equity",data:equity,borderColor:"rgba(99,102,241,1)",backgroundColor:"rgba(99,102,241,0.12)",fill:true,stepped:"before",pointRadius:0,pointHoverRadius:5,borderWidth:2},{label:"Capital (₹150k)",data:baseline,borderColor:"rgba(139,148,158,0.55)",borderDash:[6,6],pointRadius:0,borderWidth:1.2,fill:false}]},options:{responsive:true,maintainAspectRatio:false,animation:{duration:400},interaction:{intersect:false,mode:"index"},plugins:{legend:{position:"top",align:"end",labels:{color:axis,font:{size:11},usePointStyle:true,boxWidth:8}},tooltip:{backgroundColor:dark?"rgba(18,24,38,.95)":"rgba(255,255,255,.98)",titleColor:dark?"#e6edf3":"#0f172a",bodyColor:dark?"#e6edf3":"#0f172a",borderColor:dark?"#1f2937":"#e2e8f0",borderWidth:1,padding:10,callbacks:{label:c=>c.dataset.label+": ₹"+Math.round(c.parsed.y).toLocaleString("en-IN"),afterBody:it=>{if(it.length&&it[0].dataset.label.startsWith("Equity")){const v=it[0].parsed.y,diff=v-cap;return["","P&L: "+(diff>=0?"+":"")+"₹"+Math.round(diff).toLocaleString("en-IN")+" ("+(diff/cap*100).toFixed(2)+"%)"];}return[];}}}},scales:{x:{ticks:{maxTicksLimit:8,color:axis,font:{size:10}},grid:{color:grid}},y:{min:Math.max(0,minV-pad),max:maxV+pad,ticks:{color:axis,font:{size:10},callback:v=>"₹"+(v/1000).toFixed(0)+"k"},grid:{color:grid}}}}});
}

async function refreshDailyPnl(){
  const d=await fetchJSON("/api/daily-pnl");if(!d||!d.rows||!d.rows.length)return;
  const labels=d.rows.map(r=>r.date),data=d.rows.map(r=>r.pnl);
  const colors=data.map(v=>v>=0?"rgba(16,185,129,0.8)":"rgba(239,68,68,0.8)");
  if(pnlChart)pnlChart.destroy();
  const dark=document.documentElement.getAttribute("data-theme")!=="light";const{grid,axis}=chartCommon(dark);
  pnlChart=new Chart($("#daily-pnl-chart").getContext("2d"),{type:"bar",data:{labels,datasets:[{label:"Daily P&L",data,backgroundColor:colors,borderRadius:3}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>"₹"+Math.round(c.parsed.y).toLocaleString("en-IN")}}},scales:{x:{ticks:{maxTicksLimit:8,color:axis,font:{size:10}},grid:{color:grid}},y:{ticks:{color:axis,font:{size:10},callback:v=>"₹"+(v/1000).toFixed(1)+"k"},grid:{color:grid}}}}});
}

async function refreshDrawdown(){
  const d=await fetchJSON("/api/drawdown");if(!d||!d.rows||!d.rows.length)return;
  const labels=d.rows.map(r=>r.date),dd=d.rows.map(r=>r.dd_pct);
  const cur=dd[dd.length-1],mx=Math.min(...dd);
  $("#current-dd").textContent=`Current: ${cur.toFixed(2)}%  ·  Max: ${mx.toFixed(2)}%`;
  if(ddChart)ddChart.destroy();
  const dark=document.documentElement.getAttribute("data-theme")!=="light";const{grid,axis}=chartCommon(dark);
  ddChart=new Chart(($("#drawdown-chart")||document.createElement("canvas")).getContext("2d"),{type:"line",data:{labels,datasets:[{label:"Drawdown %",data:dd,borderColor:"rgba(239,68,68,1)",backgroundColor:"rgba(239,68,68,0.15)",fill:true,pointRadius:0,borderWidth:1.5,stepped:"before"}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>c.parsed.y.toFixed(2)+"%"}}},scales:{x:{ticks:{maxTicksLimit:8,color:axis,font:{size:10}},grid:{color:grid}},y:{max:0,ticks:{color:axis,font:{size:10},callback:v=>v.toFixed(1)+"%"},grid:{color:grid}}}}});
}

async function refreshPortfolio(){
  // Phase 9.8f.62: real bot status + mode badges from /api/status
  const [p, s] = await Promise.all([
    fetchJSON("/api/portfolio"),
    fetchJSON("/api/status").catch(()=>null)
  ]);
  if(!p) return;
  const el = $("#portfolio-view");
  if(!p.ok){ el.innerHTML = `<div class="muted">Angel: ${p.error||"--"}</div>`; return; }
  const rms = p.rms || null;
  const hasReal = rms && Object.keys(rms).some(k => Number(rms[k]||0) !== 0);
  if(!hasReal){
    const st = s || {};
    const live = !!st.live_mode;
    const bs = st.bot_state || "unknown";
    const ts = st.timer_state || "unknown";
    const hb_age = (st.heartbeat_age_s != null) ? Number(st.heartbeat_age_s) : null;
    const hb_count = st.heartbeat_count_today || 0;
    const next_us = st.next_run_usec || 0;
    const mkt = st.market_status || "unknown";
    const modeLbl = live ? "LIVE MODE" : "PAPER MODE";
    const modeStyle = live
      ? "background:rgba(34,197,94,.15);color:#22c55e;border:1px solid rgba(34,197,94,.4)"
      : "background:rgba(245,158,11,.15);color:#f59e0b;border:1px solid rgba(245,158,11,.4)";
    let sessLbl, sessStyle;
    if(bs !== "active"){
      sessLbl = "BOT DEAD";
      sessStyle = "background:rgba(239,68,68,.15);color:#ef4444;border:1px solid rgba(239,68,68,.4)";
    } else if(hb_age != null && hb_age < 120){
      sessLbl = "BOT ACTIVE";
      sessStyle = "background:rgba(34,197,94,.15);color:#22c55e;border:1px solid rgba(34,197,94,.4)";
    } else if(ts === "active" || (st.bot_status && /ARM/i.test(st.bot_status))){
      sessLbl = "BOT ARMED";
      sessStyle = "background:rgba(59,130,246,.15);color:#3b82f6;border:1px solid rgba(59,130,246,.4)";
    } else {
      sessLbl = "BOT IDLE";
      sessStyle = "background:rgba(156,163,175,.15);color:#9ca3af;border:1px solid rgba(156,163,175,.4)";
    }
    let nextStr = "--";
    if(next_us > 0){
      try {
        const d = new Date(next_us/1000);
        nextStr = d.toLocaleString("en-IN", {weekday:"short", day:"2-digit", month:"short", hour:"2-digit", minute:"2-digit", hour12:false, timeZone:"Asia/Kolkata"}) + " IST";
      } catch(e){}
    }
    let hbStr = "--";
    if(hb_age != null){
      if(hb_age < 60) hbStr = Math.round(hb_age) + "s ago";
      else if(hb_age < 3600) hbStr = Math.round(hb_age/60) + "m ago";
      else hbStr = Math.round(hb_age/3600) + "h ago";
    }
    const cap = Number(window.CAPITAL || 3750000);
    const capStr = "Rs " + cap.toLocaleString("en-IN");
    const badgeBase = "padding:3px 10px;border-radius:3px;font-family:JetBrains Mono,Consolas,monospace;font-size:11px;font-weight:700;letter-spacing:.5px;display:inline-block";
    el.innerHTML = `<div class="pf-paper">
      <div class="pf-paper-badges" style="display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap"><span style="${badgeBase};${modeStyle}">${modeLbl}</span><span style="${badgeBase};${sessStyle}">${sessLbl}</span></div>
      <div class="pf-paper-row"><span class="mk">Simulated capital</span><span class="pf-val">${capStr}</span></div>
      <div class="pf-paper-row"><span class="mk">Broker positions</span><span class="pf-muted">${live ? "--" : "none (paper)"}</span></div>
      <div class="pf-paper-row"><span class="mk">Next wakeup</span><span class="pf-val">${nextStr}</span></div>
      <div class="pf-paper-row"><span class="mk">Last heartbeat</span><span class="pf-val">${hbStr}</span></div>
      <div class="pf-paper-row"><span class="mk">Heartbeats today</span><span class="pf-val">${hb_count}</span></div>
      <div class="pf-paper-row"><span class="mk">Market</span><span class="pf-val">${mkt}</span></div>
      <div class="pf-paper-hint">${live ? "Broker balance refreshes as the bot pushes live state." : "Live broker data will populate when LIVE=true and the bot is logged in."}</div>
    </div>`;
  } else {
    const f = k => fmtMoney(Number(rms[k]||0));
    el.innerHTML = `<div class="metrics-grid"><div><span class="mk">Available</span><span>${f("availablecash")}</span></div><div><span class="mk">Net balance</span><span>${f("net")}</span></div><div><span class="mk">Margin used</span><span>${f("utiliseddebits")}</span></div><div><span class="mk">Collateral</span><span>${f("collateral")}</span></div></div>`;
  }
  $("#portfolio-ts").textContent = new Date().toLocaleTimeString();
}

async function refreshFast(){await Promise.all([refreshStatus(),refreshHealth(),refreshMarket(),refreshTrades(),refreshLog()]);$("#last-update").textContent=new Date().toLocaleTimeString();}
async function refreshSlow(){await Promise.all([refreshMetrics(),refreshEquity(),refreshDailyPnl(),refreshDrawdown(),refreshStrategy(),refreshPortfolio(),refreshHeatmap()]);}

function initTheme(){
  const saved=localStorage.getItem("theme")||"dark";
  document.documentElement.setAttribute("data-theme",saved);
  ($("#theme-toggle")||document.createElement("span")).textContent=saved==="dark"?"☀️":"🌙";
  ($("#theme-toggle")||document.createElement("span")).onclick=()=>{const cur=document.documentElement.getAttribute("data-theme");const nx=cur==="dark"?"light":"dark";document.documentElement.setAttribute("data-theme",nx);localStorage.setItem("theme",nx);($("#theme-toggle")||document.createElement("span")).textContent=nx==="dark"?"☀️":"🌙";refreshEquity();refreshDailyPnl();refreshDrawdown();};
}
function initFilters(){$("#trade-filter").onchange=()=>refreshTrades();$("#log-errors-only").onchange=()=>refreshLog();}


// ===== p98g.73 cascade-stopper =====
(function(){
function safeTxt(s,v){var e=typeof s==='string'?document.querySelector(s):s;if(e){try{e.textContent=v;}catch(_){}}}
function safeHTML(s,v){var e=typeof s==='string'?document.querySelector(s):s;if(e){try{e.innerHTML=v;}catch(_){}}}
function safeClass(s,v){var e=typeof s==='string'?document.querySelector(s):s;if(e){try{e.className=v;}catch(_){}}}
window.setTxt=safeTxt;window.setHTML=safeHTML;window.setClass=safeClass;
var A=['refreshMarket','refreshHealth','refreshStrategy','refreshTrades','refreshEquity','refreshDailyPnl','refreshDrawdown','refreshPortfolio','refreshMetrics','refreshHeatmap','refreshStatus','refreshLog','refreshFast','refreshSlow','refreshChallenge'];
A.forEach(function(n){if(typeof window[n]==='function'){var o=window[n];window[n]=async function(){try{return await o.apply(this,arguments);}catch(e){var k=n+':'+(e&&e.message||'');window.__p98g73_s=window.__p98g73_s||{};if(!window.__p98g73_s[k]){console.warn('p98g.73 silenced '+n+':',e&&e.message);window.__p98g73_s[k]=1;}}};}});
var S=['initFilters','initLogControls'];
S.forEach(function(n){if(typeof window[n]==='function'){var o=window[n];window[n]=function(){try{return o.apply(this,arguments);}catch(e){console.warn('p98g.73 silenced '+n+':',e&&e.message);}};}});
})();
try{initTheme()}catch(e){console.warn("initTheme failed:",e)};initFilters();initLogControls();refreshFast();refreshSlow();
setInterval(refreshFast,5000);setInterval(refreshSlow,60000);

// ===== v6 -- chart subtitles + info tooltips =====
(function(){
  const labels = {
    "Equity Curve":     { sub: "Backtest replay · 2026-02-25 → 2026-04-23 · 37 trading days · base ₹1,50,000 (academic notional) · live capital ₹37,50,000 scales same return %", info: "Stepped line = daily equity. Dotted = starting capital. Rising line = strategy is profitable over time." },
    "Daily P&L":        { sub: "Per-day realised profit/loss from closed trades",                    info: "Green bar = profitable day · Red bar = losing day · No bar = no trades that day. Height = ₹ amount." },
    "Drawdown":         { sub: "How far equity fell from its running peak (risk view)",              info: "0% = at all-time high. -3.65% = worst peak-to-trough loss. Small drawdown = stable strategy." },
    "Backtest Metrics": { sub: "Risk/return stats from 121-day historical simulation",               info: "Sharpe 3.25 = excellent risk-adj return. PF 2.35 = earned ₹2.35 for every ₹1 lost. 62.5% win rate." },
    "Live Portfolio":   { sub: "Real-time Angel broker balance (paper mode = ₹0 used)",              info: "Available = deposit. Margin Used = locked for open positions. Paper mode uses zero margin." },
    "Trade History":    { sub: "All trades · backtest + paper · most recent first",                         info: "Empty = no signals fired yet today. Bot waits for z-score ≥ |1.5| after 40-bar warm-up (~09:55 AM)." },
    "Live Bot Log":     { sub: "Tail of the bot's runtime log (heartbeats + trades + errors)",       info: "Heartbeats every 30s = bot is alive. Errors shown in red. Toggle 'Errors only' to filter noise." },
  };
  function enhance(){
    document.querySelectorAll(".panel-head, .panel h2, .panel h3").forEach(h => {
      const title = (h.textContent || "").trim().split("\n")[0].trim();
      const cfg = labels[title];
      if (!cfg || h.dataset.enhanced) return;
      h.dataset.enhanced = "1";
      // subtitle
      const sub = document.createElement("div");
      sub.className = "panel-subtitle";
      sub.textContent = cfg.sub;
      // info badge
      const info = document.createElement("span");
      info.className = "info-badge";
      info.textContent = "ⓘ";
      info.title = cfg.info;
      h.appendChild(info);
      h.parentNode.insertBefore(sub, h.nextSibling);
    });
  }
  // run on load + every refresh
  document.addEventListener("DOMContentLoaded", enhance);
  setTimeout(enhance, 500);
  setInterval(enhance, 3000);
})();

// ===== LIVE_PANELS_v1 =====
(function(){
  function injectDOM(){
    if (document.getElementById("live-strip")) return;
    const afterKpi = document.querySelector(".kpi-grid");
    if (!afterKpi) return;
    const html = `
      <section id="live-strip" class="live-strip">
        <div class="live-card main waiting" id="lc-ltp">
          <div class="lbl" id="ltp-label">BANKNIFTY FUT · LTP</div>
          <div class="ltp-val" id="ltp-val">--</div>
          <div class="sub" id="ltp-sub">waiting for bot...</div>
        </div>
        <div class="live-card waiting" id="lc-state">
          <div class="lbl">Bot State</div>
          <div class="val" id="state-val"><span class="state-badge idle"><span class="dot"></span>IDLE</span></div>
          <div class="sub" id="state-sub">--</div>
        </div>
        <div class="live-card waiting" id="lc-zscore">
          <div class="lbl">Z-Score (now)</div>
          <div class="val" id="z-val">--</div>
          <div class="sub">entry ±1.5 · stop ±3.5</div>
        </div>
        <div class="live-card waiting" id="lc-candles">
          <div class="lbl">Candles Today</div>
          <div class="val" id="cn-val">--</div>
          <div class="sub">of 375 · warmup 40</div>
        </div>
        <div class="live-card waiting" id="lc-nextcheck">
          <div class="lbl">Next Check</div>
          <div class="val" id="nc-val">--</div>
          <div class="sub">30s loop</div>
        </div>
      </section>
      <section class="panel" id="panel-zgauge">
        <div class="panel-head"><h3>Z-Score Gauge · Live</h3></div>
        <div class="z-gauge">
          <div class="band" style="left:12.5%">-3.5σ</div>
          <div class="band" style="left:31.25%">-1.5σ</div>
          <div class="band mid" style="left:50%">0</div>
          <div class="band" style="left:68.75%">+1.5σ</div>
          <div class="band" style="left:87.5%">+3.5σ</div>
          <div class="marker" id="z-marker" style="left:50%"></div>
        </div>
        <div class="z-legend"><span>-4</span><span>-2</span><span>0</span><span>+2</span><span>+4</span></div>
      </section>
      <section class="grid-2">
        <div class="panel" id="panel-intraday">
          <div class="panel-head"><h3>Intraday · 1-min Close</h3></div>
          <div class="chart-wrap"><canvas id="chart-intraday"></canvas></div>
        </div>
        <div class="panel" id="panel-depth">
          <div class="panel-head"><h3>Market Depth · Level 2</h3></div>
          <div class="depth-grid">
            <div class="depth-col bids">
              <div class="head"><span>BID</span><span>QTY</span><span>ORD</span></div>
              <div id="depth-bids"><div class="pos-empty">--</div></div>
            </div>
            <div class="depth-col asks">
              <div class="head"><span>ASK</span><span>QTY</span><span>ORD</span></div>
              <div id="depth-asks"><div class="pos-empty">--</div></div>
            </div>
          </div>
        </div>
      </section>
      <section class="panel" id="panel-position">
        <div class="panel-head"><h3>Current Position · Live</h3></div>
        <div id="pos-body"><div class="pos-empty">No open position · bot is watching the market 👀</div></div>
      </section>`;
    const wrap = document.createElement("div");
    wrap.innerHTML = html;
    const nodes = Array.from(wrap.children);
    let anchor = afterKpi;
    nodes.forEach(n => { anchor.parentNode.insertBefore(n, anchor.nextSibling); anchor = n; });
  }

  let intradayChart = null;
  function renderIntraday(candles){
    const canvas = document.getElementById("chart-intraday");
    if (!canvas || !candles.length) return;
    const labels = candles.map(c => c[0]);
    const closes = candles.map(c => Number(c[4]));
    if (intradayChart) { intradayChart.data.labels=labels; intradayChart.data.datasets[0].data=closes; intradayChart.update("none"); return; }
    intradayChart = new Chart(canvas, {
      type: "line",
      data: { labels, datasets: [{ label:"Close", data:closes, borderColor:"#6366f1",
        backgroundColor:"rgba(99,102,241,0.12)", fill:true, tension:0, pointRadius:0, borderWidth:2 }] },
      options: { plugins:{legend:{display:false}},
        scales:{ x:{ticks:{maxTicksLimit:8}}, y:{ticks:{callback:v=>"₹"+Number(v).toLocaleString("en-IN")}} } }
    });
  }

  function renderDepth(side, rows){
    const el = document.getElementById("depth-"+side);
    if (!el) return;
    if (!rows || !rows.length) { el.innerHTML = '<div class="pos-empty">--</div>'; return; }
    const maxQ = Math.max(...rows.map(r => Number(r.qty||r.quantity||0)), 1);
    el.innerHTML = rows.slice(0,5).map(r => {
      const p = Number(r.price ?? r.Price ?? 0);
      const q = Number(r.qty ?? r.quantity ?? 0);
      const o = r.orders ?? r.Orders ?? r.num_orders ?? "-";
      const pct = Math.round((q/maxQ)*100);
      return `<div class="row"><div class="bar" style="width:${pct}%"></div><span>${p.toFixed(2)}</span><span>${q}</span><span>${o}</span></div>`;
    }).join("");
  }

  function renderPosition(pos){
    const el = document.getElementById("pos-body");
    if (!el) return;
    if (!pos) { el.innerHTML = '<div class="pos-empty">No open position · bot is watching the market 👀</div>'; return; }
    const pnl = Number(pos.unrealized_pnl || 0);
    const col = pnl >= 0 ? "#22c55e" : "#ef4444";
    const sign = pnl >= 0 ? "+" : "−";
    el.innerHTML = `<div class="pos-card">
      <div class="cell"><div class="lbl">Side</div><div class="val">${pos.side||"-"}</div></div>
      <div class="cell"><div class="lbl">Entry</div><div class="val">₹${Number(pos.entry||0).toFixed(2)}</div></div>
      <div class="cell"><div class="lbl">Qty</div><div class="val">${pos.qty||0}</div></div>
      <div class="cell"><div class="lbl">Unrealized P&L</div><div class="val" style="color:${col}">${sign}₹${Math.abs(pnl).toFixed(2)}</div></div>
      <div class="cell"><div class="lbl">Bars Held</div><div class="val">${pos.bars_held||0}</div></div>
      <div class="cell"><div class="lbl">Entry Time</div><div class="val" style="font-size:13px">${pos.entry_ts||"-"}</div></div>
      <div class="cell"><div class="lbl">Target</div><div class="val" style="font-size:13px">z=0</div></div>
      <div class="cell"><div class="lbl">Stop</div><div class="val" style="font-size:13px">z=±3.5</div></div>
    </div>`;
  }

  async function refreshLive(){
    try {
      // 8o.3b: per-symbol routing
      try{if(["FNF",null,""].indexOf(localStorage.getItem("ou_mrs_active_symbol"))>=0)localStorage.setItem("ou_mrs_active_symbol","BNF");}catch(_){} const __sym = (window.__ouActiveSymbol || localStorage.getItem("ou_mrs_active_symbol") || "BNF");
      const r = await fetch("/api/live/state?symbol=" + encodeURIComponent(__sym), { credentials:"same-origin" });
      if (r.status === 401 || r.status === 303) return;
      const d = await r.json();
      if (!d.ok || d.stale) {
        document.querySelectorAll(".live-card").forEach(c => c.classList.add("waiting"));
        const sub = document.getElementById("ltp-sub");
        if (sub) sub.textContent = d.reason === "waiting_for_bot"
          ? "⏳ add live_hook.tick() to ou_mrs.py + restart"
          : `stale (${d.age_sec||'?'}s old)`;
        return;
      }
      document.querySelectorAll(".live-card").forEach(c => c.classList.remove("waiting"));
      if (d.ltp != null) {
        document.getElementById("ltp-val").textContent = "₹" + Number(d.ltp).toLocaleString("en-IN",{minimumFractionDigits:2,maximumFractionDigits:2}); const _lbl_p98o = document.getElementById("ltp-label"); if (_lbl_p98o) _lbl_p98o.textContent = ({BNF:"BANKNIFTY",NF:"NIFTY",MCN:"MIDCPNIFTY"}[__sym]||__sym) + " FUT · LTP";
        if (d.ohlc_today) {
          const o = d.ohlc_today.o || d.ltp;
          const chg = d.ltp - o;
          const pct = o ? (chg/o*100) : 0;
          document.getElementById("ltp-sub").textContent = `${chg>=0?"▲":"▼"} ${Math.abs(chg).toFixed(2)} (${pct.toFixed(2)}%) · O ${(d.ohlc_today.o||0).toFixed(0)} H ${(d.ohlc_today.h||0).toFixed(0)} L ${(d.ohlc_today.l||0).toFixed(0)}`;
          document.getElementById("lc-ltp").classList.toggle("up", chg>=0);
          document.getElementById("lc-ltp").classList.toggle("down", chg<0);
        }
      }
      const sv = document.getElementById("state-val");
      if (sv) sv.innerHTML = `<span class="state-badge ${d.state||'idle'}"><span class="dot"></span>${(d.state||'IDLE').toUpperCase().replace("_"," ")}</span>`;
      const ss = document.getElementById("state-sub");
      if (ss) ss.textContent = d.state_reason || "--";
      if (d.z != null) {
        document.getElementById("z-val").textContent = (d.z>=0?"+":"") + Number(d.z).toFixed(3) + "σ";
        const z = Math.max(-4, Math.min(4, Number(d.z)));
        const left = ((z+4)/8) * 100;
        const m = document.getElementById("z-marker");
        if (m) m.style.left = left + "%";
      }
      if (d.candles_count != null) document.getElementById("cn-val").textContent = d.candles_count;
      if (d.next_check_in_sec != null) document.getElementById("nc-val").textContent = d.next_check_in_sec + "s";
      if (d.intraday_candles && d.intraday_candles.length) renderIntraday(d.intraday_candles);
      if (d.depth) { renderDepth("bids", d.depth.bids || []); renderDepth("asks", d.depth.asks || []); }
      renderPosition(d.position);
      // 8o.3b: lite-mode notice when non-primary symbol is active
      const __isLite = !!d.is_lite;
      const __notice = document.getElementById("deep-dive-notice");
      if (__notice) {
        __notice.textContent = __isLite ? ("Deep-dive (z · intraday · depth) is primary-symbol only. Showing lite state for " + (d.active_symbol||"--") + ".") : "";
        __notice.classList.toggle("visible", __isLite);
      }
      document.body.classList.toggle("lite-symbol", __isLite);
    } catch(e) {}
  }

  // 8o.3b: symbol-card click-to-activate hero focus tabs
  function initSymbolTabs(){
    const stored = localStorage.getItem("ou_mrs_active_symbol") || "BNF";
    window.__ouActiveSymbol = stored;
    function applyActive(){
      document.querySelectorAll(".symbol-card").forEach(c => {
        const sym = (c.id||"").replace("card-","");
        c.classList.toggle("active", sym === window.__ouActiveSymbol);
      });
    }
    document.querySelectorAll(".symbol-card").forEach(c => {
      c.style.cursor = "pointer";
      c.addEventListener("click", () => {
        const sym = (c.id||"").replace("card-","");
        if (!sym) return;
        window.__ouActiveSymbol = sym;
        localStorage.setItem("ou_mrs_active_symbol", sym);
        applyActive();
        refreshLive();
      });
    });
    applyActive();
  }
  function boot(){ injectDOM(); initSymbolTabs(); refreshLive(); setInterval(refreshLive, 5000); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();

// ===== MARKET_HERO_v1 -- prop-firm closed-mode hero with live countdown =====
(function(){
  const IST_OFFSET_MS = 5.5 * 3600 * 1000;
  function nowIST(){ return new Date(Date.now() + IST_OFFSET_MS); }
  function nextOpenIST(){
    const ist = nowIST();
    const target = new Date(ist);
    target.setUTCHours(9, 15, 0, 0);
    if (target <= ist) target.setUTCDate(target.getUTCDate() + 1);
    while (target.getUTCDay() === 0 || target.getUTCDay() === 6) {
      target.setUTCDate(target.getUTCDate() + 1);
    }
    return target;
  }
  function fmtCountdown(ms){
    if (ms <= 0) return "OPENING NOW";
    const s = Math.floor(ms/1000);
    const h = Math.floor(s/3600);
    const m = Math.floor((s%3600)/60);
    const sec = s%60;
    if (h >= 24) { const d = Math.floor(h/24); return d+"d "+(h%24)+"h "+m+"m"; }
    return String(h).padStart(2,"0")+":"+String(m).padStart(2,"0")+":"+String(sec).padStart(2,"0");
  }
  function fmtResume(target){
    const days = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
    return "Reopens "+days[target.getUTCDay()]+" 9:15 AM IST";
  }
  let countdownTimer = null;
  let cachedTarget = null;
  function tickCountdown(){
    if (!cachedTarget) return;
    const ms = cachedTarget - nowIST();
    const cd = document.getElementById("mh-countdown");
    if (cd) cd.textContent = fmtCountdown(ms);
    if (ms <= 0) cachedTarget = nextOpenIST();
  }
  function applyClosedMode(isClosed){
    document.body.classList.toggle("market-closed", isClosed);
    const hero = document.getElementById("market-hero");
    if (!hero) return;
    if (isClosed) {
      hero.hidden = false;
      cachedTarget = nextOpenIST();
      const r = document.getElementById("mh-resume");
      if (r) r.textContent = fmtResume(cachedTarget);
      tickCountdown();
      if (!countdownTimer) countdownTimer = setInterval(tickCountdown, 1000);
      const botVal = document.getElementById("bot-status");
      if (botVal && botVal.textContent.trim() === "INACTIVE") {
        botVal.textContent = "RESTING";
        botVal.style.color = "#60a5fa";
      }
      const botSub = document.getElementById("bot-sub");
      if (botSub) botSub.textContent = "Auto-resume at open";
    } else {
      hero.hidden = true;
      cachedTarget = null;
      if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null; }
    }
  }
  function check(){
    fetch("/api/market-status", {credentials:"same-origin"})
      .then(r => r.json())
      .then(ms => {
        if (!ms) return;
        const isClosed = ms.status !== "open" && ms.status !== "pre_open";
        applyClosedMode(isClosed);
      })
      .catch(()=>{});
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => setTimeout(check, 300));
  } else { setTimeout(check, 300); }
  setInterval(check, 30000);
})();

// Phase 8m.2: per-symbol hero cards with live sparklines (replaces 8g.6 refreshSymbols)
const SYM_NAMES_8M2 = { BNF: "BANKNIFTY", NF: "NIFTY", MCN: "MIDCPNIFTY" };
const SYM_COLORS_8M2 = { in_trade: "#3ce04f", cooldown: "#ff5566", warming_up: "#ffaa3c", idle: "#94a3b8", offline: "#475569" };
const SPARK_BUFFER = { BNF: [], NF: [], MCN: [] };
const SPARK_MAX = 60;

function pushSpark(sym, ltp) {
  if (ltp == null || isNaN(Number(ltp))) return;
  const arr = SPARK_BUFFER[sym];
  arr.push(Number(ltp));
  if (arr.length > SPARK_MAX) arr.shift();
}

function drawSparkline(canvas, samples, color) {
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth || canvas.parentElement.clientWidth - 40;
  const h = canvas.clientHeight || 50;
  if (canvas.width !== w*dpr) { canvas.width = w*dpr; canvas.height = h*dpr; }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  if (!samples || samples.length < 2) {
    ctx.fillStyle = "rgba(148,163,184,0.5)";
    ctx.font = "10px JetBrains Mono, monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(samples.length === 0 ? "awaiting first tick" : "warming up", w/2, h/2);
    return;
  }
  const min = Math.min.apply(null, samples);
  const max = Math.max.apply(null, samples);
  const range = (max - min) || 1;
  const stepX = w / (samples.length - 1);
  const yFor = v => h - ((v - min) / range) * (h - 8) - 4;
  ctx.beginPath();
  samples.forEach((v, i) => {
    const x = i * stepX;
    const y = yFor(v);
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.lineJoin = "round";
  ctx.stroke();
  ctx.lineTo(w, h);
  ctx.lineTo(0, h);
  ctx.closePath();
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, color + "33");
  grad.addColorStop(1, color + "00");
  ctx.fillStyle = grad;
  ctx.fill();
}

async function refreshSymbols() {
  const d = await fetchJSON("/api/symbols");
  if (!d || !d.symbols) return;
  for (const sym of ["BNF", "NF", "MCN"]) {
    const lower = sym.toLowerCase();
    const data = d.symbols[sym];
    const card = document.getElementById("card-" + sym);
    if (!card) continue;
    if (!data) {
      card.className = "symbol-card sc-offline";
      const se = document.getElementById(lower + "-state");
      if (se) se.textContent = "OFFLINE";
      const sp = document.getElementById("spark-" + sym);
      if (sp) drawSparkline(sp, SPARK_BUFFER[sym], SYM_COLORS_8M2.offline);
      continue;
    }
    const state = data.state || "idle";
    card.className = "symbol-card sc-" + state;
    const se = document.getElementById(lower + "-state");
    if (se) se.textContent = state.toUpperCase().replace(/_/g, " ");
    pushSpark(sym, data.ltp);
    const ltpEl = document.getElementById(lower + "-ltp");
    if (ltpEl) {
      ltpEl.textContent = (data.ltp != null)
        ? "Rs " + Number(data.ltp).toLocaleString("en-IN", {maximumFractionDigits: 2})
        : "--";
    }
    const chgEl = document.getElementById(lower + "-chg");
    if (chgEl) {
      const arr = SPARK_BUFFER[sym];
      if (arr.length >= 2) {
        const first = arr[0];
        const last = arr[arr.length - 1];
        const chg = last - first;
        const pct = first ? (chg / first * 100) : 0;
        const arrow = chg >= 0 ? "▲" : "▼";
        chgEl.textContent = arrow + " " + Math.abs(chg).toFixed(1) + " (" + pct.toFixed(2) + "%)";
        chgEl.className = "sc-chg " + (chg > 0 ? "pnl-pos" : chg < 0 ? "pnl-neg" : "pnl-flat");
      } else {
        chgEl.textContent = "--";
        chgEl.className = "sc-chg pnl-flat";
      }
    }
    const sp = document.getElementById("spark-" + sym);
    if (sp) drawSparkline(sp, SPARK_BUFFER[sym], SYM_COLORS_8M2[state] || SYM_COLORS_8M2.idle);
    const pe = document.getElementById(lower + "-pnl");
    if (pe) {
      const pnl = Number(data.pnl_today || 0);
      pe.textContent = (pnl >= 0 ? "+Rs " : "-Rs ") + Math.round(Math.abs(pnl)).toLocaleString("en-IN");
      pe.className = "sc-pnl " + (pnl > 0 ? "pnl-pos" : pnl < 0 ? "pnl-neg" : "pnl-flat");
    }
    const te = document.getElementById(lower + "-trades");
    if (te) te.textContent = String(data.trades_today || 0);
    const po = document.getElementById(lower + "-pos");
    if (po) {
      if (data.position) {
        const p = data.position;
        po.textContent = (p.side || "?") + " " + (p.qty || 0) + "L @ " + Math.round(p.entry || 0).toLocaleString("en-IN");
        po.className = "sc-meta-val sc-pos-active";
      } else {
        po.textContent = "flat";
        po.className = "sc-meta-val";
      }
    }
  }
}
setInterval(refreshSymbols, 5000);
refreshSymbols();

// Phase 9.8e B-CAL-1: compact money formatter for heatmap cells
function fmtCalCell(v){
  if(v == null || isNaN(v) || v === 0) return "";
  const abs = Math.abs(v);
  const sign = v < 0 ? "−" : "+";
  if(abs >= 100000) return sign + (abs/100000).toFixed(1) + "L";
  if(abs >= 1000)   return sign + Math.round(abs/1000) + "k";
  return sign + Math.round(abs);
}

// Phase 9.8e B-CAL-3: filter trade table to specific date
function filterTradesByDate(dateStr){
  const tt = document.getElementById("trades-table");
  if(tt) tt.scrollIntoView({behavior:"smooth", block:"start"});
  const rows = document.querySelectorAll("#trades-table tbody tr");
  let matched = 0;
  rows.forEach(r => {
    const cells = r.querySelectorAll("td");
    if(cells.length < 2){ r.style.display = "none"; return; }
    const ts = (cells[1].textContent || "").trim();
    const match = ts.startsWith(dateStr);
    r.style.display = match ? "" : "none";
    if(match) matched++;
  });
  let bn = document.getElementById("hm-trade-filter-banner");
  if(!bn){
    bn = document.createElement("div");
    bn.id = "hm-trade-filter-banner";
    bn.className = "trade-filter-banner";
    const tbl = document.getElementById("trades-table");
    if(tbl && tbl.parentNode) tbl.parentNode.insertBefore(bn, tbl);
  }
  bn.innerHTML = '<span>Showing <b>' + matched + '</b> trade' + (matched===1?'':'s') + ' for <b>' + dateStr + '</b></span>' +
                 '<button class="hm-clear-btn" onclick="clearTradeDateFilter()">× clear filter</button>';
  bn.style.display = "flex";
}

function clearTradeDateFilter(){
  document.querySelectorAll("#trades-table tbody tr").forEach(r => r.style.display = "");
  const bn = document.getElementById("hm-trade-filter-banner");
  if(bn) bn.style.display = "none";
}

// Phase 8q · Premium daily P&L heatmap (GitHub-contrib style)
async function refreshHeatmap(){
  const t0 = performance.now();
  const d = await fetchJSON("/api/daily-pnl"); if(!d) return;
  recordLatency("daily-pnl", performance.now() - t0);
  const rows = d.rows || [];
  const byDate = {}; rows.forEach(r => { byDate[r.date] = r; });
  const grid = document.getElementById("heatmap-grid"); if(!grid) return;
  grid.innerHTML = "";
  const today = new Date(); today.setHours(0,0,0,0);
  const days = 91;
  const start = new Date(today); start.setDate(today.getDate() - (days - 1));
  while(start.getDay() !== 0) start.setDate(start.getDate() - 1);
  let maxAbs = 0; rows.forEach(r => { const a = Math.abs(r.pnl||0); if(a>maxAbs) maxAbs = a; });
  if(maxAbs <= 0) maxAbs = 1;

  // Build month labels: scan each week for boundary
  const monthsRow = document.getElementById("hm-months");
  monthsRow.innerHTML = '<span></span>';  // empty corner
  const monthSpans = {}; const monthCounts = {};
  for(let w=0; w<13; w++){
    const wkStart = new Date(start); wkStart.setDate(start.getDate() + w*7);
    const monKey = wkStart.getFullYear() + "-" + wkStart.getMonth();
    if(!(monKey in monthSpans)){
      monthSpans[monKey] = { label: wkStart.toLocaleString("en-US", {month:"short"}).toUpperCase(), startWeek: w };
      monthCounts[monKey] = 1;
    } else { monthCounts[monKey]++; }
  }
  Object.values(monthSpans).forEach(m => {
    const sp = document.createElement("span");
    const cnt = monthCounts[Object.keys(monthSpans).find(k => monthSpans[k] === m)];
    sp.style.gridColumn = (m.startWeek + 2) + " / span " + cnt;
    sp.textContent = (cnt >= 2) ? m.label : "";
    monthsRow.appendChild(sp);
  });

  const cells = [];
  for(let w=0; w<13; w++){
    for(let dow=0; dow<7; dow++){
      const dt = new Date(start); dt.setDate(start.getDate() + w*7 + dow);
      const key = dt.toISOString().slice(0,10);
      const rec = byDate[key];
      const pnl = rec ? (rec.pnl||0) : null;
      const cell = document.createElement("div");
      cell.className = "heatmap-cell";
      cell.style.gridColumn = (w+1);
      cell.style.gridRow = (dow+1);
      if(dt > today){ cell.style.visibility = "hidden"; }
      else if(pnl == null || rec.trades === 0){ cell.classList.add("empty"); }
      else {
        const ratio = Math.abs(pnl) / maxAbs;
        const tier = ratio >= 0.75 ? 4 : ratio >= 0.45 ? 3 : ratio >= 0.18 ? 2 : 1;
        cell.classList.add(pnl >= 0 ? "win-"+tier : "loss-"+tier);
        cell.textContent = fmtCalCell(pnl);  // Phase 9.8e B-CAL-1
      }
      cell.dataset.date = key;
      cell.dataset.pnl = pnl != null ? pnl : "";
      cell.dataset.trades = rec ? rec.trades : 0;
      cell.dataset.wins = rec ? rec.wins : 0;
      cell.dataset.live = rec ? (rec.live||0) : 0;
      cell.dataset.bt = rec ? (rec.bt||0) : 0;
      // Phase 9.8e B-CAL-3: click cell -> filter trade table to that date
      if(pnl != null && rec && rec.trades > 0){
        cell.style.cursor = "pointer";
        cell.addEventListener("click", () => filterTradesByDate(key));
      }
      cells.push(cell);
      grid.appendChild(cell);
    }
  }

  // Stats
  const past = rows.filter(r => new Date(r.date) <= today);
  const winDays = past.filter(r => (r.pnl||0) > 0).length;
  const lossDays = past.filter(r => (r.pnl||0) < 0).length;
  const tradingDays = past.length;
  const totalPnl = past.reduce((s, r) => s + (r.pnl||0), 0);
  const avg = tradingDays ? totalPnl / tradingDays : 0;
  const liveTotal = past.reduce((s, r) => s + (r.live||0), 0);
  const btTotal = past.reduce((s, r) => s + (r.bt||0), 0);

  setText("hm-tdays", tradingDays);
  const _dates = past.map(r => r.date).filter(Boolean).sort();
  const _rangeStr = _dates.length ? (_dates[0].slice(5) + " to " + _dates[_dates.length-1].slice(5)) : "no data";
  const _liveTag = liveTotal > 0 ? " · " + liveTotal + " live" : "";
  setText("hm-tdays-sub", _rangeStr + _liveTag);
  setText("hm-winpct", tradingDays ? (winDays/tradingDays*100).toFixed(1) + "%" : "--");
  setText("hm-winpct-sub", winDays + "W / " + lossDays + "L");
  const avgEl = document.getElementById("hm-avg");
  if(avgEl){
    avgEl.textContent = (avg >= 0 ? "+" : "") + "Rs " + Math.round(avg).toLocaleString("en-IN");
    avgEl.className = "hm-stat-val " + (avg > 0 ? "pos" : avg < 0 ? "neg" : "");
  }
  if(past.length){
    const best = past.reduce((a,b) => (b.pnl||0) > (a.pnl||0) ? b : a);
    const worst = past.reduce((a,b) => (b.pnl||0) < (a.pnl||0) ? b : a);
    document.getElementById("hm-extremes").innerHTML =
      '<span style="color:var(--green)">+' + Math.round(best.pnl).toLocaleString("en-IN") + '</span> / <span style="color:var(--red)">' + Math.round(worst.pnl).toLocaleString("en-IN") + '</span>';
    setText("hm-extremes-sub", best.date.slice(5) + " · " + worst.date.slice(5));
  }
  // Streak
  const sorted = past.slice().sort((a,b) => a.date.localeCompare(b.date));
  let streak = 0; let streakSign = 0;
  for(let i = sorted.length - 1; i >= 0; i--){
    const p = sorted[i].pnl || 0;
    const sign = p > 0 ? 1 : p < 0 ? -1 : 0;
    if(sign === 0) continue;
    if(streak === 0){ streakSign = sign; streak = 1; }
    else if(sign === streakSign){ streak++; }
    else break;
  }
  const stEl = document.getElementById("hm-streak");
  if(stEl){
    if(streak === 0){ stEl.textContent = "--"; stEl.className = "hm-stat-val"; }
    else {
      stEl.textContent = (streakSign > 0 ? "+" : "−") + streak;
      stEl.className = "hm-stat-val " + (streakSign > 0 ? "pos" : "neg");
    }
  }
  setText("hm-streak-sub", streak === 0 ? "no streak" : (streak === 1 ? "1 day" : streak + " days"));

  // Phase 9.8e B-CAL-2: rich tooltip — day-of-week, win%, avg/trade, smart positioning
  const tip = document.getElementById("hm-tooltip");
  const _DOW = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
  const _MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  cells.forEach(cell => {
    cell.addEventListener("mouseenter", () => {
      const date = cell.dataset.date;
      const pnl = cell.dataset.pnl;
      const trades = parseInt(cell.dataset.trades)||0;
      const wins = parseInt(cell.dataset.wins)||0;
      const losses = Math.max(0, trades - wins);
      const live = parseInt(cell.dataset.live)||0;
      const bt = parseInt(cell.dataset.bt)||0;
      let prettyDate = date;
      try {
        const dt = new Date(date + "T00:00:00");
        prettyDate = _DOW[dt.getDay()] + " · " + dt.getDate() + " " + _MON[dt.getMonth()] + " " + dt.getFullYear();
      } catch(e){}
      let html = '<div class="ht-date">' + prettyDate + '</div>';
      if(pnl === "" || trades === 0){
        html += '<div class="ht-empty">no trades this day</div>';
      } else {
        const p = parseFloat(pnl);
        const avg = trades > 0 ? p / trades : 0;
        const winPct = trades > 0 ? (wins / trades * 100) : 0;
        html += '<div class="ht-pnl ' + (p>=0?"pos":"neg") + '">' + (p>=0?"+":"−") + "₹" + Math.abs(Math.round(p)).toLocaleString("en-IN") + '</div>';
        html += '<div class="ht-grid">';
        html +=   '<div class="ht-k">Trades</div><div class="ht-v">' + trades + '</div>';
        html +=   '<div class="ht-k">Win rate</div><div class="ht-v">' + winPct.toFixed(0) + '% (' + wins + 'W / ' + losses + 'L)</div>';
        html +=   '<div class="ht-k">Avg/trade</div><div class="ht-v ' + (avg>=0?"pos":"neg") + '">' + (avg>=0?"+":"−") + "₹" + Math.abs(Math.round(avg)).toLocaleString("en-IN") + '</div>';
        html += '</div>';
        const tags = [];
        if(live > 0) tags.push('<span class="ht-tag live">LIVE ×' + live + '</span>');
        if(bt > 0)   tags.push('<span class="ht-tag bt">BT ×' + bt + '</span>');
        if(tags.length) html += '<div class="ht-tags">' + tags.join("") + '</div>';
        html += '<div class="ht-hint">→ click to filter trade table</div>';
      }
      tip.innerHTML = html;
      tip.classList.add("show");
    });
    cell.addEventListener("mousemove", (e) => {
      const tw = tip.offsetWidth || 220;
      const th = tip.offsetHeight || 100;
      let x = e.clientX + 14;
      let y = e.clientY + 14;
      if(x + tw > window.innerWidth - 8) x = e.clientX - tw - 14;
      if(y + th > window.innerHeight - 8) y = e.clientY - th - 14;
      tip.style.left = Math.max(8, x) + "px";
      tip.style.top = Math.max(8, y) + "px";
    });
    cell.addEventListener("mouseleave", () => { tip.classList.remove("show"); });
  });
}

function setText(id, v){ const e = document.getElementById(id); if(e) e.textContent = v; }

// Phase 8q · Latency tracking
const _latencies = [];
function recordLatency(endpoint, ms){
  _latencies.push({ endpoint, ms, t: Date.now() });
  if(_latencies.length > 30) _latencies.shift();
  const recent = _latencies.slice(-10);
  const avg = recent.reduce((s,x) => s + x.ms, 0) / recent.length;
  const chip = document.getElementById("latency-chip");
  if(chip){
    chip.textContent = "API " + Math.round(avg) + "ms";
    chip.className = "chip " + (avg < 50 ? "lat-fast" : avg < 200 ? "lat-mid" : "lat-slow");
  }
}

// Phase 8q · Adaptive cadence (1s/5s during market hours, 5s/30s when closed)
let _fastInterval = null, _slowInterval = null;
let _currentCadence = "closed";
function applyCadence(marketOpen){
  const target = marketOpen ? "open" : "closed";
  if(target === _currentCadence) return;
  _currentCadence = target;
  if(_fastInterval) clearInterval(_fastInterval);
  if(_slowInterval) clearInterval(_slowInterval);
  const fastMs = marketOpen ? 1000 : 5000;
  const slowMs = marketOpen ? 5000 : 30000;
  _fastInterval = setInterval(() => refreshFast(), fastMs);
  _slowInterval = setInterval(() => refreshSlow(), slowMs);
  console.log("[cadence] applied " + target + ": fast=" + fastMs + "ms slow=" + slowMs + "ms");
}

// Phase 8n.1: Elite Challenge polling (decoupled from refreshStatus)
setTimeout(function(){ try { refreshChallenge(); } catch(e){} }, 800);
setInterval(function(){ try { refreshChallenge(); } catch(e){} }, 7500);

// Phase 8h.2: Market Regime panel
let _regimeChart = null;
async function refreshRegime(){
  const r = await fetchJSON('/api/regime');
  if(!r) return;
  const cEl = document.getElementById('regime-current');
  if(cEl){
    cEl.textContent = r.current || 'UNKNOWN';
    var cls = 'info';
    if(r.current === 'RANGE') cls = 'healthy';
    else if(r.current === 'CHOP') cls = 'at-risk';
    else if(r.current === 'TREND') cls = 'breached';
    cEl.className = 'panel-badge ' + cls;
  }
  const aEl = document.getElementById('regime-adx');
  if(aEl){ aEl.textContent = 'ADX ' + (r.current_adx != null ? r.current_adx.toFixed(1) : '--'); }
  const regimes = r.regimes || {};
  const keys = ['TREND', 'RANGE', 'CHOP'];
  const trades = keys.map(function(k){ return (regimes[k] && regimes[k].trades) || 0; });
  const ctx = document.getElementById('regime-donut');
  if(ctx && typeof Chart !== 'undefined'){
    if(_regimeChart) _regimeChart.destroy();
    _regimeChart = new Chart(ctx, {
      type: 'doughnut',
      data: { labels: keys, datasets: [{ data: trades, backgroundColor: ['#ef4444', '#10b981', '#f59e0b'], borderWidth: 0, hoverOffset: 8 }] },
      options: { responsive: true, maintainAspectRatio: false, cutout: '65%',
        plugins: {
          legend: { position: 'bottom', labels: { font: { family: 'Inter', size: 11 } } },
          tooltip: { callbacks: { label: function(c){ var k = c.label; var m = regimes[k] || {}; return k + ': ' + (m.trades || 0) + ' trades, Rs ' + Math.round(m.total_pnl || 0).toLocaleString(); } } }
        }
      }
    });
  }
  const tEl = document.getElementById('regime-table');
  if(tEl){
    var html = '<table class="regime-stats"><thead><tr><th>Regime</th><th>Trades</th><th>WR</th><th>Total PnL</th><th>Avg</th><th>PF</th></tr></thead><tbody>';
    // Phase 9.8e B8: sample-size guard - WR/PF unreliable when n<5
    var SAMPLE_MIN = 5;
    keys.forEach(function(k){
      var m = regimes[k] || {};
      var n = m.trades || 0;
      var pnlStr = m.total_pnl != null ? 'Rs ' + Math.round(m.total_pnl).toLocaleString() : '--';
      var avgStr = m.avg_pnl != null ? 'Rs ' + Math.round(m.avg_pnl).toLocaleString() : '--';
      var wrStr, pfStr;
      if (n < SAMPLE_MIN) {
        var tip = 'needs &ge;' + SAMPLE_MIN + ' trades (n=' + n + ')';
        wrStr = '<span class="ns-small" title="' + tip + '">&mdash;</span>';
        pfStr = '<span class="ns-small" title="' + tip + '">&mdash;</span>';
      } else {
        wrStr = m.win_rate != null ? (m.win_rate * 100).toFixed(0) + '%' : '&mdash;';
        pfStr = m.profit_factor != null ? (m.profit_factor >= 999 ? '&infin;' : m.profit_factor.toFixed(2)) : '&mdash;';
      }
      var nCell = (n < SAMPLE_MIN) ? '<span class="ns-trades">' + n + '</span>' : String(n);
      html += '<tr><td><span class="regime-pill regime-' + k.toLowerCase() + '">' + k + '</span></td><td>' + nCell + '</td><td>' + wrStr + '</td><td class="num">' + pnlStr + '</td><td class="num">' + avgStr + '</td><td>' + pfStr + '</td></tr>';
    });
    html += '</tbody></table>';
    tEl.innerHTML = html;
  }
}
setTimeout(function(){ try { refreshRegime(); } catch(e){} }, 1100);
setInterval(function(){ try { refreshRegime(); } catch(e){} }, 30000);

// Phase 9.8v: PFM panel + tick chip live updaters
async function refreshPfm(){
  try {
    const r = await fetch("/api/risk", { credentials: "same-origin" });
    if (!r.ok) return;
    const d = await r.json();
    if (!d || d.cumulative_pnl == null) return;
    const pnl = Number(d.cumulative_pnl);
    const peak = Number(d.peak_equity || 0);
    const cumEl = document.getElementById("pfm-cum");
    if (cumEl) { cumEl.textContent = (pnl >= 0 ? "+" : "") + "₹" + pnl.toLocaleString("en-IN",{maximumFractionDigits:0}); cumEl.className = "pfm-val " + (pnl >= 0 ? "profit" : "loss"); }
    const peakEl = document.getElementById("pfm-peak");
    if (peakEl) peakEl.textContent = "₹" + peak.toLocaleString("en-IN",{maximumFractionDigits:0});
    const daysEl = document.getElementById("pfm-days");
    if (daysEl) daysEl.textContent = String(d.days_traded || 0);
    const bestEl = document.getElementById("pfm-best");
    if (bestEl) bestEl.textContent = "₹" + Number(d.best_day_pnl || 0).toLocaleString("en-IN",{maximumFractionDigits:0});
    const consEl = document.getElementById("pfm-cons");
    if (consEl) consEl.textContent = (d.consistency_flag ? "✓ " : "⚠ ") + Number(d.consistency_frac || 0).toFixed(2);
    const progEl = document.getElementById("pfm-prog");
    const progBar = document.getElementById("pfm-prog-bar");
    const pct = Math.max(0, Math.min(100, Number(d.profit_target_progress || 0) * 100));
    if (progEl) progEl.textContent = pct.toFixed(0) + "%";
    if (progBar) progBar.style.width = pct + "%";
    const chip = document.getElementById("pfm-chip");
    if (chip) { const s = d.consistency_flag ? "pfm-ok" : "pfm-soft"; chip.className = "chip " + s; chip.textContent = "PFM: " + (d.consistency_flag ? "OK" : "WARN"); }
    const badge = document.getElementById("pfm-status-badge");
    if (badge) badge.textContent = d.consistency_flag ? "CONSISTENT" : "REVIEW";
  } catch(e) {}
}

async function refreshTickChip(){
  try {
    const r = await fetch("/api/ticks/stats", { credentials: "same-origin" });
    if (!r.ok) return;
    const d = await r.json();
    const chip = document.getElementById("tick-chip");
    if (!chip) return;
    if (d && d.subscribers != null && d.subscribers > 0) {
      chip.className = "chip tick-live";
      chip.textContent = "Ticks: " + (d.last_tick_age_sec != null ? Math.round(d.last_tick_age_sec) + "s" : "live");
    } else {
      chip.className = "chip tick-stale";
      chip.textContent = "Ticks: idle";
    }
  } catch(e) {}
}

setInterval(refreshPfm, 60000);
setInterval(refreshTickChip, 5000);
setTimeout(refreshPfm, 1500);
setTimeout(refreshTickChip, 1500);

// Phase 9.8w: latency monitor - wraps fetch to measure RTT, p50 over 20 samples
(function _p98w_latency(){
  const samples = [];
  const _origFetch = window.fetch.bind(window);
  window.fetch = function(...args){
    const t0 = performance.now();
    return _origFetch(...args).then(r => {
      const dt = performance.now() - t0;
      samples.push(dt);
      if (samples.length > 20) samples.shift();
      return r;
    }).catch(e => {
      samples.push(2000);
      if (samples.length > 20) samples.shift();
      throw e;
    });
  };
  function p50(arr){
    if (!arr.length) return 0;
    const s = [...arr].sort((a,b) => a-b);
    return s[Math.floor(s.length/2)];
  }
  function update(){
    const chip = document.getElementById("latency-chip");
    if (!chip || !samples.length) return;
    const v = Math.round(p50(samples));
    chip.textContent = v + "ms";
    chip.className = "chip " + (v < 200 ? "ok" : v < 500 ? "warn" : "err");
    chip.title = "p50 round-trip over last " + samples.length + " API calls";
  }
  setInterval(update, 2000);
  setTimeout(update, 2500);
})();

// Phase 9.8x: regime overlay plugin for equity chart
(function _p98x_regimeOverlay(){
  if (typeof Chart === 'undefined') return;
  let regimeRows = null;
  const colors = {
    TREND:   'rgba(16,185,129,0.10)',
    RANGE:   'rgba(59,130,246,0.10)',
    CHOP:    'rgba(245,158,11,0.10)',
    UNKNOWN: 'rgba(139,148,168,0.04)'
  };
  async function fetchRegime(){
    try {
      const r = await fetch('/api/regime/timeseries', { credentials:'same-origin' });
      if (!r.ok) return;
      const d = await r.json();
      regimeRows = (d && d.rows) || [];
      const inst = Chart.getChart && Chart.getChart('equity-chart');
      if (inst) inst.update('none');
    } catch(e) {}
  }
  function buildIndex(){
    const idx = {};
    if (!regimeRows) return idx;
    for (const r of regimeRows) idx[r.date] = r.regime;
    return idx;
  }
  const plugin = {
    id: 'regimeOverlay',
    beforeDatasetsDraw(chart){
      if (!chart.canvas || chart.canvas.id !== 'equity-chart') return;
      if (!regimeRows || !regimeRows.length) return;
      const idx = buildIndex();
      const labels = chart.data.labels || [];
      const ctx = chart.ctx;
      const area = chart.chartArea;
      const xScale = chart.scales.x;
      ctx.save();
      labels.forEach((label, i) => {
        const lblStr = String(label).slice(0,10);
        const regime = idx[lblStr];
        if (!regime) return;
        const x0 = xScale.getPixelForValue(i);
        const x1 = i + 1 < labels.length ? xScale.getPixelForValue(i+1) : area.right;
        ctx.fillStyle = colors[regime] || colors.UNKNOWN;
        ctx.fillRect(x0, area.top, Math.max(1, x1 - x0), area.bottom - area.top);
      });
      ctx.restore();
    }
  };
  Chart.register(plugin);
  // wait for equity chart to exist, then refresh
  let polled = 0;
  const poller = setInterval(() => {
    polled++;
    const inst = Chart.getChart && Chart.getChart('equity-chart');
    if (inst) {
      clearInterval(poller);
      fetchRegime();
    }
    if (polled > 60) clearInterval(poller);
  }, 1000);
})();

// Phase 9.8y: keyboard shortcuts
(function _p98y_keyboard(){
  let chordMode = null;
  let chordTimer = null;
  function isTyping(){
    const a = document.activeElement;
    if (!a) return false;
    const tag = (a.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return true;
    if (a.isContentEditable) return true;
    return false;
  }
  function flash(el){
    if (!el) return;
    el.classList.add("kbd-flash");
    setTimeout(() => el.classList.remove("kbd-flash"), 1000);
  }
  function scrollTo(sel){
    const el = document.querySelector(sel);
    if (!el) return false;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    flash(el);
    return true;
  }
  function showModal(){ const m = document.getElementById("kbd-modal"); if (m) m.hidden = false; }
  function hideModal(){ const m = document.getElementById("kbd-modal"); if (m) m.hidden = true; }
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      hideModal();
      if (document.activeElement && typeof document.activeElement.blur === "function") document.activeElement.blur();
      chordMode = null;
      return;
    }
    if (isTyping()) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (chordMode === "g") {
      clearTimeout(chordTimer);
      chordMode = null;
      const targets = {
        e: "#equity-chart-wrap",
        r: "#panel-regime",
        p: "#panel-pfm",
        t: "#trades-table",
        l: "#panel-log"
      };
      const sel = targets[e.key.toLowerCase()];
      if (sel) { e.preventDefault(); scrollTo(sel); }
      return;
    }
    switch (e.key) {
      case "?":
        e.preventDefault(); showModal(); break;
      case "r":
        e.preventDefault();
        if (typeof refreshFast === "function") refreshFast();
        if (typeof refreshSlow === "function") refreshSlow();
        break;
      case "t":
        e.preventDefault();
        const tt = document.getElementById("theme-toggle");
        if (tt) tt.click();
        break;
      case "1":
        e.preventDefault(); scrollTo("#card-BNF"); break;
      case "2":
        e.preventDefault(); scrollTo("#card-NF"); break;
      case "3":
        e.preventDefault(); scrollTo("#card-MCN"); break;
      case "/":
        e.preventDefault();
        const s = document.getElementById("log-search");
        if (s) { s.focus(); s.select(); }
        break;
      case "g":
        chordMode = "g";
        chordTimer = setTimeout(() => { chordMode = null; }, 1500);
        break;
    }
  });
  document.addEventListener("click", (e) => {
    if (e.target && e.target.classList && e.target.classList.contains("kbd-close")) hideModal();
    if (e.target && e.target.id === "kbd-modal") hideModal();
  });
  console.log("Phase 9.8y: keyboard shortcuts active. Press ? for help.");
})();

// Phase 9.8z: smart empty states
(function _p98z_emptyStates(){
  function getISTNow(){
    const now = new Date();
    const utc = now.getTime() + now.getTimezoneOffset() * 60000;
    return new Date(utc + 5.5 * 3600000);
  }
  function isMarketOpen(){
    const ist = getISTNow();
    const day = ist.getDay();
    if (day === 0 || day === 6) return false;
    const mins = ist.getHours() * 60 + ist.getMinutes();
    return mins >= 555 && mins <= 930; // 09:15 - 15:30 IST
  }
  function nextMarketStart(){
    const ist = getISTNow();
    const next = new Date(ist);
    next.setHours(9, 14, 0, 0);
    if (next.getTime() <= ist.getTime()) next.setDate(next.getDate() + 1);
    while (next.getDay() === 0 || next.getDay() === 6) next.setDate(next.getDate() + 1);
    return next;
  }
  function fmtDelta(target){
    const ms = target.getTime() - getISTNow().getTime();
    if (ms <= 0) return "now";
    const h = Math.floor(ms / 3600000);
    const m = Math.floor((ms % 3600000) / 60000);
    if (h > 0) return h + "h " + m + "m";
    return m + "m";
  }
  function paintEmptyTrades(){
    const tbody = document.querySelector("#trades-table tbody");
    if (!tbody) return;
    const realRows = Array.from(tbody.children).filter(r => !r.classList.contains("es-row"));
    if (realRows.length > 0) return;
    const open = isMarketOpen();
    const next = nextMarketStart();
    const heading = open
      ? "Bot is watching for signals"
      : "Market closed";
    const subline = open
      ? "Waiting for z-score >= 1.5 with ADX confirmation"
      : "Next session opens in " + fmtDelta(next) + " (09:14 IST)";
    tbody.innerHTML = '<tr class="es-row"><td colspan="11" class="empty-state-cell"><div class="empty-state"><span class="empty-icon">\ud83d\udcca</span><span class="empty-text">' + heading + '</span><span class="empty-sub">' + subline + '</span></div></td></tr>';
  }
  function paintEmptyLog(){
    const lv = document.getElementById("log-view");
    if (!lv) return;
    const txt = (lv.textContent || "").trim();
    if (!txt) {
      lv.classList.add("is-empty");
      const open = isMarketOpen();
      lv.textContent = open
        ? "No log entries yet - waiting for first heartbeat..."
        : "Bot is offline - log will populate after market opens at 09:14 IST. Heartbeats appear every 30s when running.";
    } else if (txt.length > 60 && lv.classList.contains("is-empty")) {
      lv.classList.remove("is-empty");
    }
  }
  function tick(){
    try { paintEmptyTrades(); paintEmptyLog(); } catch(e) {}
  }
  // Observe trade table mutations to react fast after refreshTrades
  const tbody = document.querySelector("#trades-table tbody");
  if (tbody && typeof MutationObserver !== "undefined") {
    new MutationObserver(() => setTimeout(paintEmptyTrades, 80)).observe(tbody, { childList: true });
  }
  setTimeout(tick, 1500);
  setInterval(tick, 10000);
})();

// Phase 9.8aa: trade exit reason mix
(function _p98aa_reasonMix(){
  const COLORS = {
    TARGET: "#10b981",
    STOP: "#ef4444",
    TIME: "#f59e0b",
    Z_VEL_STALL: "#8b5cf6",
    KILL: "#dc2626",
    EOD: "#3b82f6",
    OTHER: "#6b7280"
  };
  const SYMBOLS = ["BNF", "NF", "MCN"];
  function pickField(t, names){
    for (const n of names) {
      if (t[n] != null && t[n] !== "") return t[n];
    }
    return null;
  }
  async function refresh(){
    try {
      const r = await fetch("/api/trades", { credentials: "same-origin" });
      if (!r.ok) return;
      const d = await r.json();
      const trades = Array.isArray(d) ? d : (d.trades || d.rows || []);
      const grouped = {};
      SYMBOLS.forEach(s => grouped[s] = {});
      trades.forEach(t => {
        const symRaw = pickField(t, ["symbol", "sym", "instrument"]) || "";
        const sym = String(symRaw).toUpperCase();
        if (!SYMBOLS.includes(sym)) return;
        const reasonRaw = pickField(t, ["reason", "exit_reason", "exit"]) || "OTHER";
        const reason = String(reasonRaw).toUpperCase().replace(/\s+/g, "_");
        grouped[sym][reason] = (grouped[sym][reason] || 0) + 1;
      });
      const body = document.getElementById("reason-mix-body");
      if (!body) return;
      let html = "";
      SYMBOLS.forEach(sym => {
        const counts = grouped[sym] || {};
        const reasonKeys = Object.keys(counts);
        const total = reasonKeys.reduce((a, k) => a + counts[k], 0);
        if (total === 0) {
          html += '<div class="rmix-row"><div class="rmix-header"><span class="rmix-sym">' + sym + '</span> <span class="muted">(0 trades)</span></div><div class="rmix-bar"><div class="rmix-empty">no trades yet</div></div></div>';
          return;
        }
        const sorted = reasonKeys.sort((a,b) => counts[b] - counts[a]);
        let bars = "", chips = "";
        sorted.forEach(re => {
          const c = counts[re];
          const pct = (c / total * 100);
          const color = COLORS[re] || COLORS.OTHER;
          bars += '<div class="rmix-seg" style="width:' + pct.toFixed(2) + '%;background:' + color + '" title="' + re + ': ' + c + ' (' + pct.toFixed(1) + '%)"></div>';
          chips += '<span class="rmix-chip" style="--c:' + color + '">' + re + ' ' + c + '</span>';
        });
        const noun = total === 1 ? "trade" : "trades";
        html += '<div class="rmix-row"><div class="rmix-header"><span class="rmix-sym">' + sym + '</span> <span class="muted">(' + total + ' ' + noun + ')</span></div><div class="rmix-bar">' + bars + '</div><div class="rmix-chips">' + chips + '</div></div>';
      });
      body.innerHTML = html;
    } catch(e) {}
  }
  setTimeout(refresh, 2000);
  setInterval(refresh, 60000);
})();

// Phase 9.8ab Fix 6: schedule-time fallback when /api/status doesn't populate it
(function _p98ab_schedFallback(){
  setInterval(function(){
    var el = document.getElementById('schedule-time');
    if (!el) return;
    var t = (el.textContent||'').trim();
    if (t === '--' || t === '') {
      var now = new Date();
      var utc = now.getTime() + now.getTimezoneOffset()*60000;
      var ist = new Date(utc + 5.5*3600000);
      var next = new Date(ist);
      next.setHours(9,14,0,0);
      if (next.getTime() <= ist.getTime()) next.setDate(next.getDate()+1);
      while (next.getDay() === 0 || next.getDay() === 6) next.setDate(next.getDate()+1);
      var pad = function(n){return n<10?'0'+n:n;};
      el.textContent = next.toDateString().slice(0,10) + ' · ' + pad(next.getHours())+':'+pad(next.getMinutes())+' IST';
    }
  }, 5000);
})();

// Phase 9.8ab Fix 1: reason mix robust response parsing
(function _p98ab_mixFix(){
  const COLORS = { TARGET:'#10b981', STOP:'#ef4444', TIME:'#f59e0b', Z_VEL_STALL:'#8b5cf6', KILL:'#dc2626', EOD:'#3b82f6', OTHER:'#6b7280' };
  const SYMBOLS = ['BNF','NF','MCN'];
  function inferSymbolFromTrade(t){
    var direct = t.symbol || t.sym || t.instrument || t.ticker;
    if (direct) return String(direct).toUpperCase();
    var entry = Number(t.entry || t.in || t.in_price || t.entryPrice || 0);
    if (entry > 50000) return 'BNF';
    if (entry > 22000 && entry < 30000) return 'NF';
    if (entry > 12000 && entry < 16000) return 'MCN';
    return null;
  }
  function flatten(d){
    if (Array.isArray(d)) return d;
    if (d && Array.isArray(d.trades)) return d.trades;
    if (d && Array.isArray(d.rows)) return d.rows;
    if (d && typeof d === 'object'){
      var out=[];
      for (var k of Object.keys(d)){
        if (Array.isArray(d[k])){
          for (var t of d[k]) out.push(Object.assign({symbol:k}, t));
        }
      }
      return out;
    }
    return [];
  }
  async function refresh(){
    try {
      const r = await fetch('/api/trades', { credentials:'same-origin' });
      if (!r.ok) return;
      const d = await r.json();
      const trades = flatten(d);
      const grouped = { BNF:{}, NF:{}, MCN:{} };
      trades.forEach(t => {
        var sym = inferSymbolFromTrade(t);
        if (!sym || !SYMBOLS.includes(sym)) return;
        var reasonRaw = t.reason || t.exit_reason || t.exit || 'OTHER';
        var reason = String(reasonRaw).toUpperCase().replace(/\s+/g,'_');
        grouped[sym][reason] = (grouped[sym][reason]||0)+1;
      });
      const body = document.getElementById('reason-mix-body');
      if (!body) return;
      var html='';
      SYMBOLS.forEach(function(sym){
        var counts = grouped[sym]||{};
        var keys = Object.keys(counts);
        var total = keys.reduce(function(a,k){return a+counts[k];},0);
        if (total===0){
          html += '<div class="rmix-row"><div class="rmix-header"><span class="rmix-sym">'+sym+'</span> <span class="muted">(0 trades)</span></div><div class="rmix-bar"><div class="rmix-empty">no trades yet</div></div></div>';
          return;
        }
        var sorted = keys.sort(function(a,b){return counts[b]-counts[a];});
        var bars='', chips='';
        sorted.forEach(function(re){
          var c = counts[re];
          var pct = c/total*100;
          var color = COLORS[re]||COLORS.OTHER;
          bars += '<div class="rmix-seg" style="width:'+pct.toFixed(2)+'%;background:'+color+'" title="'+re+': '+c+' ('+pct.toFixed(1)+'%)"></div>';
          chips += '<span class="rmix-chip" style="--c:'+color+'">'+re+' '+c+'</span>';
        });
        var noun = total===1?'trade':'trades';
        html += '<div class="rmix-row"><div class="rmix-header"><span class="rmix-sym">'+sym+'</span> <span class="muted">('+total+' '+noun+')</span></div><div class="rmix-bar">'+bars+'</div><div class="rmix-chips">'+chips+'</div></div>';
      });
      body.innerHTML = html;
    } catch(e){}
  }
  setTimeout(refresh, 2500);
  setInterval(refresh, 60000);
})();

// Phase 9.8ac: post-refresh fixers (defensive overrides for minified upstream code)
(function _p98ac_finalFixers(){
  function safeNum(v){
    if (v == null) return 0;
    if (typeof v === "number") return isFinite(v) ? v : 0;
    if (typeof v === "string") return parseFloat(v) || 0;
    if (typeof v === "object") {
      if (v.value != null) return safeNum(v.value);
      if (v.count != null) return safeNum(v.count);
      if (v.days != null) return safeNum(v.days);
      // numpy-serialized scalars sometimes look like { "0": 5 }
      if (v["0"] != null) return safeNum(v["0"]);
      return 0;
    }
    return 0;
  }
  function safeBool(v){
    if (v === true || v === 1 || v === "True" || v === "true") return true;
    if (typeof v === "object" && v !== null) {
      if (v.value === true || v.value === "True") return true;
    }
    return false;
  }

  // Fix 5: Total P&L percent on Rs 37.5L live capital
  setInterval(function(){
    var totalEl = document.getElementById("total-pnl");
    var pctEl = document.getElementById("pnl-pct");
    if (!totalEl || !pctEl) return;
    var txt = (totalEl.textContent || "").replace(/[^0-9.\-]/g, "");
    var v = parseFloat(txt);
    if (!isNaN(v) && v !== 0) {
      var newTxt = (v >= 0 ? "+" : "") + (v/(window.__CAPITAL__||3750000)*100).toFixed(2) + "% on ₹37.5L";
      if (pctEl.textContent !== newTxt) pctEl.textContent = newTxt;
    }
  }, 3000);

  // Fix 7: Strategy KPI - replace verbose config dump with friendly summary
  setInterval(function(){
    var el = document.getElementById("strategy-detail");
    if (!el) return;
    var t = (el.textContent || "").trim();
    if (t.length > 80 || t.indexOf("z_e") !== -1 || t.indexOf("max ") !== -1 || t.indexOf("HEDGE_FUND") !== -1) {
      el.innerHTML = '<div style="font-size:11px;line-height:1.5"><div><strong>Mean Reversion</strong></div><div class="muted">z entry ±1.5 · stop ±3.5</div><div class="muted">BNF + NF · ₹37.5L · paper</div></div>';
    }
  }, 4000);

  // PFM panel defensive: handle nested objects, numpy-serialized scalars, missing fields
  async function refreshPfmStrong(){
    try {
      var r = await fetch("/api/risk", { credentials: "same-origin" });
      if (!r.ok) return;
      var d = await r.json();
      if (!d) return;
      var pnl = safeNum(d.cumulative_pnl);
      var peak = safeNum(d.peak_equity);
      var days = safeNum(d.days_traded);
      var best = safeNum(d.best_day_pnl);
      var cf = safeNum(d.consistency_frac);
      var flag = safeBool(d.consistency_flag);
      var prog = safeNum(d.profit_target_progress);
      var cumEl = document.getElementById("pfm-cum");
      if (cumEl) {
        cumEl.textContent = (pnl >= 0 ? "+" : "") + "₹" + pnl.toLocaleString("en-IN",{maximumFractionDigits:0});
        cumEl.className = "pfm-val " + (pnl >= 0 ? "profit" : "loss");
      }
      var peakEl = document.getElementById("pfm-peak");
      if (peakEl) peakEl.textContent = "₹" + peak.toLocaleString("en-IN",{maximumFractionDigits:0});
      var daysEl = document.getElementById("pfm-days");
      if (daysEl) daysEl.textContent = String(days);
      var bestEl = document.getElementById("pfm-best");
      if (bestEl) bestEl.textContent = "₹" + best.toLocaleString("en-IN",{maximumFractionDigits:0});
      var consEl = document.getElementById("pfm-cons");
      if (consEl) consEl.textContent = (flag ? "✓ " : "⚠ ") + cf.toFixed(2);
      var progEl = document.getElementById("pfm-prog");
      var progBar = document.getElementById("pfm-prog-bar");
      var pct = Math.max(0, Math.min(100, prog * 100));
      if (progEl) progEl.textContent = pct.toFixed(0) + "%";
      if (progBar) progBar.style.width = pct + "%";
      var badge = document.getElementById("pfm-status-badge");
      if (badge) badge.textContent = flag ? "CONSISTENT" : "REVIEW";
    } catch(e) {}
  }
  setInterval(refreshPfmStrong, 30000);
  setTimeout(refreshPfmStrong, 1500);
  setTimeout(refreshPfmStrong, 4000);
})();

// ===== Phase 9.8e B-UI-4 + B-UI-1: Bloomberg status bar + flash highlights =====
(function _p98e_premium(){
  if (window.__P98E_PREMIUM__) return;
  window.__P98E_PREMIUM__ = true;

  // ---------- B-UI-4: dense top status bar ----------
  function injectBar(){
    if (document.getElementById('p98e-statusbar')) return;
    const bar = document.createElement('div');
    bar.id = 'p98e-statusbar';
    bar.className = 'p98e-statusbar';
    bar.innerHTML =
      '<div class="sb-cell sb-brand">OU-MRS</div>' +
      '<div class="sb-cell"><span class="sb-lbl">IST</span><span class="sb-val sb-mono" id="sb-clock">--:--:--</span></div>' +
      '<div class="sb-cell"><span class="sb-lbl">MKT</span><span class="sb-val" id="sb-mkt">--</span></div>' +
      '<div class="sb-cell sb-grow"><span class="sb-lbl">SESSION</span><span class="sb-val" id="sb-session">--</span></div>' +
      '<div class="sb-cell"><span class="sb-lbl">CUM P&amp;L</span><span class="sb-val" id="sb-cum">--</span></div>' +
      '<div class="sb-cell"><span class="sb-lbl">TODAY</span><span class="sb-val" id="sb-day">--</span></div>' +
      '<div class="sb-cell"><span class="sb-lbl">LAT</span><span class="sb-val" id="sb-lat">--</span></div>' +
      '<div class="sb-cell sb-pulse-cell"><span class="sb-pulse" id="sb-pulse" title="live heartbeat"></span></div>';
    document.body.insertBefore(bar, document.body.firstChild);
    document.body.classList.add('p98e-has-statusbar');
  }
  function pad(n,k){ return String(n).padStart(k,'0'); }
  function istNow(){
    const now = new Date();
    const utcMs = now.getTime() + now.getTimezoneOffset()*60000;
    return new Date(utcMs + 5.5*3600*1000);
  }
  function marketState(d){
    const dow = d.getDay();
    if (dow === 0 || dow === 6) return {state:'CLOSED', cls:'closed', sub:'Weekend market closed'};
    const m = d.getHours()*60 + d.getMinutes();
    const openM = 9*60+15, closeM = 15*60+30;
    if (m < openM){
      const mins = openM - m;
      return {state:'PRE-OPEN', cls:'preopen', sub:'Opens in ' + Math.floor(mins/60) + 'h ' + (mins%60) + 'm'};
    }
    if (m < closeM){
      const mins = closeM - m;
      return {state:'OPEN', cls:'open', sub:'Closes in ' + Math.floor(mins/60) + 'h ' + (mins%60) + 'm'};
    }
    return {state:'CLOSED', cls:'closed', sub:'After-hours / next open 09:15 IST'};
  }
  function tick(){
    const d = istNow();
    const ck = document.getElementById('sb-clock');
    if (ck) ck.textContent = pad(d.getHours(),2)+':'+pad(d.getMinutes(),2)+':'+pad(d.getSeconds(),2);
    const ms = marketState(d);
    const mk = document.getElementById('sb-mkt');
    if (mk){ mk.textContent = ms.state; mk.className = 'sb-val sb-mkt-' + ms.cls; }
    const ss = document.getElementById('sb-session');
    if (ss) ss.textContent = ms.sub;
    // mirror Top KPI cumulative
    const tot = document.getElementById('total-pnl');
    const sbc = document.getElementById('sb-cum');
    if (tot && sbc){
      sbc.textContent = (tot.textContent || '--').trim();
      const pos = /positive/.test(tot.className), neg = /negative/.test(tot.className);
      sbc.className = 'sb-val ' + (pos ? 'sb-pos' : neg ? 'sb-neg' : '');
    }
    // mirror today's PnL — try common ids
    const day = document.getElementById('today-pnl') || document.getElementById('pnl-today') || document.getElementById('day-pnl');
    const sbd = document.getElementById('sb-day');
    if (sbd){
      if (day){
        sbd.textContent = (day.textContent || '--').trim();
        const dpos = /positive/.test(day.className), dneg = /negative/.test(day.className);
        sbd.className = 'sb-val ' + (dpos ? 'sb-pos' : dneg ? 'sb-neg' : '');
      } else {
        sbd.textContent = '--';
      }
    }
    // mirror latency chip
    const lat = document.getElementById('latency-chip');
    const sbl = document.getElementById('sb-lat');
    if (sbl){
      if (lat) sbl.textContent = (lat.textContent || '--').replace(/^API\s+/i,'');
      else sbl.textContent = '--';
    }
  }
  function startBar(){
    injectBar();
    tick();
    setInterval(tick, 1000);
    setInterval(function(){
      const p = document.getElementById('sb-pulse');
      if (p){ p.classList.add('beat'); setTimeout(function(){ p.classList.remove('beat'); }, 300); }
    }, 2000);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', startBar);
  else startBar();

  // ---------- B-UI-1: flash highlights on numeric change ----------
  function parseNum(s){
    if (s == null) return NaN;
    const cleaned = String(s).replace(/[,\s₹Rs]/g,'').replace(/[^\d.\-+]/g,'');
    if (!cleaned) return NaN;
    return parseFloat(cleaned);
  }
  function attachFlash(){
    const sel = '.kpi-value, #total-pnl, #pnl-pct, #trade-count, #win-rate, #pfm-cum, #pfm-peak, #sb-cum, #sb-day';
    document.querySelectorAll(sel).forEach(function(el){
      if (el.dataset.p98eFlash) return;
      el.dataset.p98eFlash = '1';
      el.dataset.lastTxt = el.textContent;
      const obs = new MutationObserver(function(){
        const newT = el.textContent;
        const oldT = el.dataset.lastTxt || '';
        if (newT === oldT) return;
        el.dataset.lastTxt = newT;
        const n1 = parseNum(oldT), n2 = parseNum(newT);
        let cls;
        if (isNaN(n1) || isNaN(n2)) cls = 'flash-eq';
        else if (n2 > n1) cls = 'flash-up';
        else if (n2 < n1) cls = 'flash-down';
        else cls = 'flash-eq';
        el.classList.remove('flash-up','flash-down','flash-eq');
        void el.offsetWidth; // restart animation
        el.classList.add(cls);
        setTimeout(function(){ el.classList.remove(cls); }, 900);
      });
      obs.observe(el, {childList:true, characterData:true, subtree:true});
    });
  }
  setTimeout(attachFlash, 1500);
  setInterval(attachFlash, 5000);
})();

// ===== Phase 9.8e B-UI-2: KPI mini sparklines (SVG, no deps) =====
(function _p98e_sparklines(){
  if (window.__P98E_SPARK__) return;
  window.__P98E_SPARK__ = true;
  const HIST_KEY = 'p98e_kpi_hist_v1';
  const MAX = 40;
  function loadHist(){
    try { return JSON.parse(localStorage.getItem(HIST_KEY) || '{}'); } catch(e){ return {}; }
  }
  function saveHist(h){
    try { localStorage.setItem(HIST_KEY, JSON.stringify(h)); } catch(e){}
  }
  function parseNum(s){
    if (s == null) return null;
    const cleaned = String(s).replace(/[,\s₹Rs%]/g,'').replace(/[^\d.\-+]/g,'');
    if (!cleaned || cleaned === '-' || cleaned === '+') return null;
    const n = parseFloat(cleaned);
    return isNaN(n) ? null : n;
  }
  function buildSvg(vals, w, h){
    if (!vals || vals.length < 2) return '';
    const min = Math.min(...vals), max = Math.max(...vals);
    const range = max - min || 1;
    const pad = 2;
    const step = (w - pad*2) / (vals.length - 1);
    const pts = vals.map(function(v, i){
      const x = pad + i*step;
      const y = h - pad - ((v - min) / range) * (h - pad*2);
      return x.toFixed(1) + ',' + y.toFixed(1);
    }).join(' ');
    const last = vals[vals.length-1], first = vals[0];
    const trend = last > first ? 'up' : last < first ? 'down' : 'flat';
    const lastX = pad + (vals.length-1)*step;
    const lastY = h - pad - ((last - min) / range) * (h - pad*2);
    return '<svg class="p98e-spark p98e-spark-' + trend + '" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '">' +
      '<polyline points="' + pts + '" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>' +
      '<circle cx="' + lastX.toFixed(1) + '" cy="' + lastY.toFixed(1) + '" r="1.6" fill="currentColor"/>' +
      '</svg>';
  }
  const TARGETS = [
    { sel: '#total-pnl', key: 'total_pnl' },
    { sel: '#pnl-pct', key: 'pnl_pct' },
    { sel: '#trade-count', key: 'trade_count' },
    { sel: '#win-rate', key: 'win_rate' }
  ];
  function tick(){
    const hist = loadHist();
    let changed = false;
    TARGETS.forEach(function(t){
      const el = document.querySelector(t.sel);
      if (!el) return;
      const n = parseNum(el.textContent);
      if (n == null) return;
      hist[t.key] = hist[t.key] || [];
      const last = hist[t.key][hist[t.key].length - 1];
      if (last !== n) {
        hist[t.key].push(n);
        if (hist[t.key].length > MAX) hist[t.key].shift();
        changed = true;
      }
      // attach or update spark
      let sp = el.parentNode.querySelector('.p98e-spark-host[data-key="' + t.key + '"]');
      if (!sp) {
        sp = document.createElement('span');
        sp.className = 'p98e-spark-host';
        sp.setAttribute('data-key', t.key);
        el.insertAdjacentElement('afterend', sp);
      }
      sp.innerHTML = buildSvg(hist[t.key], 56, 16);
    });
    if (changed) saveHist(hist);
  }
  function start(){ tick(); setInterval(tick, 5500); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else setTimeout(start, 1800);
})();

// ===== Phase 9.8e B-CAL-7: heatmap legend + B-CAL-8: streak markers =====
(function _p98e_calLegend(){
  if (window.__P98E_CAL_LEGEND__) return;
  window.__P98E_CAL_LEGEND__ = true;

  function injectLegend(){
    const hm = document.getElementById('heatmap') || document.querySelector('.heatmap-grid') || document.querySelector('[id*="heatmap"]');
    if (!hm) return false;
    const host = hm.parentNode;
    if (!host || host.querySelector('.hm-legend')) return true;
    const leg = document.createElement('div');
    leg.className = 'hm-legend';
    leg.innerHTML =
      '<span class="hm-leg-lbl">P&amp;L bins:</span>' +
      '<span class="hm-leg-item"><span class="hm-leg-sw t-loss-2"></span>&lt; &minus;&#8377;5k</span>' +
      '<span class="hm-leg-item"><span class="hm-leg-sw t-loss-1"></span>&minus;&#8377;5k..0</span>' +
      '<span class="hm-leg-item"><span class="hm-leg-sw t-flat"></span>0</span>' +
      '<span class="hm-leg-item"><span class="hm-leg-sw t-win-1"></span>0..+&#8377;5k</span>' +
      '<span class="hm-leg-item"><span class="hm-leg-sw t-win-2"></span>+&#8377;5k..+&#8377;25k</span>' +
      '<span class="hm-leg-item"><span class="hm-leg-sw t-win-3"></span>&gt; +&#8377;25k</span>' +
      '<span class="hm-leg-sep">&middot;</span>' +
      '<span class="hm-leg-item"><span class="hm-leg-emoji">&#128293;</span>3+ win streak</span>' +
      '<span class="hm-leg-item"><span class="hm-leg-emoji">&#10052;</span>3+ loss streak</span>';
    hm.insertAdjacentElement('afterend', leg);
    return true;
  }

  function markStreaks(){
    const cells = Array.from(document.querySelectorAll('.heatmap-cell, .hm-cell, [data-pnl]'));
    if (!cells.length) return;
    // Sort by date attribute if present
    cells.sort(function(a,b){
      const da = a.getAttribute('data-date') || '';
      const db = b.getAttribute('data-date') || '';
      return da.localeCompare(db);
    });
    let run = 0, runSign = 0;
    cells.forEach(function(c, i){
      // remove previous marker
      const prev = c.querySelector('.hm-streak-emoji');
      if (prev) prev.remove();
      const pnl = parseFloat(c.getAttribute('data-pnl') || '0');
      if (!pnl) { run = 0; runSign = 0; return; }
      const sign = pnl > 0 ? 1 : pnl < 0 ? -1 : 0;
      if (sign === runSign && sign !== 0) {
        run++;
      } else {
        run = 1;
        runSign = sign;
      }
      // Mark the cell that completes a streak of 3+ — and continues marking each subsequent
      const isLastInRun = (i === cells.length - 1) ||
                          (function(){
                            const next = cells[i+1];
                            if (!next) return true;
                            const np = parseFloat(next.getAttribute('data-pnl') || '0');
                            const ns = np > 0 ? 1 : np < 0 ? -1 : 0;
                            return ns !== sign;
                          })();
      if (run >= 3 && isLastInRun) {
        const em = document.createElement('span');
        em.className = 'hm-streak-emoji';
        em.textContent = sign > 0 ? '\uD83D\uDD25' : '\u2744';
        em.title = (sign > 0 ? 'Win' : 'Loss') + ' streak: ' + run + ' days';
        c.appendChild(em);
      }
    });
  }

  function tick(){
    injectLegend();
    markStreaks();
  }
  setTimeout(tick, 2200);
  setInterval(tick, 8000);
})();

// ===== Phase 9.8f Bloomberg overlay: command bar + ticker tape + function keys + theme toggle =====
(function _p98f_bloomberg(){
  if (window.__P98F_BB__) return;
  window.__P98F_BB__ = true;

  function getPanels(){
    const out = [];
    document.querySelectorAll('section.panel, .panel').forEach(p => {
      const h = p.querySelector('h1, h2, h3');
      const id = p.id || '';
      const title = h ? h.textContent.trim().replace(/\s+/g, ' ').slice(0, 60) : (id || 'Panel');
      if (title) out.push({ id: id, title: title, el: p });
    });
    return out;
  }

  function flashPanel(el){
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    el.classList.remove('bb-panel-flash');
    void el.offsetWidth;
    el.classList.add('bb-panel-flash');
  }

  function jumpTo(keyword){
    const panels = getPanels();
    const k = (keyword || '').toLowerCase();
    const m = panels.find(p => (p.id || '').toLowerCase().includes(k) || p.title.toLowerCase().includes(k));
    if (m) flashPanel(m.el);
  }

  function toggleTheme(){
    const cur = document.documentElement.getAttribute('data-theme');
    const next = cur === 'bloomberg' ? '' : 'bloomberg';
    if (next) document.documentElement.setAttribute('data-theme', next);
    else document.documentElement.removeAttribute('data-theme');
    try { localStorage.setItem('ou-mrs-theme', next); } catch(e){}
  }
  try {
    if (localStorage.getItem('ou-mrs-theme') === 'bloomberg') {
      document.documentElement.setAttribute('data-theme', 'bloomberg');
    }
  } catch(e){}

  function ensureCommandBar(){
    if (document.getElementById('bb-command-bar')) return;
    const bar = document.createElement('div');
    bar.id = 'bb-command-bar';
    bar.hidden = true;
    bar.innerHTML =
      '<div class="bb-cmd-prompt">' +
        '<span class="bb-cmd-icon">&#10095;</span>' +
        '<input type="text" placeholder="Type to filter panels \u2014 Enter to jump, Esc to close" autocomplete="off"/>' +
      '</div>' +
      '<ul class="bb-cmd-list"></ul>' +
      '<div class="bb-cmd-hint"><span>&uarr;&darr; navigate</span><span>Enter jump</span><span>Esc close</span></div>';
    document.body.appendChild(bar);

    const input = bar.querySelector('input');
    const list = bar.querySelector('.bb-cmd-list');
    let panels = [], filtered = [], active = 0;

    function render(){
      list.innerHTML = '';
      filtered.forEach((p, i) => {
        const li = document.createElement('li');
        li.className = 'bb-cmd-item' + (i === active ? ' active' : '');
        const t = p.title.replace(/</g, '&lt;');
        const k = (p.id || '\u2014').replace(/</g, '&lt;');
        li.innerHTML = '<span>' + t + '</span><span class="bb-cmd-key">' + k + '</span>';
        li.addEventListener('click', () => { active = i; jumpActive(); });
        list.appendChild(li);
      });
    }
    function jumpActive(){
      const p = filtered[active];
      if (!p) return;
      hide();
      flashPanel(p.el);
    }
    function show(){
      panels = getPanels();
      filtered = panels.slice();
      active = 0;
      input.value = '';
      render();
      bar.hidden = false;
      setTimeout(() => input.focus(), 10);
    }
    function hide(){ bar.hidden = true; }

    input.addEventListener('input', () => {
      const q = input.value.toLowerCase().trim();
      filtered = q ? panels.filter(p => p.title.toLowerCase().includes(q) || (p.id || '').toLowerCase().includes(q)) : panels.slice();
      active = 0;
      render();
    });
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { e.preventDefault(); hide(); }
      else if (e.key === 'ArrowDown') { e.preventDefault(); active = Math.min(filtered.length - 1, active + 1); render(); }
      else if (e.key === 'ArrowUp')   { e.preventDefault(); active = Math.max(0, active - 1); render(); }
      else if (e.key === 'Enter')     { e.preventDefault(); jumpActive(); }
    });

    window.__bbCmdShow__ = show;
    window.__bbCmdHide__ = hide;
  }

  function ensureTickerTape(){
    if (document.getElementById('bb-ticker-tape')) return;
    const tape = document.createElement('div');
    tape.id = 'bb-ticker-tape';
    tape.innerHTML =
      '<div class="bb-tape-item" data-sym="BANKNIFTY"><span class="bb-tape-sym">BNF</span><span class="bb-tape-val">&mdash;</span><span class="bb-tape-chg flat">0.00%</span></div>' +
      '<div class="bb-tape-item" data-sym="NIFTY"><span class="bb-tape-sym">NF</span><span class="bb-tape-val">&mdash;</span><span class="bb-tape-chg flat">0.00%</span></div>' +
      '<div class="bb-tape-item" data-sym="MIDCPNIFTY"><span class="bb-tape-sym">MCN</span><span class="bb-tape-val">&mdash;</span><span class="bb-tape-chg flat">0.00%</span></div>' +
      '<div class="bb-tape-item"><span class="bb-tape-sym">IST</span><span class="bb-tape-val" id="bb-tape-clock">--:--:--</span></div>' +
      '<div class="bb-tape-item"><span class="bb-tape-sym">SESSION</span><span class="bb-tape-val" id="bb-tape-session">--</span></div>' +
      '<div class="bb-tape-item"><span class="bb-tape-sym">THEME</span><span class="bb-tape-val" id="bb-tape-theme">DEFAULT</span></div>';
    document.body.insertBefore(tape, document.body.firstChild);

    function tickClock(){
      const d = new Date();
      const hh = String(d.getHours()).padStart(2, '0');
      const mm = String(d.getMinutes()).padStart(2, '0');
      const ss = String(d.getSeconds()).padStart(2, '0');
      const ce = document.getElementById('bb-tape-clock');
      if (ce) ce.textContent = hh + ':' + mm + ':' + ss;
      const m = d.getHours() * 60 + d.getMinutes();
      const session = (m >= 555 && m <= 930) ? 'OPEN' : (m < 555 ? 'PRE' : 'CLOSED');
      const se = document.getElementById('bb-tape-session');
      if (se) se.textContent = session;
      const te = document.getElementById('bb-tape-theme');
      if (te) te.textContent = (document.documentElement.getAttribute('data-theme') === 'bloomberg') ? 'BLOOMBERG' : 'DEFAULT';
    }
    tickClock();
    setInterval(tickClock, 1000);

    const lastVals = {};
    async function pollTape(){
      try {
        const r = await fetch('/api/symbols');
        if (!r.ok) return;
        const d = await r.json();
        const rows = d.rows || d.symbols || [];
        rows.forEach(row => {
          const sym = row.symbol || row.name;
          const ltp = row.ltp != null ? row.ltp : (row.price != null ? row.price : row.last);
          const chg = row.change_pct != null ? row.change_pct : (row.changePct != null ? row.changePct : (row.chgPct != null ? row.chgPct : null));
          const item = tape.querySelector('.bb-tape-item[data-sym="' + sym + '"]');
          if (!item || ltp == null) return;
          const valEl = item.querySelector('.bb-tape-val');
          const chgEl = item.querySelector('.bb-tape-chg');
          const prev = lastVals[sym];
          if (valEl) valEl.textContent = (typeof ltp === 'number') ? ltp.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2}) : String(ltp);
          if (chgEl && chg != null) {
            const cls = chg > 0 ? 'up' : (chg < 0 ? 'down' : 'flat');
            const arr = chg > 0 ? '\u25B2' : (chg < 0 ? '\u25BC' : '\u2192');
            chgEl.className = 'bb-tape-chg ' + cls;
            chgEl.textContent = arr + ' ' + (chg > 0 ? '+' : '') + (typeof chg === 'number' ? chg.toFixed(2) : chg) + '%';
          }
          if (prev != null && typeof ltp === 'number' && ltp !== prev) {
            const dir = ltp > prev ? 'flash-up' : 'flash-down';
            item.classList.add(dir);
            setTimeout(() => { item.classList.remove(dir); }, 350);
          }
          if (typeof ltp === 'number') lastVals[sym] = ltp;
        });
      } catch(e){}
    }
    pollTape();
    setInterval(pollTape, 2500);
  }

  function ensureFKeyBar(){
    if (document.getElementById('bb-fkey-bar')) return;
    const bar = document.createElement('div');
    bar.id = 'bb-fkey-bar';
    bar.innerHTML =
      '<span class="bb-fk" data-action="cmd"><span class="bb-fk-key">/</span><span class="bb-fk-lbl">cmd</span></span>' +
      '<span class="bb-fk" data-jump="heatmap"><span class="bb-fk-key">H</span><span class="bb-fk-lbl">heatmap</span></span>' +
      '<span class="bb-fk" data-jump="regime"><span class="bb-fk-key">R</span><span class="bb-fk-lbl">regime</span></span>' +
      '<span class="bb-fk" data-jump="equity"><span class="bb-fk-key">E</span><span class="bb-fk-lbl">equity</span></span>' +
      '<span class="bb-fk" data-jump="trade"><span class="bb-fk-key">T</span><span class="bb-fk-lbl">trades</span></span>' +
      '<span class="bb-fk" data-jump="portfolio"><span class="bb-fk-key">P</span><span class="bb-fk-lbl">portfolio</span></span>' +
      '<span class="bb-fk" data-jump="risk"><span class="bb-fk-key">K</span><span class="bb-fk-lbl">risk</span></span>' +
      '<span class="bb-fk" data-action="theme"><span class="bb-fk-key">B</span><span class="bb-fk-lbl">bloomberg theme</span></span>';
    document.body.appendChild(bar);
    bar.querySelectorAll('.bb-fk').forEach(fk => {
      fk.addEventListener('click', () => {
        const jump = fk.getAttribute('data-jump');
        const action = fk.getAttribute('data-action');
        if (jump) jumpTo(jump);
        else if (action === 'cmd') window.__bbCmdShow__ && window.__bbCmdShow__();
        else if (action === 'theme') toggleTheme();
      });
    });
  }

  function isTyping(el){
    if (!el) return false;
    const t = (el.tagName || '').toUpperCase();
    return t === 'INPUT' || t === 'TEXTAREA' || el.isContentEditable;
  }
  document.addEventListener('keydown', (e) => {
    if (e.altKey || e.metaKey || e.ctrlKey) return;
    if (isTyping(e.target) && e.key !== 'Escape') return;
    const k = e.key;
    if (k === '/') { e.preventDefault(); window.__bbCmdShow__ && window.__bbCmdShow__(); }
    else if (k === 'Escape') { window.__bbCmdHide__ && window.__bbCmdHide__(); }
    else {
      const kl = k.toLowerCase();
      if (kl === 'h') { e.preventDefault(); jumpTo('heatmap'); }
      else if (kl === 'r') { e.preventDefault(); jumpTo('regime'); }
      else if (kl === 'e') { e.preventDefault(); jumpTo('equity'); }
      else if (kl === 't') { e.preventDefault(); jumpTo('trade'); }
      else if (kl === 'p') { e.preventDefault(); jumpTo('portfolio'); }
      else if (kl === 'k') { e.preventDefault(); jumpTo('risk'); }
      else if (kl === 'b') { e.preventDefault(); toggleTheme(); }
    }
  });

  function init(){
    ensureCommandBar();
    ensureTickerTape();
    ensureFKeyBar();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else setTimeout(init, 50);
})();

/* ===== Phase 9.8f.31: ticker tape data binding fix ===== */
(function _p98f_ticker_fix(){
  if (window.__P98F_TICKER_FIX__) return;
  window.__P98F_TICKER_FIX__ = true;
  const MAP = {"BANKNIFTY":"BNF","NIFTY":"NF","MIDCPNIFTY":"MCN"};
  function flashCell(el, up){
    if (!el) return;
    el.style.transition = "background 0.6s ease";
    el.style.background = up ? "rgba(0,255,127,0.35)" : "rgba(255,48,48,0.35)";
    setTimeout(function(){ el.style.background = "transparent"; }, 600);
  }
  async function update(){
    try {
      const r = await fetch("/api/symbols", {credentials:"same-origin"});
      if (!r.ok) return;
      const d = await r.json();
      const syms = d.symbols || {};
      document.querySelectorAll("#bb-ticker-tape .bb-tape-item[data-sym]").forEach(function(el){
        const key = MAP[el.dataset.sym] || el.dataset.sym;
        const sd = syms[key];
        if (!sd || sd.ltp == null) return;
        const ltp = +sd.ltp;
        const op = sd.ohlc_today && sd.ohlc_today.o;
        const chg = (op && op > 0) ? ((ltp - op) / op * 100) : 0;
        const v = el.querySelector(".bb-tape-val");
        const c = el.querySelector(".bb-tape-chg");
        if (v){
          const prev = v.dataset.prev ? +v.dataset.prev : null;
          v.textContent = "\u20b9" + ltp.toLocaleString("en-IN",{maximumFractionDigits:2});
          v.dataset.prev = String(ltp);
          if (prev != null && ltp !== prev) flashCell(v, ltp > prev);
        }
        if (c){
          c.textContent = (chg >= 0 ? "+" : "") + chg.toFixed(2) + "%";
          c.className = "bb-tape-chg " + (chg > 0 ? "up" : (chg < 0 ? "down" : "flat"));
        }
      });
    } catch(e){}
  }
  setTimeout(update, 500);
  setInterval(update, 2500);
})();

/* ===== Phase 9.8f.33: Rolling Risk-Adjusted Returns panel ===== */
(function _p98f_rolling_panel(){
  if (window.__P98F_ROLLING__) return;
  window.__P98F_ROLLING__ = true;
  function loadUplot(cb){
    if (typeof uPlot !== "undefined") return cb(true);
    const css = document.createElement("link"); css.rel="stylesheet"; css.href="https://unpkg.com/uplot@1.6.30/dist/uPlot.min.css"; document.head.appendChild(css);
    const s = document.createElement("script"); s.src="https://unpkg.com/uplot@1.6.30/dist/uPlot.iife.min.js"; s.onload=function(){cb(true);}; s.onerror=function(){cb(false);}; document.head.appendChild(s);
  }
  function makePanel(){
    if (document.getElementById("p98f-rolling-panel")) return;
    const sec = document.createElement("section"); sec.className="panel"; sec.id="p98f-rolling-panel";
    sec.innerHTML = "<div class=\"panel-header\"><div><h2>Rolling Risk-Adjusted Returns</h2><span class=\"muted\">20-day rolling \u00b7 annualized \u00d7 \u221a252 \u00b7 source: /api/rolling-metrics</span></div><span class=\"panel-badge\" style=\"background:rgba(255,140,0,.12);color:#ff8c00\">QUANT</span></div><div id=\"p98f-rolling-chart\" style=\"width:100%;height:380px;position:relative\"></div><div id=\"p98f-rolling-summary\" class=\"muted\" style=\"margin-top:24px;font-family:JetBrains Mono,Consolas,monospace;font-size:12px\">loading\u2026</div>";
    const anchors = document.querySelectorAll(".grid-2");
    const target = anchors[anchors.length - 1] || document.querySelector("main");
    if (target && target.parentNode) target.parentNode.insertBefore(sec, target.nextSibling);
    else if (target) target.appendChild(sec);
  }
  async function render(){
    try {
      const r = await fetch("/api/rolling-metrics?window=20", {credentials:"same-origin"});
      if (!r.ok) return;
      const d = await r.json();
      if (!d.ok || !d.rows || !d.rows.length){ const s=document.getElementById("p98f-rolling-summary"); if(s) s.textContent = "no data: " + (d.message||"empty"); return; }
      const xs = d.rows.map(function(rr){ return Math.floor(new Date(rr.date).getTime()/1000); });
      const sh = d.rows.map(function(rr){ return rr.sharpe; });
      const so = d.rows.map(function(rr){ return rr.sortino; });
      const ca = d.rows.map(function(rr){ return rr.calmar; });
      const el = document.getElementById("p98f-rolling-chart"); if (!el) return;
      const last = d.rows[d.rows.length - 1];
      const summ = document.getElementById("p98f-rolling-summary");
      if (summ) summ.innerHTML = "LATEST " + last.date + " \u00b7 Sharpe <b style=\"color:#00bfff\">" + (last.sharpe!=null?last.sharpe:"n/a") + "</b> \u00b7 Sortino <b style=\"color:#00ff7f\">" + (last.sortino!=null?last.sortino:"n/a") + "</b> \u00b7 Calmar <b style=\"color:#ff8c00\">" + (last.calmar!=null?last.calmar:"n/a") + "</b> \u00b7 n=" + last.n + " \u00b7 obs=" + d.rows.length;
      if (typeof uPlot === "undefined"){ el.innerHTML = "<div class=\"muted\" style=\"padding:20px\">uPlot CDN unavailable \u2014 see summary below</div>"; return; }
      el.innerHTML = "";
      const w = el.clientWidth || el.parentElement.clientWidth || 800;
      const opts = {width:w, height:340, scales:{x:{time:true}, y:{auto:true}, c:{auto:true}}, series:[{},{label:"Sharpe",stroke:"#00bfff",width:2},{label:"Sortino",stroke:"#00ff7f",width:2},{label:"Calmar",stroke:"#ff8c00",width:2,scale:"c"}], axes:[{stroke:"#888"},{stroke:"#888"},{scale:"c",side:1,stroke:"#ff8c00"}]};
      new uPlot(opts, [xs, sh, so, ca], el);
    } catch(e){ console.warn("rolling panel:", e); }
  }
  function init(){ makePanel(); loadUplot(function(){ render(); setInterval(render, 60000); }); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();

/* ===== Phase 9.8f.34: Regime Transition Matrix panel ===== */
(function _p98f_regime_hm(){
  if (window.__P98F_REGIME_HM__) return;
  window.__P98F_REGIME_HM__ = true;
  const REGIMES = ["TREND","RANGE","CHOP"];
  const COLORS = {TREND:"#00bfff", RANGE:"#ffa500", CHOP:"#ff4444"};
  function makePanel(){
    if (document.getElementById("p98f-regime-hm-panel")) return;
    const sec = document.createElement("section"); sec.className="panel"; sec.id="p98f-regime-hm-panel";
    sec.innerHTML = "<div class=\"panel-header\"><div><h2>Regime Transition Matrix</h2><span class=\"muted\">Markov chain \u00b7 daily ADX-14 split \u00b7 TREND/RANGE/CHOP \u00b7 source: /api/regime-transitions</span></div><span class=\"panel-badge\" style=\"background:rgba(0,191,255,.12);color:#00bfff\">MARKOV</span></div><div id=\"p98f-regime-hm-grid\" style=\"display:grid;grid-template-columns:90px repeat(3,1fr);gap:6px;margin-top:14px;font-family:JetBrains Mono,Consolas,monospace;font-size:13px\"></div><div id=\"p98f-regime-hm-note\" class=\"muted\" style=\"margin-top:10px;font-size:12px;line-height:1.6\">loading\u2026</div>";
    const anchor = document.getElementById("p98f-rolling-panel") || document.querySelectorAll(".grid-2")[document.querySelectorAll(".grid-2").length-1];
    if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(sec, anchor.nextSibling);
  }
  function cellBg(p, color){
    const r = parseInt(color.slice(1,3),16), g = parseInt(color.slice(3,5),16), b = parseInt(color.slice(5,7),16);
    return "rgba(" + r + "," + g + "," + b + "," + (0.08 + 0.72*p).toFixed(3) + ")";
  }
  async function render(){
    try {
      const r = await fetch("/api/regime-transitions", {credentials:"same-origin"});
      if (!r.ok) return;
      const d = await r.json();
      if (!d.ok){ const nn=document.getElementById("p98f-regime-hm-note"); if(nn) nn.textContent="no data: "+(d.message||"empty"); return; }
      const grid = document.getElementById("p98f-regime-hm-grid"); if (!grid) return;
      const counts = d.counts || {}, probs = d.probs || {};
      let html = "<div></div>";
      REGIMES.forEach(function(to){ html += "<div style=\"text-align:center;color:" + COLORS[to] + ";font-weight:700;padding:8px;letter-spacing:.5px\">\u2192 " + to + "</div>"; });
      REGIMES.forEach(function(from){
        html += "<div style=\"color:" + COLORS[from] + ";font-weight:700;padding:8px;display:flex;align-items:center;letter-spacing:.5px\">" + from + " \u2192</div>";
        REGIMES.forEach(function(to){
          const p = (probs[from] && probs[from][to] != null) ? probs[from][to] : 0;
          const c = (counts[from] && counts[from][to] != null) ? counts[from][to] : 0;
          const isDiag = (from === to);
          const cellColor = isDiag ? "#666666" : COLORS[to];
          html += "<div title=\"" + from + " \u2192 " + to + ": " + (p*100).toFixed(2) + "% (" + c + " obs)\" style=\"background:" + cellBg(p,cellColor) + ";padding:16px 12px;text-align:center;border-radius:6px;border:1px solid rgba(255,255,255,.08);transition:transform 0.2s\" onmouseover=\"this.style.transform=\u0027scale(1.03)\u0027\" onmouseout=\"this.style.transform=\u0027scale(1)\u0027\"><div style=\"font-size:20px;font-weight:800;color:" + (isDiag ? "#888" : COLORS[to]) + "\">" + (p*100).toFixed(1) + "%</div><div class=\"muted\" style=\"font-size:11px;margin-top:4px\">n=" + c + "</div></div>";
        });
      });
      grid.innerHTML = html;
      const note = document.getElementById("p98f-regime-hm-note");
      if (note){
        const trToRa = (probs.TREND && probs.TREND.RANGE) || 0;
        const raToTr = (probs.RANGE && probs.RANGE.TREND) || 0;
        const meanRev = (trToRa + raToTr) / 2;
        const verdict = meanRev > 0.4 ? "<b style=\"color:#00ff7f\">CONFIRMED</b>" : (meanRev > 0.25 ? "<b style=\"color:#ffa500\">MODERATE</b>" : "<b style=\"color:#ff4444\">WEAK</b>");
        note.innerHTML = "OBS " + (d.n_obs||0) + " transitions \u00b7 TREND\u2192RANGE <b style=\"color:#ffa500\">" + (trToRa*100).toFixed(1) + "%</b> \u00b7 RANGE\u2192TREND <b style=\"color:#00bfff\">" + (raToTr*100).toFixed(1) + "%</b> \u00b7 mean-reversion thesis: " + verdict + " (avg " + (meanRev*100).toFixed(1) + "%)";
      }
    } catch(e){ console.warn("regime hm:", e); }
  }
  function init(){ makePanel(); render(); setInterval(render, 60000); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();

/* ===== Phase 9.8f.35: uPlot legend styling + overlap fix ===== */
(function _p98f_legend_css(){
  if (window.__P98F_LEGEND_CSS__) return;
  window.__P98F_LEGEND_CSS__ = true;
  const style = document.createElement("style");
  style.textContent = "#p98f-rolling-chart{padding-bottom:8px}#p98f-rolling-chart .u-legend{font-family:JetBrains Mono,Consolas,monospace !important;font-size:11px !important;padding:10px 0 4px !important;border-top:1px solid rgba(128,128,128,.18) !important;margin-top:10px !important;background:transparent !important;text-align:left !important}#p98f-rolling-chart .u-legend th{color:#999 !important;font-weight:500 !important;padding-right:14px !important}#p98f-rolling-chart .u-legend td{padding-right:18px !important}#p98f-rolling-summary{border-top:1px solid rgba(128,128,128,.18) !important;padding-top:12px !important;letter-spacing:.3px}";
  document.head.appendChild(style);
})();

/* ===== Phase 9.8f.36: Intraday sparklines (375-bar session from intraday_candles) ===== */
(function _p98f_spark_intraday(){
  if (window.__P98F_SPARK_INTRADAY__) return;
  window.__P98F_SPARK_INTRADAY__ = true;
  const SYMS = ["BNF","NF","MCN"];
  const css = document.createElement("style");
  css.textContent = ".sc-spark{width:100%;height:46px;display:block;margin:8px 0 6px;border-radius:3px}";
  document.head.appendChild(css);
  function drawSpark(canvas, candles, openPrice){
    if (!canvas || !candles || !candles.length) return;
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const W = Math.max(rect.width || canvas.parentElement.clientWidth || 200, 100);
    const H = Math.max(rect.height || 46, 32);
    canvas.width = Math.floor(W * dpr); canvas.height = Math.floor(H * dpr);
    canvas.style.width = W + "px"; canvas.style.height = H + "px";
    const ctx = canvas.getContext("2d"); ctx.setTransform(1,0,0,1,0,0); ctx.scale(dpr, dpr); ctx.clearRect(0, 0, W, H);
    const closes = candles.map(function(c){ return c[4]; });
    const n = closes.length;
    let min = Math.min.apply(null, closes); let max = Math.max.apply(null, closes);
    min = Math.min(min, openPrice); max = Math.max(max, openPrice);
    const pad = (max - min) * 0.12 || 1; min -= pad; max += pad;
    const last = closes[n - 1];
    const isUp = last >= openPrice;
    const color = isUp ? "#3ce04f" : "#ff5566";
    const fill = isUp ? "rgba(60,224,79,0.12)" : "rgba(255,85,102,0.12)";
    const baseY = H - ((openPrice - min) / (max - min)) * H;
    ctx.beginPath(); ctx.setLineDash([2,3]); ctx.strokeStyle = "rgba(160,160,160,0.45)"; ctx.lineWidth = 1; ctx.moveTo(0, baseY); ctx.lineTo(W, baseY); ctx.stroke(); ctx.setLineDash([]);
    ctx.beginPath();
    for (let i = 0; i < n; i++){ const x = (i / Math.max(n - 1, 1)) * W; const y = H - ((closes[i] - min) / (max - min)) * H; if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); }
    ctx.lineTo(W, H); ctx.lineTo(0, H); ctx.closePath(); ctx.fillStyle = fill; ctx.fill();
    ctx.beginPath();
    for (let i = 0; i < n; i++){ const x = (i / Math.max(n - 1, 1)) * W; const y = H - ((closes[i] - min) / (max - min)) * H; if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); }
    ctx.strokeStyle = color; ctx.lineWidth = 1.4; ctx.lineJoin = "round"; ctx.stroke();
    const lastX = W - 2; const lastY = H - ((last - min) / (max - min)) * H;
    ctx.beginPath(); ctx.arc(lastX, lastY, 2.5, 0, Math.PI * 2); ctx.fillStyle = color; ctx.fill();
    ctx.beginPath(); ctx.arc(lastX, lastY, 5, 0, Math.PI * 2); ctx.strokeStyle = color; ctx.globalAlpha = 0.35; ctx.lineWidth = 1; ctx.stroke(); ctx.globalAlpha = 1;
  }
  async function update(){
    try {
      const r = await fetch("/api/symbols", {credentials:"same-origin"});
      if (!r.ok) return;
      const d = await r.json();
      const syms = d.symbols || {};
      SYMS.forEach(function(s){
        const sd = syms[s]; if (!sd) return;
        const canvas = document.getElementById("spark-" + s);
        const candles = sd.intraday_candles || [];
        const openPrice = (sd.ohlc_today && sd.ohlc_today.o) || (candles[0] && candles[0][1]) || sd.ltp;
        if (openPrice != null) drawSpark(canvas, candles, +openPrice);
      });
    } catch(e){ console.warn("spark intraday:", e); }
  }
  setTimeout(update, 700);
  setInterval(update, 5000);
  let rT; window.addEventListener("resize", function(){ clearTimeout(rT); rT = setTimeout(update, 200); });
})();

/* ===== Phase 9.8f.37: Level 2 Order Book panel ===== */
(function _p98f_l2_book(){
  if (window.__P98F_L2__) return;
  window.__P98F_L2__ = true;
  const SYMS = ["BNF","NF","MCN"];
  const NAMES = {BNF:"BANKNIFTY", NF:"NIFTY", MCN:"MIDCPNIFTY"};
  function makePanel(){
    if (document.getElementById("p98f-l2-panel")) return;
    const sec = document.createElement("section"); sec.className="panel"; sec.id="p98f-l2-panel";
    sec.innerHTML = "<div class=\"panel-header\"><div><h2>Level 2 Order Book</h2><span class=\"muted\">Top 5 bids/asks per symbol \u00b7 source: /api/symbols depth \u00b7 live snapshot \u00b7 polled 3s</span></div><span class=\"panel-badge\" style=\"background:rgba(255,140,0,.12);color:#ff8c00\">DEPTH</span></div><div id=\"p98f-l2-grid\" style=\"display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:14px;font-family:JetBrains Mono,Consolas,monospace;font-size:11px\"><div class=\"muted\">loading\u2026</div></div>";
    const anchor = document.getElementById("p98f-regime-hm-panel") || document.getElementById("p98f-rolling-panel");
    if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(sec, anchor.nextSibling);
  }
  function fmt(n){ return Number(n).toLocaleString("en-IN"); }
  function renderBook(sym, sd){
    const depth = (sd && sd.depth) || {bids:[], asks:[]};
    const bids = depth.bids || []; const asks = depth.asks || [];
    if (!bids.length && !asks.length) return "<div style=\"color:#888;padding:20px;text-align:center\">no depth data</div>";
    const allSizes = bids.map(function(x){return x.quantity;}).concat(asks.map(function(x){return x.quantity;}));
    const maxSize = Math.max.apply(null, allSizes.concat([1]));
    let html = "<div style=\"font-weight:700;color:#ddd;padding:6px 0;border-bottom:1px solid rgba(255,255,255,.1);margin-bottom:8px;display:flex;justify-content:space-between;align-items:center\"><span>" + sym + " <span style=\"color:#888;font-weight:400;font-size:10px;letter-spacing:.4px\">" + NAMES[sym] + "</span></span><span style=\"color:#888;font-weight:400;font-size:10px\">LTP " + fmt(sd && sd.ltp || 0) + "</span></div>";
    html += "<div style=\"display:grid;grid-template-columns:1.2fr 1fr 0.5fr;gap:4px;color:#666;font-size:9px;letter-spacing:.6px;padding:0 4px 4px\"><div>PRICE</div><div style=\"text-align:right\">SIZE</div><div style=\"text-align:right\">ORD</div></div>";
    asks.slice().reverse().forEach(function(a){
      const w = (a.quantity / maxSize) * 100;
      html += "<div style=\"position:relative;display:grid;grid-template-columns:1.2fr 1fr 0.5fr;gap:4px;padding:3px 4px;background:linear-gradient(to left,rgba(255,85,102,0.18) " + w.toFixed(1) + "%,transparent " + w.toFixed(1) + "%);color:#ff5566;border-radius:2px;margin:1px 0\"><div>" + fmt(a.price) + "</div><div style=\"text-align:right;color:#ddd\">" + fmt(a.quantity) + "</div><div style=\"text-align:right;color:#888\">" + a.orders + "</div></div>";
    });
    const bestBid = bids[0] && bids[0].price; const bestAsk = asks[0] && asks[0].price;
    const spread = (bestAsk && bestBid) ? (bestAsk - bestBid) : 0;
    const bps = (bestBid && spread) ? (spread / bestBid * 10000) : 0;
    html += "<div style=\"text-align:center;padding:7px 0;margin:6px 0;background:rgba(255,255,255,.04);border-radius:3px;font-weight:600;color:#ddd;letter-spacing:.4px;border-top:1px dashed rgba(255,255,255,.1);border-bottom:1px dashed rgba(255,255,255,.1)\">SPREAD " + spread.toFixed(2) + " <span style=\"color:#888;font-weight:400;margin-left:6px\">(" + bps.toFixed(1) + " bps)</span></div>";
    bids.forEach(function(b){
      const w = (b.quantity / maxSize) * 100;
      html += "<div style=\"position:relative;display:grid;grid-template-columns:1.2fr 1fr 0.5fr;gap:4px;padding:3px 4px;background:linear-gradient(to left,rgba(60,224,79,0.18) " + w.toFixed(1) + "%,transparent " + w.toFixed(1) + "%);color:#3ce04f;border-radius:2px;margin:1px 0\"><div>" + fmt(b.price) + "</div><div style=\"text-align:right;color:#ddd\">" + fmt(b.quantity) + "</div><div style=\"text-align:right;color:#888\">" + b.orders + "</div></div>";
    });
    const totBid = bids.reduce(function(a,b){return a+b.quantity;}, 0);
    const totAsk = asks.reduce(function(a,b){return a+b.quantity;}, 0);
    const imb = (totBid + totAsk > 0) ? ((totBid - totAsk) / (totBid + totAsk)) : 0;
    const imbColor = imb > 0.15 ? "#3ce04f" : (imb < -0.15 ? "#ff5566" : "#888");
    const imbLbl = imb > 0.15 ? "BID-HEAVY" : (imb < -0.15 ? "ASK-HEAVY" : "BALANCED");
    html += "<div style=\"margin-top:8px;padding:6px;background:rgba(255,255,255,.03);border-radius:3px;font-size:10px;color:#888;display:flex;justify-content:space-between\"><span>BID \u03a3 " + fmt(totBid) + "</span><span style=\"color:" + imbColor + ";font-weight:600\">" + imbLbl + " " + (imb*100).toFixed(1) + "%</span><span>ASK \u03a3 " + fmt(totAsk) + "</span></div>";
    return html;
  }
  async function update(){
    try {
      const r = await fetch("/api/symbols", {credentials:"same-origin"});
      if (!r.ok) return;
      const d = await r.json();
      const syms = d.symbols || {};
      const grid = document.getElementById("p98f-l2-grid"); if (!grid) return;
      let html = "";
      SYMS.forEach(function(s){ html += "<div>" + renderBook(s, syms[s] || {}) + "</div>"; });
      grid.innerHTML = html;
    } catch(e){ console.warn("L2:", e); }
  }
  function init(){ makePanel(); update(); setInterval(update, 3000); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();

/* ===== Phase 9.8f.38: Trade Distribution scatter ===== */
(function _p98f_trade_scatter(){
  if (window.__P98F_SCATTER__) return;
  window.__P98F_SCATTER__ = true;
  let trades = [], canvas;
  function makePanel(){
    if (document.getElementById("p98f-scatter-panel")) return;
    const sec = document.createElement("section"); sec.className="panel"; sec.id="p98f-scatter-panel";
    sec.innerHTML = "<div class=\"panel-header\"><div><h2>Trade Distribution</h2><span class=\"muted\">Entry-hour \u00d7 bars-held \u00d7 |P&amp;L| \u00b7 hover for detail \u00b7 source: /api/trades</span></div><span class=\"panel-badge\" style=\"background:rgba(60,224,79,.12);color:#3ce04f\">FORENSIC</span></div><div style=\"position:relative;margin-top:14px\"><canvas id=\"p98f-scatter-canvas\" style=\"width:100%;height:340px;display:block\"></canvas><div id=\"p98f-scatter-tip\" style=\"position:absolute;display:none;padding:8px 10px;background:rgba(15,20,30,.96);border:1px solid rgba(255,255,255,.18);border-radius:4px;font-family:JetBrains Mono,Consolas,monospace;font-size:11px;color:#ddd;pointer-events:none;z-index:10;line-height:1.6;white-space:nowrap\"></div></div><div id=\"p98f-scatter-foot\" class=\"muted\" style=\"margin-top:10px;font-size:12px;padding-top:10px;border-top:1px solid rgba(128,128,128,.18);font-family:JetBrains Mono,Consolas,monospace\">loading\u2026</div>";
    const anchor = document.getElementById("p98f-l2-panel") || document.getElementById("p98f-regime-hm-panel");
    if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(sec, anchor.nextSibling);
  }
  function tradeHour(t){ const ts = (t.entry_ts || "").replace(" ", "T", 1); try { const d = new Date(ts); return d.getHours() + d.getMinutes()/60; } catch(e){ return 12; } }
  function drawScatter(){
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1; const rect = canvas.getBoundingClientRect();
    const W = rect.width || 800, H = rect.height || 340;
    canvas.width = Math.floor(W*dpr); canvas.height = Math.floor(H*dpr);
    canvas.style.width = W+"px"; canvas.style.height = H+"px";
    const ctx = canvas.getContext("2d"); ctx.setTransform(1,0,0,1,0,0); ctx.scale(dpr,dpr); ctx.clearRect(0,0,W,H);
    const padL=50, padR=20, padT=16, padB=36;
    const pw = W-padL-padR, ph = H-padT-padB;
    const xMin=9, xMax=15.5;
    const yMax = Math.max(50, Math.max.apply(null, trades.map(function(t){ return t.bars_held||0; }).concat([10])) + 5);
    ctx.strokeStyle = "rgba(128,128,128,.15)"; ctx.lineWidth = 1;
    for (let h=9; h<=15; h++){ const x = padL + ((h-xMin)/(xMax-xMin))*pw; ctx.beginPath(); ctx.moveTo(x,padT); ctx.lineTo(x,padT+ph); ctx.stroke(); }
    for (let i=0; i<=5; i++){ const y = padT + (i/5)*ph; ctx.beginPath(); ctx.moveTo(padL,y); ctx.lineTo(W-padR,y); ctx.stroke(); }
    ctx.fillStyle = "#888"; ctx.font = "10px JetBrains Mono, monospace"; ctx.textAlign = "center";
    for (let h=9; h<=15; h++){ const x = padL + ((h-xMin)/(xMax-xMin))*pw; ctx.fillText(h+":00", x, H-padB+16); }
    ctx.textAlign = "right";
    for (let i=0; i<=5; i++){ const y = padT + (i/5)*ph; const val = Math.round(yMax * (1 - i/5)); ctx.fillText(val+"b", padL-6, y+3); }
    ctx.textAlign = "left"; ctx.fillStyle = "#666"; ctx.font = "9px JetBrains Mono, monospace";
    ctx.fillText("ENTRY HOUR (IST)", padL, H-4); ctx.save(); ctx.translate(12, padT+ph/2); ctx.rotate(-Math.PI/2); ctx.textAlign = "center"; ctx.fillText("BARS HELD", 0, 0); ctx.restore();
    ctx.strokeStyle = "rgba(255,200,0,.25)"; ctx.lineWidth = 1; ctx.setLineDash([3,3]);
    const x915 = padL + ((9.25-xMin)/(xMax-xMin))*pw; const x1530 = padL + ((15.5-xMin)/(xMax-xMin))*pw;
    ctx.beginPath(); ctx.moveTo(x915,padT); ctx.lineTo(x915,padT+ph); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x1530,padT); ctx.lineTo(x1530,padT+ph); ctx.stroke();
    ctx.setLineDash([]);
    const maxAbsPnl = Math.max.apply(null, trades.map(function(t){ return Math.abs(t.pnl||0); }).concat([1]));
    trades.forEach(function(t){
      const hr = tradeHour(t); const bh = t.bars_held||0;
      const x = padL + ((hr-xMin)/(xMax-xMin))*pw; const y = padT + (1 - bh/yMax)*ph;
      const sz = 4 + Math.log(Math.abs(t.pnl||0)+1) / Math.log(maxAbsPnl+1) * 18;
      const col = (t.pnl||0) > 0 ? "#3ce04f" : "#ff5566";
      ctx.beginPath(); ctx.arc(x, y, sz, 0, Math.PI*2); ctx.fillStyle = col + "55"; ctx.fill();
      ctx.strokeStyle = col; ctx.lineWidth = 1.5; ctx.stroke();
      t._x = x; t._y = y; t._r = sz;
    });
  }
  function update(){
    fetch("/api/trades", {credentials:"same-origin"}).then(function(r){ return r.ok ? r.json() : null; }).then(function(d){
      if (!d || !d.trades) return;
      trades = d.trades; drawScatter();
      const morn = trades.filter(function(t){ return tradeHour(t) < 12; });
      const aft = trades.filter(function(t){ return tradeHour(t) >= 12; });
      const winM = morn.filter(function(t){ return (t.pnl||0) > 0; }).length;
      const winA = aft.filter(function(t){ return (t.pnl||0) > 0; }).length;
      const sumM = morn.reduce(function(a,b){ return a + (b.pnl||0); }, 0);
      const sumA = aft.reduce(function(a,b){ return a + (b.pnl||0); }, 0);
      const f = document.getElementById("p98f-scatter-foot"); if (!f) return;
      const fmtR = function(x){ return "\u20b9" + Math.round(x).toLocaleString("en-IN"); };
      f.innerHTML = "<b style=\"color:#ddd\">N=" + trades.length + "</b> trades \u00b7 MORN (9-12) <b style=\"color:#00bfff\">" + morn.length + "</b> trades, " + (morn.length ? Math.round(winM/morn.length*100) : 0) + "% win, " + fmtR(sumM) + " \u00b7 AFT (12-15:30) <b style=\"color:#ff8c00\">" + aft.length + "</b> trades, " + (aft.length ? Math.round(winA/aft.length*100) : 0) + "% win, " + fmtR(sumA);
    }).catch(function(){});
  }
  function hover(e){
    if (!trades.length || !canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    const tip = document.getElementById("p98f-scatter-tip"); if (!tip) return;
    for (let i = trades.length - 1; i >= 0; i--){
      const t = trades[i]; if (t._x == null) continue;
      const dx = mx - t._x, dy = my - t._y;
      if (dx*dx + dy*dy <= (t._r+2) * (t._r+2)){
        tip.style.display = "block"; tip.style.left = Math.min(mx+12, rect.width-260) + "px"; tip.style.top = Math.max(my-12, 0) + "px";
        const col = (t.pnl||0) > 0 ? "#3ce04f" : "#ff5566";
        tip.innerHTML = "<b style=\"color:#ddd\">" + (t.entry_ts||"").slice(0,16) + "</b><br>" + (t.side||"?") + " " + (t.qty||"?") + " @ " + Number(t.entry||0).toFixed(2) + " \u2192 " + Number(t.exit||0).toFixed(2) + "<br>P&amp;L <b style=\"color:" + col + "\">\u20b9" + Math.round(t.pnl||0).toLocaleString("en-IN") + "</b><br>Reason <b style=\"color:#ddd\">" + (t.reason||"?") + "</b> \u00b7 Bars " + (t.bars_held||0);
        return;
      }
    }
    tip.style.display = "none";
  }
  function init(){
    makePanel();
    canvas = document.getElementById("p98f-scatter-canvas");
    if (canvas){ canvas.addEventListener("mousemove", hover); canvas.addEventListener("mouseleave", function(){ const tip = document.getElementById("p98f-scatter-tip"); if (tip) tip.style.display = "none"; }); }
    update(); setInterval(update, 30000);
    let rT; window.addEventListener("resize", function(){ clearTimeout(rT); rT = setTimeout(drawScatter, 200); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();

/* ===== Phase 9.8f.39: Z-Score Live Gauges ===== */
(function _p98f_zscore(){
  if (window.__P98F_ZSCORE__) return;
  window.__P98F_ZSCORE__ = true;
  const SYMS = ["BNF","NF","MCN"];
  const NAMES = {BNF:"BANKNIFTY", NF:"NIFTY", MCN:"MIDCPNIFTY"};
  function makePanel(){
    if (document.getElementById("p98f-z-panel")) return;
    const sec = document.createElement("section"); sec.className="panel"; sec.id="p98f-z-panel";
    sec.innerHTML = "<div class=\"panel-header\"><div><h2>Z-Score Live Gauges</h2><span class=\"muted\">Mean-reversion signal per symbol \u00b7 gauge shows current z within entry/stop bands \u00b7 polled 3s</span></div><span class=\"panel-badge\" style=\"background:rgba(0,191,255,.12);color:#00bfff\">SIGNAL</span></div><div id=\"p98f-z-grid\" style=\"display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin-top:14px;font-family:JetBrains Mono,Consolas,monospace\"><div class=\"muted\">loading\u2026</div></div>";
    const anchor = document.getElementById("p98f-scatter-panel") || document.getElementById("p98f-l2-panel");
    if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(sec, anchor.nextSibling);
  }
  function zoneColor(z, ze, zs){ const a = Math.abs(z); if (a >= zs) return "#ff5566"; if (a >= ze) return "#ff8c00"; return "#888"; }
  function zoneLabel(z, ze, zs){ const a = Math.abs(z); if (a >= zs) return "BEYOND-STOP"; if (a >= ze) return z > 0 ? "ABOVE-ENTRY (SHORT)" : "BELOW-ENTRY (LONG)"; return "NEUTRAL ZONE"; }
  function renderGauge(sym, sd){
    if (!sd) return "<div class=\"muted\" style=\"padding:20px;text-align:center\">no data</div>";
    const z = Number(sd.z || 0); const ze = Number(sd.z_entry || 1.5); const zs = Number(sd.z_stop || 3.0);
    const mu = Number(sd.mean || 0); const sg = Number(sd.std || 0); const ltp = Number(sd.ltp || 0);
    const state = (sd.state || "idle").toUpperCase();
    const range = zs * 1.1;
    const zPct = Math.max(0, Math.min(100, ((z + range) / (2 * range)) * 100));
    const elP = ((-ze + range) / (2 * range)) * 100;
    const ehP = ((ze + range) / (2 * range)) * 100;
    const slP = ((-zs + range) / (2 * range)) * 100;
    const shP = ((zs + range) / (2 * range)) * 100;
    const color = zoneColor(z, ze, zs); const label = zoneLabel(z, ze, zs);
    let h = "<div style=\"padding:12px;background:rgba(255,255,255,.02);border-radius:6px;border:1px solid rgba(255,255,255,.06)\">";
    h += "<div style=\"display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px\"><div><span style=\"font-weight:700;color:#ddd\">" + sym + "</span> <span style=\"color:#888;font-size:10px;letter-spacing:.4px\">" + NAMES[sym] + "</span></div><span style=\"font-size:9px;color:#888;letter-spacing:.4px\">LTP " + ltp.toLocaleString("en-IN") + "</span></div>";
    h += "<div style=\"display:flex;align-items:baseline;gap:8px;margin-bottom:10px\"><span style=\"font-size:28px;font-weight:700;color:" + color + ";line-height:1;font-variant-numeric:tabular-nums\">" + z.toFixed(2) + "</span><span style=\"font-size:10px;color:" + color + ";letter-spacing:.4px\">" + label + "</span></div>";
    h += "<div style=\"position:relative;height:16px;background:linear-gradient(to right,rgba(255,85,102,.25) 0%,rgba(255,85,102,.25) " + slP.toFixed(1) + "%,rgba(255,140,0,.2) " + slP.toFixed(1) + "%,rgba(255,140,0,.2) " + elP.toFixed(1) + "%,rgba(128,128,128,.15) " + elP.toFixed(1) + "%,rgba(128,128,128,.15) " + ehP.toFixed(1) + "%,rgba(255,140,0,.2) " + ehP.toFixed(1) + "%,rgba(255,140,0,.2) " + shP.toFixed(1) + "%,rgba(255,85,102,.25) " + shP.toFixed(1) + "%);border-radius:3px;border:1px solid rgba(255,255,255,.08)\">";
    h += "<div style=\"position:absolute;top:-2px;bottom:-2px;left:50%;width:1px;background:rgba(255,255,255,.45)\"></div>";
    h += "<div style=\"position:absolute;top:-3px;bottom:-3px;left:" + elP.toFixed(1) + "%;width:1px;background:#ff8c00;opacity:.7\"></div>";
    h += "<div style=\"position:absolute;top:-3px;bottom:-3px;left:" + ehP.toFixed(1) + "%;width:1px;background:#ff8c00;opacity:.7\"></div>";
    h += "<div style=\"position:absolute;top:-3px;bottom:-3px;left:" + slP.toFixed(1) + "%;width:1px;background:#ff5566;opacity:.7\"></div>";
    h += "<div style=\"position:absolute;top:-3px;bottom:-3px;left:" + shP.toFixed(1) + "%;width:1px;background:#ff5566;opacity:.7\"></div>";
    h += "<div style=\"position:absolute;top:-4px;left:" + zPct.toFixed(1) + "%;transform:translateX(-50%);width:14px;height:24px;background:" + color + ";border-radius:2px;box-shadow:0 0 10px " + color + "aa\"></div>";
    h += "</div>";
    h += "<div style=\"display:flex;justify-content:space-between;margin-top:6px;font-size:9px;color:#666;letter-spacing:.3px\"><span>\u2212" + range.toFixed(1) + "</span><span style=\"color:#ff5566\">\u2212" + zs.toFixed(1) + "</span><span style=\"color:#ff8c00\">\u2212" + ze.toFixed(1) + "</span><span style=\"color:#aaa\">0 \u03bc</span><span style=\"color:#ff8c00\">+" + ze.toFixed(1) + "</span><span style=\"color:#ff5566\">+" + zs.toFixed(1) + "</span><span>+" + range.toFixed(1) + "</span></div>";
    h += "<div style=\"margin-top:10px;font-size:10px;color:#888;display:flex;justify-content:space-between;padding-top:8px;border-top:1px solid rgba(255,255,255,.05)\"><span>\u03bc <b style=\"color:#ddd\">" + mu.toFixed(2) + "</b></span><span>\u03c3 <b style=\"color:#ddd\">" + sg.toFixed(2) + "</b></span><span>entry <b style=\"color:#ff8c00\">\u00b1" + ze.toFixed(2) + "</b></span><span>stop <b style=\"color:#ff5566\">\u00b1" + zs.toFixed(2) + "</b></span></div>";
    h += "<div style=\"margin-top:6px;font-size:9px;color:#666;text-align:right;letter-spacing:.3px\">state <b style=\"color:#ddd\">" + state + "</b></div>";
    h += "</div>"; return h;
  }
  function update(){
    fetch("/api/symbols", {credentials:"same-origin"}).then(function(r){ return r.ok ? r.json() : null; }).then(function(d){
      if (!d) return;
      const syms = d.symbols || {};
      const grid = document.getElementById("p98f-z-grid"); if (!grid) return;
      grid.innerHTML = SYMS.map(function(s){ return renderGauge(s, syms[s]); }).join("");
    }).catch(function(){});
  }
  function init(){ makePanel(); update(); setInterval(update, 3000); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();

/* ===== Phase 9.8f.40: Monte Carlo Distribution panel ===== */
(function _p98f_mc(){
  if (window.__P98F_MC__) return;
  window.__P98F_MC__ = true;
  function makePanel(){
    if (document.getElementById("p98f-mc-panel")) return;
    const sec = document.createElement("section"); sec.className="panel"; sec.id="p98f-mc-panel";
    sec.innerHTML = "<div class=\"panel-header\"><div><h2>Monte Carlo Distribution</h2><span class=\"muted\">10k-sim bootstrap \u00b7 p5/p25/p50/p75/p95 fan \u00b7 source: /api/monte-carlo</span></div><span class=\"panel-badge\" style=\"background:rgba(180,120,255,.12);color:#b478ff\">BOOTSTRAP</span></div><div id=\"p98f-mc-box\" style=\"display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin-top:14px;font-family:JetBrains Mono,Consolas,monospace\"><div class=\"muted\">loading\u2026</div></div><div style=\"margin-top:18px;padding-top:14px;border-top:1px solid rgba(128,128,128,.18)\"><div style=\"font-size:10px;color:#888;letter-spacing:.5px;margin-bottom:10px;font-family:JetBrains Mono,monospace\">PROP-FIRM &amp; OUTCOME PROBABILITIES</div><div id=\"p98f-mc-prop\" style=\"display:grid;grid-template-columns:repeat(4,1fr);gap:10px;font-family:JetBrains Mono,Consolas,monospace\"></div></div><div id=\"p98f-mc-foot\" class=\"muted\" style=\"margin-top:14px;font-size:11px;padding-top:10px;border-top:1px solid rgba(128,128,128,.18);font-family:JetBrains Mono,Consolas,monospace\"></div>";
    const anchor = document.getElementById("p98f-z-panel") || document.getElementById("p98f-scatter-panel");
    if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(sec, anchor.nextSibling);
  }
  function renderBox(metric, vals, fmt, color){
    const min = vals.p5, max = vals.p95; const range = (max - min) || 1;
    function pct(v){ return Math.max(0, Math.min(100, ((v - min) / range) * 100)); }
    const p25P = pct(vals.p25), p50P = pct(vals.p50), p75P = pct(vals.p75);
    let h = "<div style=\"padding:12px;background:rgba(255,255,255,.02);border-radius:6px;border:1px solid rgba(255,255,255,.06)\">";
    h += "<div style=\"font-weight:700;color:#ddd;letter-spacing:.5px;font-size:10px;margin-bottom:4px;text-transform:uppercase\">" + metric + "</div>";
    h += "<div style=\"font-size:24px;font-weight:700;color:" + color + ";line-height:1;font-variant-numeric:tabular-nums;margin-bottom:14px\">" + fmt(vals.p50) + " <span style=\"font-size:9px;color:#888;font-weight:400;letter-spacing:.4px\">MEDIAN</span></div>";
    h += "<div style=\"position:relative;height:28px;margin:8px 4px\">";
    h += "<div style=\"position:absolute;top:50%;left:0;right:0;height:1px;background:" + color + "99;transform:translateY(-50%)\"></div>";
    h += "<div style=\"position:absolute;top:25%;bottom:25%;left:0;width:2px;background:" + color + "\"></div>";
    h += "<div style=\"position:absolute;top:25%;bottom:25%;right:0;width:2px;background:" + color + "\"></div>";
    h += "<div style=\"position:absolute;top:15%;bottom:15%;left:" + p25P.toFixed(1) + "%;width:" + (p75P - p25P).toFixed(1) + "%;background:" + color + "33;border:1px solid " + color + ";border-radius:2px\"></div>";
    h += "<div style=\"position:absolute;top:5%;bottom:5%;left:" + p50P.toFixed(1) + "%;width:2px;background:" + color + "\"></div>";
    h += "</div>";
    h += "<div style=\"display:flex;justify-content:space-between;margin-top:6px;font-size:9px;color:#666;letter-spacing:.3px\"><span><b style=\"color:#888\">p5</b> " + fmt(vals.p5) + "</span><span><b style=\"color:#888\">p25</b> " + fmt(vals.p25) + "</span><span><b style=\"color:" + color + "\">p50</b> " + fmt(vals.p50) + "</span><span><b style=\"color:#888\">p75</b> " + fmt(vals.p75) + "</span><span><b style=\"color:#888\">p95</b> " + fmt(vals.p95) + "</span></div>";
    h += "<div style=\"margin-top:8px;padding-top:6px;border-top:1px solid rgba(255,255,255,.05);font-size:9px;color:#666;text-align:right;letter-spacing:.3px\">\u03bc " + fmt(vals.mean) + " \u00b7 \u03c3 " + fmt(vals.std) + "</div>";
    h += "</div>"; return h;
  }
  function renderProp(label, pct, lowerBetter){
    const eff = lowerBetter ? (100 - pct) : pct;
    const color = eff >= 60 ? "#3ce04f" : (eff >= 40 ? "#ff8c00" : (eff >= 25 ? "#ffc833" : "#ff5566"));
    let h = "<div style=\"padding:10px;background:rgba(255,255,255,.02);border-radius:5px;border:1px solid rgba(255,255,255,.06);text-align:center\">";
    h += "<div style=\"font-size:20px;font-weight:700;color:" + color + ";line-height:1;font-variant-numeric:tabular-nums\">" + pct.toFixed(1) + "<span style=\"font-size:11px;font-weight:400\">%</span></div>";
    h += "<div style=\"font-size:9px;color:#888;letter-spacing:.4px;margin-top:5px;text-transform:uppercase\">" + label + "</div>";
    h += "</div>"; return h;
  }
  function update(){
    fetch("/api/monte-carlo").then(function(r){ return r.ok ? r.json() : null; }).then(function(j){
      if (!j || !j.ok || !j.data) return;
      const d = j.data;
      const fmtPct = function(v){ return v.toFixed(2) + "%"; };
      const fmtNum = function(v){ return v.toFixed(2); };
      const box = document.getElementById("p98f-mc-box"); if (!box) return;
      box.innerHTML = renderBox("Return %", d.return_pct, fmtPct, "#3ce04f") + renderBox("Sharpe", d.sharpe, fmtNum, "#00bfff") + renderBox("Max Drawdown %", d.max_dd_pct, fmtPct, "#ff5566");
      const prop = document.getElementById("p98f-mc-prop"); if (!prop || !d.prop_firm) return;
      const pf = d.prop_firm;
      prop.innerHTML = renderProp("FTMO 1st", pf.prob_pass_ftmo_1st || 0) + renderProp("FTMO 2p1", pf.prob_pass_ftmo_2p1 || 0) + renderProp("TopStep", pf.prob_pass_topstep || 0) + renderProp("Hola", pf.prob_pass_hola || 0) + renderProp("Return \u2265 5%", pf.prob_return_ge_5 || 0) + renderProp("Return \u2265 10%", pf.prob_return_ge_10 || 0) + renderProp("Losing Month", pf.prob_losing_month || 0, true) + renderProp("DD safe 8%", pf.prob_dd_safe_8 || 0);
      const f = document.getElementById("p98f-mc-foot"); if (!f) return;
      const wr = ((d.input_trades||{}).win_rate || 0) * 100;
      const mp = Math.round((d.input_trades||{}).mean_pnl || 0);
      f.innerHTML = "Bootstrap from <b style=\"color:#ddd\">" + (d.n_trades||0) + "</b> backtest trades \u00b7 <b style=\"color:#ddd\">" + (d.n_sims||0).toLocaleString("en-IN") + "</b> simulations \u00b7 input win-rate <b style=\"color:#ddd\">" + wr.toFixed(1) + "%</b> \u00b7 mean P&amp;L/trade <b style=\"color:#ddd\">\u20b9" + mp.toLocaleString("en-IN") + "</b>";
    }).catch(function(){});
  }
  function init(){ makePanel(); update(); setInterval(update, 60000); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();

/* ===== Phase 9.8f.41: Exit Reasons Breakdown donut ===== */
(function _p98f_reasons(){
  if (window.__P98F_REASONS__) return;
  window.__P98F_REASONS__ = true;
  const COLORS = {"TARGET":"#3ce04f","STOP_LOSS":"#ff5566","TIME_STOP_HL":"#ff8c00","TIME_STOP_LL":"#ffc833","Z_VEL_STALL":"#00bfff","EOD":"#b478ff","KILL_SWITCH":"#ff3322","MANUAL":"#888"};
  function colorFor(r){ return COLORS[r] || "#888"; }
  function makePanel(){
    if (document.getElementById("p98f-reasons-panel")) return;
    const sec = document.createElement("section"); sec.className="panel"; sec.id="p98f-reasons-panel";
    sec.innerHTML = "<div class=\"panel-header\"><div><h2>Exit Reasons Breakdown</h2><span class=\"muted\">Distribution of trade exit triggers \u00b7 donut + per-reason P&amp;L attribution \u00b7 source: /api/trades</span></div><span class=\"panel-badge\" style=\"background:rgba(255,200,0,.12);color:#ffc833\">FORENSIC</span></div><div style=\"display:grid;grid-template-columns:300px 1fr;gap:24px;margin-top:14px;align-items:center;font-family:JetBrains Mono,Consolas,monospace\"><canvas id=\"p98f-reasons-canvas\" style=\"width:280px;height:280px;display:block;margin:0 auto\"></canvas><div id=\"p98f-reasons-legend\"><div class=\"muted\">loading\u2026</div></div></div>";
    const anchor = document.getElementById("p98f-mc-panel") || document.getElementById("p98f-z-panel");
    if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(sec, anchor.nextSibling);
  }
  function drawDonut(reasons, total, winCount){
    const canvas = document.getElementById("p98f-reasons-canvas"); if (!canvas) return;
    const dpr = window.devicePixelRatio || 1; const W = 280, H = 280;
    canvas.width = W*dpr; canvas.height = H*dpr;
    canvas.style.width = W+"px"; canvas.style.height = H+"px";
    const ctx = canvas.getContext("2d"); ctx.setTransform(1,0,0,1,0,0); ctx.scale(dpr,dpr); ctx.clearRect(0,0,W,H);
    const cx = W/2, cy = H/2, rOut = 110, rIn = 70;
    let start = -Math.PI/2;
    reasons.forEach(function(r){
      const frac = r.count / total; const end = start + frac * Math.PI * 2;
      ctx.beginPath(); ctx.arc(cx, cy, rOut, start, end); ctx.arc(cx, cy, rIn, end, start, true); ctx.closePath();
      ctx.fillStyle = colorFor(r.name); ctx.fill();
      ctx.strokeStyle = "rgba(0,0,0,.4)"; ctx.lineWidth = 1.5; ctx.stroke();
      start = end;
    });
    ctx.fillStyle = "#ddd"; ctx.font = "bold 28px JetBrains Mono, monospace"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText("N=" + total, cx, cy - 12);
    const wr = total ? Math.round(winCount/total*100) : 0;
    ctx.fillStyle = wr >= 50 ? "#3ce04f" : "#ff8c00"; ctx.font = "13px JetBrains Mono, monospace";
    ctx.fillText(wr + "% WIN", cx, cy + 14);
  }
  function update(){
    fetch("/api/trades", {credentials:"same-origin"}).then(function(r){ return r.ok ? r.json() : null; }).then(function(d){
      if (!d || !d.trades) return;
      const counts = {}, pnlByR = {};
      let winCount = 0;
      d.trades.forEach(function(t){
        const r = t.reason || "OTHER";
        counts[r] = (counts[r] || 0) + 1;
        pnlByR[r] = (pnlByR[r] || 0) + (t.pnl || 0);
        if ((t.pnl || 0) > 0) winCount++;
      });
      const reasons = Object.keys(counts).map(function(k){ return {name: k, count: counts[k], pnl: pnlByR[k]}; }).sort(function(a,b){ return b.count - a.count; });
      const total = d.trades.length;
      drawDonut(reasons, total, winCount);
      const leg = document.getElementById("p98f-reasons-legend"); if (!leg) return;
      let lh = "<table style=\"width:100%;border-collapse:collapse;font-size:11px\"><thead><tr style=\"color:#888;font-size:9px;letter-spacing:.4px\"><th style=\"text-align:left;padding:5px 0;border-bottom:1px solid rgba(255,255,255,.12)\">REASON</th><th style=\"text-align:right;padding:5px 0;border-bottom:1px solid rgba(255,255,255,.12)\">COUNT</th><th style=\"text-align:right;padding:5px 0;border-bottom:1px solid rgba(255,255,255,.12)\">SHARE</th><th style=\"text-align:right;padding:5px 0;border-bottom:1px solid rgba(255,255,255,.12)\">P&amp;L</th><th style=\"text-align:right;padding:5px 0;border-bottom:1px solid rgba(255,255,255,.12)\">AVG</th></tr></thead><tbody>";
      reasons.forEach(function(r){
        const pct = (r.count / total * 100).toFixed(1);
        const color = colorFor(r.name);
        const pnlCol = r.pnl > 0 ? "#3ce04f" : (r.pnl < 0 ? "#ff5566" : "#888");
        const avg = r.count ? r.pnl/r.count : 0;
        lh += "<tr style=\"border-bottom:1px solid rgba(255,255,255,.04)\"><td style=\"padding:8px 0;color:#ddd\"><span style=\"display:inline-block;width:10px;height:10px;background:" + color + ";border-radius:2px;margin-right:8px;vertical-align:middle\"></span>" + r.name + "</td><td style=\"text-align:right;color:#ddd;padding:8px 0\">" + r.count + "</td><td style=\"text-align:right;color:#888;padding:8px 0\">" + pct + "%</td><td style=\"text-align:right;color:" + pnlCol + ";padding:8px 0;font-weight:600\">\u20b9" + Math.round(r.pnl).toLocaleString("en-IN") + "</td><td style=\"text-align:right;color:" + pnlCol + ";padding:8px 0\">\u20b9" + Math.round(avg).toLocaleString("en-IN") + "</td></tr>";
      });
      const totPnl = reasons.reduce(function(a,b){ return a + b.pnl; }, 0);
      const totCol = totPnl > 0 ? "#3ce04f" : "#ff5566";
      lh += "<tr style=\"border-top:1px solid rgba(255,255,255,.18)\"><td style=\"padding:8px 0;color:#aaa;letter-spacing:.4px;font-size:10px\">TOTAL</td><td style=\"text-align:right;color:#ddd;padding:8px 0;font-weight:700\">" + total + "</td><td style=\"text-align:right;color:#888;padding:8px 0\">100%</td><td style=\"text-align:right;color:" + totCol + ";padding:8px 0;font-weight:700\">\u20b9" + Math.round(totPnl).toLocaleString("en-IN") + "</td><td style=\"text-align:right;color:" + totCol + ";padding:8px 0\">\u20b9" + Math.round(total ? totPnl/total : 0).toLocaleString("en-IN") + "</td></tr>";
      lh += "</tbody></table>";
      leg.innerHTML = lh;
    }).catch(function(){});
  }
  function init(){ makePanel(); update(); setInterval(update, 30000); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();

/* ===== Phase 9.8f.42: Daily P&L Calendar Heatmap ===== */
(function _p98f_cal(){
  if (window.__P98F_CAL__) return;
  window.__P98F_CAL__ = true;
  function makePanel(){
    if (document.getElementById("p98f-cal-panel")) return;
    const sec = document.createElement("section"); sec.className="panel"; sec.id="p98f-cal-panel";
    sec.innerHTML = "<div class=\"panel-header\"><div><h2>Daily P&amp;L Heatmap</h2><span class=\"muted\">Last 13 weeks (91 days) \u00b7 color = sign \u00d7 intensity \u00b7 hover for detail \u00b7 source: /api/daily-pnl</span></div><span class=\"panel-badge\" style=\"background:rgba(60,224,79,.12);color:#3ce04f\">HEATMAP</span></div><div id=\"p98f-cal-wrap\" style=\"margin-top:14px;font-family:JetBrains Mono,Consolas,monospace\"><div class=\"muted\">loading\u2026</div></div><div id=\"p98f-cal-foot\" class=\"muted\" style=\"margin-top:14px;font-size:11px;padding-top:10px;border-top:1px solid rgba(128,128,128,.18);font-family:JetBrains Mono,Consolas,monospace\"></div>";
    const anchor = document.getElementById("p98f-reasons-panel") || document.getElementById("p98f-mc-panel");
    if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(sec, anchor.nextSibling);
  }
  function isoDate(d){ const y=d.getFullYear(); const m=String(d.getMonth()+1).padStart(2,"0"); const dd=String(d.getDate()).padStart(2,"0"); return y+"-"+m+"-"+dd; }
  function update(){
    fetch("/api/daily-pnl", {credentials:"same-origin"}).then(function(r){ return r.ok ? r.json() : null; }).then(function(d){
      const wrap = document.getElementById("p98f-cal-wrap"); if (!wrap) return;
      if (!d) { wrap.innerHTML = "<div class=\"muted\">no data\u2014auth?</div>"; return; }
      const rows = d.days || d.daily || d.rows || d.data || [];
      const map = {};
      rows.forEach(function(x){ const dt = x.date || x.day || x.dt; if (dt) { const k = String(dt).slice(0,10); map[k] = {pnl: Number(x.pnl||x.daily_pnl||0), trades: Number(x.trades||x.n||x.count||0)}; } });
      const today = new Date(); today.setHours(0,0,0,0);
      const lastSat = new Date(today); lastSat.setDate(lastSat.getDate() + (6 - lastSat.getDay()));
      const NW = 13;
      const startDate = new Date(lastSat); startDate.setDate(startDate.getDate() - (NW * 7 - 1));
      let maxAbs = 1;
      Object.keys(map).forEach(function(k){ if (Math.abs(map[k].pnl) > maxAbs) maxAbs = Math.abs(map[k].pnl); });
      const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
      const DOW = ["","Mon","","Wed","","Fri",""];
      let h = "<div style=\"display:flex;gap:14px;align-items:flex-start\">";
      h += "<div style=\"display:grid;grid-template-rows:repeat(7,15px);gap:2px;padding-top:18px;font-size:9px;color:#666;line-height:15px\">";
      DOW.forEach(function(lbl){ h += "<div>" + lbl + "</div>"; });
      h += "</div><div>";
      h += "<div style=\"display:grid;grid-template-columns:repeat(" + NW + ",15px);gap:2px;height:16px;font-size:9px;color:#888;margin-bottom:2px\">";
      let prevMonth = -1;
      for (let wi = 0; wi < NW; wi++){ const cd = new Date(startDate); cd.setDate(cd.getDate() + wi * 7); const m = cd.getMonth(); if (m !== prevMonth) { h += "<div>" + MONTHS[m] + "</div>"; prevMonth = m; } else { h += "<div></div>"; } }
      h += "</div>";
      h += "<div style=\"display:grid;grid-template-columns:repeat(" + NW + ",15px);grid-template-rows:repeat(7,15px);gap:2px\">";
      const todayKey = isoDate(today);
      for (let i = 0; i < NW * 7; i++){
        const cd = new Date(startDate); cd.setDate(cd.getDate() + i);
        const wk = Math.floor(i / 7); const dow = i % 7;
        const key = isoDate(cd); const entry = map[key]; const future = cd > today;
        let bg = "rgba(128,128,128,0.06)"; let title = key + " \u00b7 no data";
        if (entry && (entry.pnl !== 0 || entry.trades > 0)){
          const intensity = Math.min(1, Math.abs(entry.pnl) / maxAbs);
          const alpha = (0.18 + 0.72 * intensity).toFixed(2);
          bg = entry.pnl > 0 ? "rgba(60,224,79," + alpha + ")" : (entry.pnl < 0 ? "rgba(255,85,102," + alpha + ")" : "rgba(128,128,128,0.18)");
          title = key + " \u00b7 \u20b9" + Math.round(entry.pnl).toLocaleString("en-IN") + (entry.trades ? " \u00b7 " + entry.trades + " trades" : "");
        }
        const border = todayKey === key ? "1.5px solid rgba(255,255,255,.7)" : "1px solid rgba(255,255,255,.04)";
        const opacity = future ? "0.12" : "1";
        h += "<div title=\"" + title + "\" style=\"grid-column:" + (wk + 1) + ";grid-row:" + (dow + 1) + ";background:" + bg + ";border:" + border + ";border-radius:2px;opacity:" + opacity + "\"></div>";
      }
      h += "</div></div>";
      h += "<div style=\"margin-left:auto;display:flex;align-items:flex-start;gap:18px;padding-top:18px\"><div><div style=\"font-size:9px;color:#666;letter-spacing:.4px;margin-bottom:5px\">PROFIT</div><div style=\"display:flex;gap:2px\"><div style=\"width:12px;height:12px;background:rgba(60,224,79,.18);border-radius:2px\"></div><div style=\"width:12px;height:12px;background:rgba(60,224,79,.35);border-radius:2px\"></div><div style=\"width:12px;height:12px;background:rgba(60,224,79,.55);border-radius:2px\"></div><div style=\"width:12px;height:12px;background:rgba(60,224,79,.75);border-radius:2px\"></div><div style=\"width:12px;height:12px;background:rgba(60,224,79,.90);border-radius:2px\"></div></div></div><div><div style=\"font-size:9px;color:#666;letter-spacing:.4px;margin-bottom:5px\">LOSS</div><div style=\"display:flex;gap:2px\"><div style=\"width:12px;height:12px;background:rgba(255,85,102,.18);border-radius:2px\"></div><div style=\"width:12px;height:12px;background:rgba(255,85,102,.35);border-radius:2px\"></div><div style=\"width:12px;height:12px;background:rgba(255,85,102,.55);border-radius:2px\"></div><div style=\"width:12px;height:12px;background:rgba(255,85,102,.75);border-radius:2px\"></div><div style=\"width:12px;height:12px;background:rgba(255,85,102,.90);border-radius:2px\"></div></div></div></div>";
      h += "</div>";
      wrap.innerHTML = h;
      const entries = Object.entries(map);
      const profitD = entries.filter(function(e){ return e[1].pnl > 0; });
      const lossD = entries.filter(function(e){ return e[1].pnl < 0; });
      const total = entries.reduce(function(a,b){ return a + b[1].pnl; }, 0);
      const sorted = entries.slice().sort(function(a,b){ return b[1].pnl - a[1].pnl; });
      const best = sorted[0]; const worst = sorted[sorted.length - 1];
      const fmtR = function(x){ return "\u20b9" + Math.round(x).toLocaleString("en-IN"); };
      const f = document.getElementById("p98f-cal-foot"); if (!f) return;
      f.innerHTML = "<b style=\"color:#ddd\">" + entries.length + "</b> trading days \u00b7 <b style=\"color:#3ce04f\">" + profitD.length + "</b> profitable \u00b7 <b style=\"color:#ff5566\">" + lossD.length + "</b> losing \u00b7 best <b style=\"color:#3ce04f\">" + (best ? (best[0] + " " + fmtR(best[1].pnl)) : "\u2014") + "</b> \u00b7 worst <b style=\"color:#ff5566\">" + (worst ? (worst[0] + " " + fmtR(worst[1].pnl)) : "\u2014") + "</b> \u00b7 net <b style=\"color:" + (total > 0 ? "#3ce04f" : "#ff5566") + "\">" + fmtR(total) + "</b>";
    }).catch(function(){});
  }
  function init(){ makePanel(); update(); setInterval(update, 60000); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();

/* ===== Phase 9.8f.43: Equity Curve & Drawdown panel ===== */
(function _p98f_equity(){
  if (window.__P98F_EQUITY__) return;
  window.__P98F_EQUITY__ = true;
  function makePanel(){
    if (document.getElementById("p98f-equity-panel")) return;
    const sec = document.createElement("section"); sec.className="panel"; sec.id="p98f-equity-panel";
    sec.innerHTML = "<div class=\"panel-header\"><div><h2>Equity Curve &amp; Drawdown</h2><span class=\"muted\">Cumulative equity (top) \u00b7 drawdown from peak (bottom) \u00b7 underwater chart \u00b7 source: /api/drawdown</span></div><span class=\"panel-badge\" style=\"background:rgba(60,224,79,.12);color:#3ce04f\">CURVE</span></div><canvas id=\"p98f-equity-canvas\" style=\"width:100%;height:380px;display:block;margin-top:14px\"></canvas><div id=\"p98f-equity-foot\" class=\"muted\" style=\"margin-top:14px;font-size:11px;padding-top:10px;border-top:1px solid rgba(128,128,128,.18);font-family:JetBrains Mono,Consolas,monospace\"></div>";
    const anchor = document.getElementById("p98f-cal-panel") || document.getElementById("p98f-reasons-panel");
    if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(sec, anchor.nextSibling);
  }
  function draw(canvas, dates, eqs, dds){
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const W = rect.width || 1000, H = 380;
    canvas.width = W * dpr; canvas.height = H * dpr;
    canvas.style.width = W + "px"; canvas.style.height = H + "px";
    const ctx = canvas.getContext("2d"); ctx.setTransform(1,0,0,1,0,0); ctx.scale(dpr, dpr); ctx.clearRect(0, 0, W, H);
    const padL = 75, padR = 30, padT = 18, padB = 38, gap = 14;
    const pw = W - padL - padR;
    const totalPlotH = H - padT - padB - gap;
    const eqH = Math.round(totalPlotH * 0.66);
    const ddH = totalPlotH - eqH;
    const eqY0 = padT, eqY1 = padT + eqH;
    const ddY0 = eqY1 + gap, ddY1 = ddY0 + ddH;
    const n = eqs.length; if (!n) return;
    const eqMin = Math.min.apply(null, eqs), eqMax = Math.max.apply(null, eqs);
    const eqPad = (eqMax - eqMin) * 0.05 || 1;
    const eqLo = eqMin - eqPad, eqHi = eqMax + eqPad, eqRange = eqHi - eqLo;
    const ddMin = Math.min(0, Math.min.apply(null, dds));
    const xAt = function(i){ return padL + (i / Math.max(n - 1, 1)) * pw; };
    const eqYAt = function(v){ return eqY0 + (1 - (v - eqLo) / eqRange) * eqH; };
    const ddYAt = function(v){ return ddY0 + (v === 0 ? 0 : (v / ddMin) * ddH); };
    ctx.strokeStyle = "rgba(255,255,255,0.04)"; ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++){ const y = eqY0 + (i / 4) * eqH; ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(padL + pw, y); ctx.stroke(); }
    ctx.beginPath(); ctx.moveTo(padL, ddY0); ctx.lineTo(padL + pw, ddY0); ctx.stroke();
    ctx.beginPath();
    for (let i = 0; i < n; i++){ const x = xAt(i), y = eqYAt(eqs[i]); if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); }
    ctx.lineTo(padL + pw, eqY1); ctx.lineTo(padL, eqY1); ctx.closePath();
    const grad = ctx.createLinearGradient(0, eqY0, 0, eqY1);
    grad.addColorStop(0, "rgba(60,224,79,0.28)"); grad.addColorStop(1, "rgba(60,224,79,0.02)");
    ctx.fillStyle = grad; ctx.fill();
    ctx.beginPath();
    for (let i = 0; i < n; i++){ const x = xAt(i), y = eqYAt(eqs[i]); if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); }
    ctx.strokeStyle = "#3ce04f"; ctx.lineWidth = 2; ctx.stroke();
    ctx.beginPath(); ctx.moveTo(padL, ddY0);
    for (let i = 0; i < n; i++){ ctx.lineTo(xAt(i), ddYAt(dds[i])); }
    ctx.lineTo(padL + pw, ddY0); ctx.closePath();
    ctx.fillStyle = "rgba(255,85,102,0.28)"; ctx.fill();
    ctx.beginPath();
    for (let i = 0; i < n; i++){ const x = xAt(i), y = ddYAt(dds[i]); if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); }
    ctx.strokeStyle = "#ff5566"; ctx.lineWidth = 1.4; ctx.stroke();
    ctx.fillStyle = "#888"; ctx.font = "10px JetBrains Mono, monospace"; ctx.textAlign = "right";
    for (let i = 0; i <= 4; i++){ const y = eqY0 + (i / 4) * eqH; const val = eqHi - (i / 4) * eqRange; ctx.fillText("\u20b9" + (val / 100000).toFixed(2) + "L", padL - 8, y + 3); }
    ctx.fillText("0%", padL - 8, ddY0 + 3);
    ctx.fillText(ddMin.toFixed(2) + "%", padL - 8, ddY1 + 3);
    ctx.fillText(((ddMin / 2)).toFixed(2) + "%", padL - 8, ddY0 + ddH / 2 + 3);
    ctx.fillStyle = "#666"; ctx.font = "9px JetBrains Mono, monospace"; ctx.textAlign = "left";
    ctx.fillText("EQUITY", padL, eqY0 - 5);
    ctx.fillText("DRAWDOWN", padL, ddY0 - 5);
    ctx.fillStyle = "#888"; ctx.font = "10px JetBrains Mono, monospace"; ctx.textAlign = "center";
    const tickN = Math.min(8, n);
    for (let i = 0; i < tickN; i++){ const idx = Math.round(i * (n - 1) / Math.max(tickN - 1, 1)); const x = xAt(idx); const ds = (dates[idx] || "").slice(5); ctx.fillText(ds, x, ddY1 + 16); }
    const peakIdx = eqs.indexOf(eqMax);
    if (peakIdx >= 0){ const x = xAt(peakIdx), y = eqYAt(eqMax); ctx.beginPath(); ctx.arc(x, y, 3.5, 0, Math.PI * 2); ctx.fillStyle = "#3ce04f"; ctx.fill(); ctx.strokeStyle = "rgba(0,0,0,.4)"; ctx.lineWidth = 1; ctx.stroke(); }
    const ddMinIdx = dds.indexOf(ddMin);
    if (ddMinIdx >= 0 && ddMin < 0){ const x = xAt(ddMinIdx), y = ddYAt(ddMin); ctx.beginPath(); ctx.arc(x, y, 3.5, 0, Math.PI * 2); ctx.fillStyle = "#ff5566"; ctx.fill(); ctx.strokeStyle = "rgba(0,0,0,.4)"; ctx.lineWidth = 1; ctx.stroke(); }
  }
  function update(){
    fetch("/api/drawdown", {credentials:"same-origin"}).then(function(r){ return r.ok ? r.json() : null; }).then(function(d){
      if (!d || !d.rows || !d.rows.length) return;
      const rows = d.rows;
      const dates = rows.map(function(r){ return String(r.date || "").slice(0,10); });
      const eqs = rows.map(function(r){ return Number(r.equity || 0); });
      const dds = rows.map(function(r){ return Number(r.dd_pct || 0); });
      const canvas = document.getElementById("p98f-equity-canvas"); if (!canvas) return;
      draw(canvas, dates, eqs, dds);
      const peak = Math.max.apply(null, eqs);
      const terminal = eqs[eqs.length - 1];
      const totalRet = peak !== 0 ? ((terminal - eqs[0]) / Math.max(Math.abs(eqs[0]), 1) * 100) : 0;
      const maxDd = Math.min.apply(null, dds);
      const currentDd = dds[dds.length - 1];
      const calmar = maxDd < 0 ? (totalRet / Math.abs(maxDd)) : 0;
      const fmtR = function(x){ return "\u20b9" + Math.round(x).toLocaleString("en-IN"); };
      const f = document.getElementById("p98f-equity-foot"); if (!f) return;
      f.innerHTML = "<b style=\"color:#ddd\">" + rows.length + "</b> data points \u00b7 terminal <b style=\"color:#3ce04f\">" + fmtR(terminal) + "</b> \u00b7 peak <b style=\"color:#3ce04f\">" + fmtR(peak) + "</b> \u00b7 total return <b style=\"color:" + (totalRet >= 0 ? "#3ce04f" : "#ff5566") + "\">" + totalRet.toFixed(2) + "%</b> \u00b7 max DD <b style=\"color:#ff5566\">" + maxDd.toFixed(2) + "%</b> \u00b7 current DD <b style=\"color:" + (currentDd < -0.5 ? "#ff5566" : "#ddd") + "\">" + currentDd.toFixed(2) + "%</b> \u00b7 calmar <b style=\"color:#ddd\">" + calmar.toFixed(2) + "</b>";
    }).catch(function(){});
  }
  function init(){ makePanel(); update(); setInterval(update, 60000); window.addEventListener("resize", update); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();


/* ===== Phase 9.8f.44 v2: Risk Limits & Trading Guardrails (bash-safe rewrite) ===== */
(function _p98f_risk(){
  if (window.__P98F_RISK__) return;
  window.__P98F_RISK__ = true;
  const DAILY_LOSS_PCT = 3.0;
  const MAX_DD_PCT = 5.0;
  const MAX_TRADES_PER_SYM = 10;
  function makePanel(){
    if (document.getElementById("p98f-risk-panel")) return;
    const sec = document.createElement("section"); sec.className = "panel"; sec.id = "p98f-risk-panel";
    sec.innerHTML = '<div class="panel-header"><div><h2>Risk Limits &amp; Trading Guardrails</h2><span class="muted">Live proximity to safety thresholds \u00b7 auto-kill if breached \u00b7 source: /api/symbols + /api/strategy</span></div><span class="panel-badge" style="background:rgba(255,85,102,.12);color:#ff5566">SAFETY</span></div><div id="p98f-risk-grid" style="display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:14px;font-family:JetBrains Mono,Consolas,monospace"><div class="muted">loading\u2026</div></div><div id="p98f-risk-foot" class="muted" style="margin-top:14px;font-size:11px;padding-top:10px;border-top:1px solid rgba(128,128,128,.18);font-family:JetBrains Mono,Consolas,monospace"></div>';
    const anchor = document.getElementById("p98f-equity-panel") || document.getElementById("p98f-cal-panel");
    if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(sec, anchor.nextSibling);
  }
  function tile(label, valueHtml, subHtml, ratio, breach){
    const r = Math.max(0, Math.min(1.5, ratio));
    const pct = (r / 1.5 * 100).toFixed(1);
    const c = breach ? "#ff3322" : (r >= 0.7 ? "#ff8c00" : (r >= 0.4 ? "#ffc833" : "#3ce04f"));
    const badge = breach ? "BREACH" : (r >= 0.7 ? "WARN" : (r >= 0.4 ? "WATCH" : "SAFE"));
    let h = '<div style="padding:14px;background:rgba(255,255,255,.02);border-radius:6px;border:1px solid ' + (breach ? 'rgba(255,51,34,.4)' : 'rgba(255,255,255,.06)') + '">';
    h += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px"><div style="font-size:10px;color:#888;letter-spacing:.5px;text-transform:uppercase">' + label + '</div><div style="font-size:9px;font-weight:700;letter-spacing:.5px;padding:2px 6px;border-radius:3px;background:' + c + '22;color:' + c + '">' + badge + '</div></div>';
    h += '<div style="font-size:22px;font-weight:700;color:' + c + ';line-height:1.1;font-variant-numeric:tabular-nums;margin-bottom:4px">' + valueHtml + '</div>';
    h += '<div style="font-size:10px;color:#777;margin-bottom:8px">' + subHtml + '</div>';
    h += '<div style="position:relative;height:6px;background:rgba(255,255,255,.05);border-radius:3px;overflow:hidden">';
    h += '<div style="position:absolute;top:0;left:0;height:100%;width:' + pct + '%;background:' + c + ';border-radius:3px;transition:width .4s"></div>';
    h += '<div style="position:absolute;top:0;left:66.66%;width:1px;height:100%;background:rgba(255,255,255,.25)"></div>';
    h += '</div></div>'; return h;
  }
  function fmtR(x){ return (x < 0 ? "-\u20b9" : "\u20b9") + Math.abs(Math.round(x)).toLocaleString("en-IN"); }
  function update(){
    Promise.all([
      fetch("/api/symbols", {credentials:"same-origin"}).then(function(r){ return r.ok ? r.json() : null; }),
      fetch("/api/strategy", {credentials:"same-origin"}).then(function(r){ return r.ok ? r.json() : null; })
    ]).then(function(arr){
      const sym = arr[0] || {}; const strat = arr[1] || {};
      const grid = document.getElementById("p98f-risk-grid"); if (grid == null) return;
      const _so=sym.symbols||{};const symbols=Array.isArray(_so)?_so:Object.entries(_so).map(function(kv){return Object.assign({key:kv[0]},kv[1]);});
      const cap = Number(strat.capital || 3750000);
      const tier = strat.capital_tier || "GROWTH";
      const lossLimit = -cap * (DAILY_LOSS_PCT / 100);
      let totalPnl = 0, totalTrades = 0, totalLots = 0, maxLotsTotal = 0, killCount = 0;
      const killBySym = [];
      symbols.forEach(function(s){
        const pnl = Number(s.pnl_today || 0);
        const tr = Number(s.trades_today || 0);
        const pos = s.position || {}; const lots = Math.abs(Number(pos.qty || pos.lots || 0));
        const maxL = Number(s.max_lots || 1);
        const kill = Boolean(s.kill);
        totalPnl += pnl; totalTrades += tr; totalLots += lots; maxLotsTotal += maxL;
        if (kill) killCount++;
        killBySym.push({key: s.key || s.symbol || "?", kill: kill});
      });
      const trMax = symbols.length * MAX_TRADES_PER_SYM || MAX_TRADES_PER_SYM;
      const lossRatio = lossLimit !== 0 ? Math.max(0, -totalPnl) / Math.abs(lossLimit) : 0;
      const lossBreach = totalPnl <= lossLimit;
      const ddPct = cap > 0 ? (totalPnl / cap * 100) : 0;
      const ddRatio = Math.max(0, -ddPct) / MAX_DD_PCT;
      const ddBreach = ddPct <= -MAX_DD_PCT;
      const trRatio = totalTrades / trMax;
      const trBreach = totalTrades >= trMax;
      const posRatio = maxLotsTotal > 0 ? totalLots / maxLotsTotal : 0;
      const posBreach = totalLots >= maxLotsTotal;
      const killRatio = symbols.length ? killCount / symbols.length : 0;
      const killBreach = killCount > 0;
      const TIERS = ["SEED","GROWTH","INSTITUTIONAL","HEDGE_FUND","QUANT_ELITE"];
      const TIER_THR = [0, 200000, 1500000, 2500000, 5000000, 99999999];
      const ti = Math.max(0, TIERS.indexOf(tier));
      const tierLo = TIER_THR[ti], tierHi = TIER_THR[ti + 1];
      const tierProg = (cap - tierLo) / Math.max(tierHi - tierLo, 1);
      let html = "";
      html += tile("DAILY P&L vs LOSS LIMIT", '<span>' + fmtR(totalPnl) + '</span> <span style="font-size:11px;color:#888;font-weight:400">/ ' + fmtR(lossLimit) + '</span>', 'ratio ' + (lossRatio * 100).toFixed(0) + '% \u00b7 ' + DAILY_LOSS_PCT + '% capital floor', lossRatio, lossBreach);
      html += tile("INTRADAY DRAWDOWN", ddPct.toFixed(2) + '%<span style="font-size:11px;color:#888;font-weight:400"> / -' + MAX_DD_PCT + '%</span>', 'ratio ' + (ddRatio * 100).toFixed(0) + '% \u00b7 portfolio P&L / capital', ddRatio, ddBreach);
      html += tile("TRADES TODAY", totalTrades + '<span style="font-size:11px;color:#888;font-weight:400"> / ' + trMax + ' max</span>', 'across ' + symbols.length + ' symbols \u00b7 ' + MAX_TRADES_PER_SYM + '/sym cap', trRatio, trBreach);
      html += tile("POSITION EXPOSURE", totalLots + '<span style="font-size:11px;color:#888;font-weight:400"> / ' + maxLotsTotal + ' lots</span>', 'currently open \u00b7 sum of max_lots across symbols', posRatio, posBreach);
      const killHtml = killBySym.map(function(k){ const c = k.kill ? "#ff3322" : "#3ce04f"; const lbl = k.kill ? "ARM" : "OK"; return '<span style="display:inline-block;padding:2px 7px;margin-right:5px;border-radius:3px;background:' + c + '22;color:' + c + ';font-size:11px;font-weight:700;letter-spacing:.3px">' + k.key + ' ' + lbl + '</span>'; }).join("");
      html += tile("KILL SWITCHES", killHtml || '<span style="color:#3ce04f">ALL CLEAR</span>', killCount + ' of ' + symbols.length + ' armed \u00b7 trading halted on armed symbols', killRatio, killBreach);
      const tierColor = ti >= 3 ? "#b478ff" : (ti >= 2 ? "#00bfff" : (ti >= 1 ? "#3ce04f" : "#ffc833"));
      const tierTile = '<div style="padding:14px;background:rgba(255,255,255,.02);border-radius:6px;border:1px solid rgba(255,255,255,.06)"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px"><div style="font-size:10px;color:#888;letter-spacing:.5px;text-transform:uppercase">CAPITAL TIER</div><div style="font-size:9px;font-weight:700;letter-spacing:.5px;padding:2px 6px;border-radius:3px;background:' + tierColor + '22;color:' + tierColor + '">' + tier + '</div></div><div style="font-size:22px;font-weight:700;color:' + tierColor + ';line-height:1.1;font-variant-numeric:tabular-nums;margin-bottom:4px">' + fmtR(cap) + '</div><div style="font-size:10px;color:#777;margin-bottom:8px">' + (tierHi < 99999999 ? 'next tier at ' + fmtR(tierHi) + ' \u00b7 ' + (tierProg * 100).toFixed(1) + '% progress' : 'max tier reached') + '</div><div style="position:relative;height:6px;background:rgba(255,255,255,.05);border-radius:3px;overflow:hidden"><div style="position:absolute;top:0;left:0;height:100%;width:' + Math.min(100, tierProg * 100).toFixed(1) + '%;background:' + tierColor + ';border-radius:3px;transition:width .4s"></div></div></div>';
      html += tierTile;
      grid.innerHTML = html;
      const f = document.getElementById("p98f-risk-foot"); if (f == null) return;
      const breachCount = [lossBreach, ddBreach, trBreach, posBreach, killBreach].filter(Boolean).length;
      const status = breachCount > 0 ? '<b style="color:#ff3322">' + breachCount + ' BREACH' + (breachCount > 1 ? 'ES' : '') + '</b>' : '<b style="color:#3ce04f">ALL LIMITS OK</b>';
      f.innerHTML = status + ' \u00b7 capital <b style="color:#ddd">' + fmtR(cap) + '</b> \u00b7 portfolio P&L <b style="color:' + (totalPnl >= 0 ? '#3ce04f' : '#ff5566') + '">' + fmtR(totalPnl) + '</b> \u00b7 daily loss floor <b style="color:#ff5566">' + fmtR(lossLimit) + '</b> \u00b7 DD floor <b style="color:#ff5566">-' + MAX_DD_PCT + '%</b> \u00b7 last refresh <b>' + new Date().toLocaleTimeString("en-IN") + '</b>';
    }).catch(function(e){console.error("P98F_RISK fail",e);var g=document.getElementById("p98f-risk-grid");if(g)g.innerHTML="<div class=muted>error: "+(e&&e.message?e.message:String(e))+"</div>";});
  }
  function init(){ makePanel(); update(); setInterval(update, 5000); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();

/* ===== Phase 9.8f.48b v2: Bloomberg-style Options Chain panel (fixed JS string escaping) ===== */
(function _p98f_oc(){
  if (window.__P98F_OC__) return;
  window.__P98F_OC__ = true;
  let currentSym = "BNF";
  function makePanel(){
    if (document.getElementById("p98f-oc-panel")) return;
    const sec = document.createElement("section");
    sec.className = "panel";
    sec.id = "p98f-oc-panel";
    sec.innerHTML = '<div class="panel-header"><div><h2>Options Chain</h2><span class="muted">Live spot \u00b7 Black-Scholes Greeks \u00b7 synthetic OI/Vol/IV preview pending Angel One wiring</span></div><div style="display:flex;gap:8px;align-items:center"><span class="panel-badge" style="background:rgba(255,200,51,.12);color:#ffc833">PREVIEW</span><div id="p98f-oc-tabs" style="display:flex;gap:4px;font-family:JetBrains Mono,Consolas,monospace;font-size:11px"><button data-sym="BNF" class="oc-tab" style="padding:4px 10px;border:1px solid #555;background:#333;color:#fff;cursor:pointer;border-radius:3px;font-weight:700">BNF</button><button data-sym="NF" class="oc-tab" style="padding:4px 10px;border:1px solid #555;background:transparent;color:#888;cursor:pointer;border-radius:3px">NF</button><button data-sym="MCN" class="oc-tab" style="padding:4px 10px;border:1px solid #555;background:transparent;color:#888;cursor:pointer;border-radius:3px">MCN</button></div></div></div><div id="p98f-oc-info" class="muted" style="margin-top:10px;font-size:11px;font-family:JetBrains Mono,Consolas,monospace"></div><div id="p98f-oc-wrap" style="margin-top:10px;overflow-x:auto;max-height:520px;overflow-y:auto"><div class="muted">loading\u2026</div></div><div id="p98f-oc-foot" class="muted" style="margin-top:10px;font-size:11px;padding-top:10px;border-top:1px solid rgba(128,128,128,.18);font-family:JetBrains Mono,Consolas,monospace"></div>';
    const anchor = document.getElementById("p98f-risk-panel") || document.getElementById("p98f-equity-panel");
    if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(sec, anchor.nextSibling);
    sec.querySelectorAll(".oc-tab").forEach(function(btn){
      btn.addEventListener("click", function(){
        currentSym = btn.getAttribute("data-sym");
        sec.querySelectorAll(".oc-tab").forEach(function(b){
          const active = b === btn;
          b.style.background = active ? "#333" : "transparent";
          b.style.color = active ? "#fff" : "#888";
          b.style.fontWeight = active ? "700" : "400";
        });
        update();
      });
    });
  }
  function fmtN(x){ return Number(x || 0).toLocaleString("en-IN"); }
  function fmtPx(x){ return Number(x || 0).toFixed(2); }
  function update(){
    fetch("/api/option-chain?symbol=" + currentSym, {credentials:"same-origin"})
      .then(function(r){ return r.ok ? r.json() : null; })
      .then(function(d){
        const wrap = document.getElementById("p98f-oc-wrap");
        if (wrap == null) return;
        if (d == null || d.ok !== true) {
          wrap.innerHTML = '<div class="muted">option chain unavailable</div>';
          return;
        }
        const info = document.getElementById("p98f-oc-info");
        if (info != null) {
          info.innerHTML = '<b style="color:#3ce04f">' + d.underlying + '</b> spot <b style="color:#fff;font-size:13px">' + fmtN(d.spot) + '</b> \u00b7 ATM <b style="color:#ffc833;font-size:13px">' + fmtN(d.atm) + '</b> \u00b7 expiry T+' + d.expiry_days + 'd \u00b7 step ' + d.step + ' \u00b7 mode <b style="color:#ffc833">' + d.mode + '</b>';
        }
        let maxOI = 1;
        d.strikes.forEach(function(s){
          if (s.ce.oi > maxOI) maxOI = s.ce.oi;
          if (s.pe.oi > maxOI) maxOI = s.pe.oi;
        });
        let html = '<table style="width:100%;font-family:JetBrains Mono,Consolas,monospace;font-size:11px;border-collapse:collapse;font-variant-numeric:tabular-nums">';
        html += '<thead><tr style="border-bottom:1px solid rgba(128,128,128,.25)"><th colspan="6" style="text-align:center;color:#3ce04f;font-weight:700;padding:6px;background:rgba(60,224,79,.06);letter-spacing:.5px">CALL</th><th style="text-align:center;color:#fff;font-weight:700;background:rgba(255,255,255,.05);padding:6px">STRIKE</th><th colspan="6" style="text-align:center;color:#ff5566;font-weight:700;padding:6px;background:rgba(255,85,102,.06);letter-spacing:.5px">PUT</th></tr>';
        html += '<tr style="color:#888;text-align:right;font-size:10px;border-bottom:1px solid rgba(128,128,128,.2)"><th style="padding:4px 6px">OI</th><th style="padding:4px 6px">CHG</th><th style="padding:4px 6px">VOL</th><th style="padding:4px 6px">IV%</th><th style="padding:4px 6px">\u0394</th><th style="padding:4px 6px">LTP</th><th style="padding:4px 6px;color:#fff;background:rgba(255,255,255,.04);text-align:center">PRICE</th><th style="padding:4px 6px;text-align:left">LTP</th><th style="padding:4px 6px;text-align:left">\u0394</th><th style="padding:4px 6px;text-align:left">IV%</th><th style="padding:4px 6px;text-align:left">VOL</th><th style="padding:4px 6px;text-align:left">CHG</th><th style="padding:4px 6px;text-align:left">OI</th></tr></thead><tbody>';
        d.strikes.forEach(function(s){
          const isATM = s.strike === d.atm;
          const ceITM = s.strike < d.atm;
          const peITM = s.strike > d.atm;
          const rowBg = isATM ? 'background:rgba(255,200,51,.08)' : '';
          const ceHeat = Math.min(1, s.ce.oi / maxOI);
          const peHeat = Math.min(1, s.pe.oi / maxOI);
          const ceOIbg = 'background:linear-gradient(to right, rgba(60,224,79,' + (ceHeat * 0.22).toFixed(2) + ') ' + (ceHeat * 100).toFixed(0) + '%, transparent ' + (ceHeat * 100).toFixed(0) + '%)';
          const peOIbg = 'background:linear-gradient(to left, rgba(255,85,102,' + (peHeat * 0.22).toFixed(2) + ') ' + (peHeat * 100).toFixed(0) + '%, transparent ' + (peHeat * 100).toFixed(0) + '%)';
          const ceTint = ceITM ? 'color:#3ce04f' : 'color:#888';
          const peTint = peITM ? 'color:#ff5566' : 'color:#888';
          const strikeStyle = isATM ? 'color:#ffc833;font-size:13px' : 'color:#fff';
          const atmTag = isATM ? ' <span style="font-size:9px;color:#ffc833">ATM</span>' : '';
          html += '<tr style="text-align:right;border-bottom:1px solid rgba(128,128,128,.06);' + rowBg + '">';
          html += '<td style="padding:5px 6px;' + ceOIbg + ';' + ceTint + ';font-weight:600">' + fmtN(s.ce.oi) + '</td>';
          html += '<td style="padding:5px 6px;color:#666;font-size:10px">+' + fmtN(s.ce.chgOi) + '</td>';
          html += '<td style="padding:5px 6px;' + ceTint + '">' + fmtN(s.ce.volume) + '</td>';
          html += '<td style="padding:5px 6px;color:#aaa">' + s.ce.iv.toFixed(1) + '</td>';
          html += '<td style="padding:5px 6px;color:#aaa">' + s.ce.delta.toFixed(2) + '</td>';
          html += '<td style="padding:5px 6px;font-weight:700;' + (ceITM ? 'color:#3ce04f' : 'color:#ddd') + '">' + fmtPx(s.ce.ltp) + '</td>';
          html += '<td style="padding:5px 10px;text-align:center;font-weight:700;background:rgba(255,255,255,.04);' + strikeStyle + '">' + fmtN(s.strike) + atmTag + '</td>';
          html += '<td style="padding:5px 6px;text-align:left;font-weight:700;' + (peITM ? 'color:#ff5566' : 'color:#ddd') + '">' + fmtPx(s.pe.ltp) + '</td>';
          html += '<td style="padding:5px 6px;text-align:left;color:#aaa">' + s.pe.delta.toFixed(2) + '</td>';
          html += '<td style="padding:5px 6px;text-align:left;color:#aaa">' + s.pe.iv.toFixed(1) + '</td>';
          html += '<td style="padding:5px 6px;text-align:left;' + peTint + '">' + fmtN(s.pe.volume) + '</td>';
          html += '<td style="padding:5px 6px;text-align:left;color:#666;font-size:10px">+' + fmtN(s.pe.chgOi) + '</td>';
          html += '<td style="padding:5px 6px;text-align:left;' + peOIbg + ';' + peTint + ';font-weight:600">' + fmtN(s.pe.oi) + '</td>';
          html += '</tr>';
        });
        html += '</tbody></table>';
        wrap.innerHTML = html;
        const foot = document.getElementById("p98f-oc-foot");
        if (foot != null) {
          const pcr = d.totals.pcr;
          const pcrColor = pcr > 1.2 ? '#3ce04f' : (pcr < 0.8 ? '#ff5566' : '#ffc833');
          const pcrLabel = pcr > 1.2 ? 'bullish bias' : (pcr < 0.8 ? 'bearish bias' : 'neutral');
          foot.innerHTML = 'Total Call OI <b style="color:#3ce04f">' + fmtN(d.totals.call_oi) + '</b> \u00b7 Total Put OI <b style="color:#ff5566">' + fmtN(d.totals.put_oi) + '</b> \u00b7 PCR <b style="color:' + pcrColor + '">' + pcr.toFixed(2) + '</b> <span style="color:#888">(' + pcrLabel + ')</span> \u00b7 Max Pain <b style="color:#ffc833">' + fmtN(d.totals.max_pain) + '</b> \u00b7 last refresh <b>' + new Date().toLocaleTimeString("en-IN") + '</b>';
        }
      })
      .catch(function(e){
        console.error("P98F_OC fail", e);
        const w = document.getElementById("p98f-oc-wrap");
        if (w != null) w.innerHTML = '<div class="muted">error: ' + (e && e.message ? e.message : String(e)) + '</div>';
      });
  }
  function init(){ makePanel(); update(); setInterval(update, 10000); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();

/* ===== Phase 9.8f.49: SSE real-time tick consumer (replaces 2.5s polling with server push ~50ms latency) ===== */
(function _p98f_sse(){
  if (window.__P98F_SSE__) return;
  window.__P98F_SSE__ = true;
  const SYM_MAP = {
    'BANKNIFTY': 'BANKNIFTY', 'BNF': 'BANKNIFTY',
    'NIFTY': 'NIFTY', 'NF': 'NIFTY',
    'MIDCPNIFTY': 'MIDCPNIFTY', 'MCN': 'MIDCPNIFTY'
  };
  const lastSseVals = {};
  let esRef = null;
  let lastTickAt = 0;
  let tickCount = 0;
  function setBadge(state, color){
    let badge = document.getElementById('p98f-sse-status');
    if (badge == null) {
      const tape = document.getElementById('bb-ticker-tape');
      if (tape == null) return;
      const item = document.createElement('div');
      item.className = 'bb-tape-item';
      item.innerHTML = '<span class="bb-tape-sym">FEED</span><span class="bb-tape-val" id="p98f-sse-status" style="font-weight:700">--</span>';
      tape.appendChild(item);
      badge = document.getElementById('p98f-sse-status');
    }
    if (badge != null) {
      badge.textContent = state;
      badge.style.color = color;
    }
  }
  function applyTick(tick){
    const rawSym = tick.symbol || tick.sym || tick.code || '';
    const tapeSym = SYM_MAP[String(rawSym).toUpperCase()] || rawSym;
    const ltp = (tick.ltp != null ? tick.ltp : (tick.last != null ? tick.last : (tick.price != null ? tick.price : (tick.lastTradedPrice != null ? tick.lastTradedPrice : null))));
    if (ltp == null) return;
    const tape = document.getElementById('bb-ticker-tape');
    if (tape == null) return;
    const item = tape.querySelector('.bb-tape-item[data-sym="' + tapeSym + '"]');
    if (item == null) return;
    const valEl = item.querySelector('.bb-tape-val');
    if (valEl != null) valEl.textContent = (typeof ltp === 'number') ? ltp.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2}) : String(ltp);
    const chg = tick.change_pct != null ? tick.change_pct : (tick.chg_pct != null ? tick.chg_pct : (tick.changePct != null ? tick.changePct : null));
    if (chg != null) {
      const chgEl = item.querySelector('.bb-tape-chg');
      if (chgEl != null) {
        const cls = chg > 0 ? 'up' : (chg < 0 ? 'down' : 'flat');
        const arr = chg > 0 ? '\u25B2' : (chg < 0 ? '\u25BC' : '\u2192');
        chgEl.className = 'bb-tape-chg ' + cls;
        chgEl.textContent = arr + ' ' + (chg > 0 ? '+' : '') + (typeof chg === 'number' ? chg.toFixed(2) : chg) + '%';
      }
    }
    const prev = lastSseVals[tapeSym];
    if (prev != null && typeof ltp === 'number' && ltp !== prev) {
      const dir = ltp > prev ? 'flash-up' : 'flash-down';
      item.classList.add(dir);
      setTimeout(function(){ item.classList.remove(dir); }, 350);
    }
    if (typeof ltp === 'number') lastSseVals[tapeSym] = ltp;
    lastTickAt = Date.now();
    tickCount++;
    setBadge('SSE \u00b7 ' + tickCount, '#3ce04f');
  }
  function connect(){
    try {
      esRef = new EventSource('/sse/ticks');
      esRef.onopen = function(){
        tickCount = 0;
        setBadge('SSE OPEN', '#3ce04f');
        console.log('[P98F_SSE] connected to /sse/ticks');
      };
      esRef.onmessage = function(ev){
        try {
          const tick = JSON.parse(ev.data);
          applyTick(tick);
        } catch(e){
          console.warn('[P98F_SSE] parse fail', e, ev.data);
        }
      };
      esRef.onerror = function(){
        setBadge('SSE RECONNECT', '#ffc833');
      };
    } catch(e){
      console.warn('[P98F_SSE] init fail', e);
      setBadge('NO SSE', '#ff5566');
    }
  }
  setInterval(function(){
    if (lastTickAt > 0 && Date.now() - lastTickAt > 60000) {
      setBadge('SSE IDLE', '#888');
    }
  }, 5000);
  function waitForTape(){
    if (document.getElementById('bb-ticker-tape')) {
      connect();
    } else {
      setTimeout(waitForTape, 250);
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', waitForTape);
  else waitForTape();
})();


// Phase 9.8f.64b: Margin Calculator Alpine factory
window.p98fMarginPanel = function p98fMarginPanel(){return{underlying:"BANKNIFTY",lots:1,qty:35,instrument:"fut",side:"buy",price:53780,premium:200,lotSize:35,resolvedQty:35,notional:0,spanPct:0.090,exposurePct:0.035,spanMargin:0,exposureMargin:0,premiumPaid:0,initialMargin:0,leverage:0,LOTS:{NIFTY:65,BANKNIFTY:30,FINNIFTY:60,MIDCPNIFTY:120,SENSEX:20,BANKEX:30,RELIANCE:500,HDFCBANK:550,TCS:175,INFY:400,CUSTOM:1},inr(n){return "Rs "+Number(n||0).toLocaleString("en-IN",{maximumFractionDigits:2});},onUnderlyingChange(){this.lotSize=this.LOTS[this.underlying]||1;this.recompute();},async recompute(){try{const params=new URLSearchParams({underlying:this.underlying,lots:this.lots,instrument:this.instrument,side:this.side,price:this.price,premium:this.premium,qty:this.qty});const r=await fetch("/api/calc/margin?"+params.toString(),{credentials:"same-origin"});if(!r.ok)return;const j=await r.json();if(!j.ok)return;const x=j.result;this.notional=x.notional;this.spanPct=x.span_pct;this.exposurePct=x.exposure_pct;this.spanMargin=x.span_margin;this.exposureMargin=x.exposure_margin;this.premiumPaid=x.premium_paid;this.initialMargin=x.initial_margin;this.leverage=x.leverage;this.resolvedQty=x.qty;this.lotSize=x.lot_size;}catch(e){console.error("p98fMarginPanel.recompute",e);}}};};


// Phase 9.8g.66: Bloomberg SPA shell
window.p98gShell = function p98gShell(){return{activeTab:"live",VALID_TABS:["live","tools","markets","portfolio","strategy","history","system"],setTab(t){if(this.VALID_TABS.indexOf(t)<0)t="live";this.activeTab=t;try{history.replaceState(null,"","#"+t);}catch(e){}},initRouting(){const h=(location.hash||"").replace(/^#/,"").toLowerCase();if(h && this.VALID_TABS.indexOf(h)>=0)this.activeTab=h;window.addEventListener("hashchange",()=>{const nh=(location.hash||"").replace(/^#/,"").toLowerCase();if(this.VALID_TABS.indexOf(nh)>=0)this.activeTab=nh;});window.addEventListener("keydown",(e)=>{if(e.target && (e.target.tagName==="INPUT"||e.target.tagName==="SELECT"||e.target.tagName==="TEXTAREA"))return;if(e.metaKey||e.ctrlKey||e.altKey)return;const idx=parseInt(e.key)-1;if(idx>=0 && idx<this.VALID_TABS.length){this.setTab(this.VALID_TABS[idx]);e.preventDefault();}});}};};


// Phase 9.8g.68: STRATEGY + SYSTEM tab factories
window.p98gStrategyPanel = function p98gStrategyPanel() {
  return {
    lotRows: [
      { sym: "BANKNIFTY", lot: 35 },
      { sym: "NIFTY", lot: 25 },
      { sym: "MIDCPNIFTY", lot: 120 },
    ],
  };
};

window.p98gSystemPanel = function p98gSystemPanel() {
  return {
    info: { service: "active", websocket: "connected", tokens: 3, commit: "3bf9e67", activityCount: 25 },
    lastRefresh: "",
    timer: null,
    get serviceColor() { return (this.info.service||"").toLowerCase()==="active" ? "#0a0" : "#f33"; },
    get wsColor() { return (this.info.websocket||"").toLowerCase()==="connected" ? "#0a0" : "#888"; },
    async refresh() {
      try {
        const r = await fetch("/api/system/info", { credentials: "same-origin" });
        if (r.ok) {
          const d = await r.json();
          this.info = Object.assign({}, this.info, d);
        }
        // else keep static fallback
      } catch(e) {
        this.info.service = "error";
      }
      this.lastRefresh = new Date().toLocaleTimeString();
    },
    init() { this.refresh(); this.timer = setInterval(() => this.refresh(), 30000); },
  };
};

// Phase 9.8g.65c: Bloomberg instrument search component
window.p98gInstrSearch = function p98gInstrSearch() {
  return {
    q: "",
    rows: [],
    loading: false,
    async search() {
      const q = this.q.trim();
      if (q.length < 2) { this.rows = []; return; }
      this.loading = true;
      try {
        const r = await fetch("/api/instruments/search?q=" + encodeURIComponent(q) + "&limit=20", {credentials:"same-origin"});
        if (r.ok) { const j = await r.json(); this.rows = j.rows || []; } else { this.rows = []; }
      } catch(e) { this.rows = []; }
      this.loading = false;
    }
  };
};
