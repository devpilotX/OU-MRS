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
  const mc = $('#mode-chip'); mc.textContent = s.live_mode ? 'LIVE' : 'Paper'; mc.className = 'chip ' + (s.live_mode ? 'err' : 'info');
  const hbi = $('#heartbeat-info'); if(hbi) hbi.textContent = 'Heartbeats today: ' + (s.heartbeat_count_today || 0);
  const stEl = $('#server-time'); if(stEl) stEl.textContent = new Date(s.server_time).toLocaleTimeString();
  if(s.next_run_usec){ const us = parseInt(s.next_run_usec); if(us > 0){ const dt = new Date(us/1000); const sched = $('#schedule-time'); if(sched) sched.textContent = dt.toLocaleString('en-IN',{weekday:'short',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'}); } }
}

async function refreshHealth(){
  const h=await fetchJSON("/api/health");if(!h)return;
  const c=$("#health-chip");
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
  const c=$("#market-chip");c.textContent="Market: "+m.status.toUpperCase().replace("_"," ");
  c.className="chip "+(m.status==="open"?"ok":m.status==="pre_open"?"warn":"");
  applyCadence(m.status === "open" || m.status === "pre_open");
}

async function refreshStrategy(){
  const s=await fetchJSON("/api/strategy");if(!s)return;
  // 8o.3a: multi-symbol render + capital tier chip
  const symList=(s.symbols||[]).map(x=>`<span class="strat-sym">${x.key}</span><span class="strat-lot">${x.lot_size}L · max ${x.max_lots}</span>`).join("&nbsp;&nbsp;");
  const tierChip=s.capital_tier?`<span class="strat-tier">${s.capital_tier}</span>`:"";
  $("#strategy-detail").innerHTML=`<div>📊 ${symList||s.symbol||"--"}</div><div>💰 Rs ${(s.capital||0).toLocaleString("en-IN")} ${tierChip}</div><div>📏 z_e ${s.z_entry} · z_s ${s.z_stop} · w ${s.window}</div>`;
}

async function refreshTrades(){
  const d=await fetchJSON("/api/trades");if(!d)return;
  const pnl=d.total_pnl||0;
  const el=$("#total-pnl");el.textContent=fmtMoney(pnl);
  el.className="kpi-value "+(pnl>0?"positive":pnl<0?"negative":"");
  $("#pnl-pct").textContent=fmtPct(pnl/150000);
  $("#trade-count").textContent=d.count;
  $("#win-rate").textContent="Win: "+fmtPct(d.win_rate);
  $("#trade-summary").textContent=`${d.count} trades · ${fmtMoney(pnl)} · win ${fmtPct(d.win_rate)}`;
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
  const d=await fetchJSON("/api/log?n=120");if(!d)return;
  const pre=$("#log-view");const errOnly=$("#log-errors-only").checked;
  let lines=d.lines||[];
  if(errOnly)lines=lines.filter(l=>/error|exception|traceback|failed/i.test(l));
  pre.innerHTML=lines.map(l=>{let cls="log-info";if(/error|exception|traceback|failed/i.test(l))cls="log-err";else if(/warn/i.test(l))cls="log-warn";else if(/heartbeat/i.test(l))cls="log-hb";return `<span class="${cls}">${escHtml(l)}</span>`;}).join("\n");
  if(d.source)$("#log-source").textContent="file: "+d.source;
  if($("#log-autoscroll").checked)pre.scrollTop=pre.scrollHeight;
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
  const cap=150000,baseline=new Array(equity.length).fill(cap);
  const minV=Math.min(...equity,cap),maxV=Math.max(...equity,cap),pad=(maxV-minV)*.15||5000;
  const finalEq=equity[equity.length-1],pnl=finalEq-cap;
  $("#equity-range").textContent=`${labels[0]} → ${labels[labels.length-1]}  ·  Final ₹${Math.round(finalEq).toLocaleString("en-IN")} (${pnl>=0?"+":""}${(pnl/cap*100).toFixed(2)}%)`;
  if(equityChart)equityChart.destroy();
  const dark=document.documentElement.getAttribute("data-theme")!=="light";const{grid,axis}=chartCommon(dark);
  equityChart=new Chart($("#equity-chart").getContext("2d"),{type:"line",data:{labels,datasets:[{label:"Equity",data:equity,borderColor:"rgba(99,102,241,1)",backgroundColor:"rgba(99,102,241,0.12)",fill:true,stepped:"before",pointRadius:0,pointHoverRadius:5,borderWidth:2},{label:"Capital (₹150k)",data:baseline,borderColor:"rgba(139,148,158,0.55)",borderDash:[6,6],pointRadius:0,borderWidth:1.2,fill:false}]},options:{responsive:true,maintainAspectRatio:false,animation:{duration:400},interaction:{intersect:false,mode:"index"},plugins:{legend:{position:"top",align:"end",labels:{color:axis,font:{size:11},usePointStyle:true,boxWidth:8}},tooltip:{backgroundColor:dark?"rgba(18,24,38,.95)":"rgba(255,255,255,.98)",titleColor:dark?"#e6edf3":"#0f172a",bodyColor:dark?"#e6edf3":"#0f172a",borderColor:dark?"#1f2937":"#e2e8f0",borderWidth:1,padding:10,callbacks:{label:c=>c.dataset.label+": ₹"+Math.round(c.parsed.y).toLocaleString("en-IN"),afterBody:it=>{if(it.length&&it[0].dataset.label.startsWith("Equity")){const v=it[0].parsed.y,diff=v-cap;return["","P&L: "+(diff>=0?"+":"")+"₹"+Math.round(diff).toLocaleString("en-IN")+" ("+(diff/cap*100).toFixed(2)+"%)"];}return[];}}}},scales:{x:{ticks:{maxTicksLimit:8,color:axis,font:{size:10}},grid:{color:grid}},y:{min:Math.max(0,minV-pad),max:maxV+pad,ticks:{color:axis,font:{size:10},callback:v=>"₹"+(v/1000).toFixed(0)+"k"},grid:{color:grid}}}}});
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
  ddChart=new Chart($("#drawdown-chart").getContext("2d"),{type:"line",data:{labels,datasets:[{label:"Drawdown %",data:dd,borderColor:"rgba(239,68,68,1)",backgroundColor:"rgba(239,68,68,0.15)",fill:true,pointRadius:0,borderWidth:1.5,stepped:"before"}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>c.parsed.y.toFixed(2)+"%"}}},scales:{x:{ticks:{maxTicksLimit:8,color:axis,font:{size:10}},grid:{color:grid}},y:{max:0,ticks:{color:axis,font:{size:10},callback:v=>v.toFixed(1)+"%"},grid:{color:grid}}}}});
}

async function refreshPortfolio(){
  const p=await fetchJSON("/api/portfolio");if(!p)return;
  const el=$("#portfolio-view");
  if(!p.ok){el.innerHTML=`<div class="muted">Angel: ${p.error||"--"}</div>`;return;}
  const rms=p.rms||{};const f=k=>fmtMoney(Number(rms[k]||0));
  el.innerHTML=`<div class="metrics-grid"><div><span class="mk">Available</span><span>${f("availablecash")}</span></div><div><span class="mk">Net balance</span><span>${f("net")}</span></div><div><span class="mk">Margin used</span><span>${f("utiliseddebits")}</span></div><div><span class="mk">Collateral</span><span>${f("collateral")}</span></div></div>`;
  $("#portfolio-ts").textContent=new Date().toLocaleTimeString();
}

async function refreshFast(){await Promise.all([refreshStatus(),refreshHealth(),refreshMarket(),refreshTrades(),refreshLog()]);$("#last-update").textContent=new Date().toLocaleTimeString();}
async function refreshSlow(){await Promise.all([refreshMetrics(),refreshEquity(),refreshDailyPnl(),refreshDrawdown(),refreshStrategy(),refreshPortfolio(),refreshHeatmap()]);}

function initTheme(){
  const saved=localStorage.getItem("theme")||"dark";
  document.documentElement.setAttribute("data-theme",saved);
  $("#theme-toggle").textContent=saved==="dark"?"☀️":"🌙";
  $("#theme-toggle").onclick=()=>{const cur=document.documentElement.getAttribute("data-theme");const nx=cur==="dark"?"light":"dark";document.documentElement.setAttribute("data-theme",nx);localStorage.setItem("theme",nx);$("#theme-toggle").textContent=nx==="dark"?"☀️":"🌙";refreshEquity();refreshDailyPnl();refreshDrawdown();};
}
function initFilters(){$("#trade-filter").onchange=()=>refreshTrades();$("#log-errors-only").onchange=()=>refreshLog();}

initTheme();initFilters();refreshFast();refreshSlow();
setInterval(refreshFast,5000);setInterval(refreshSlow,60000);

// ===== v6 -- chart subtitles + info tooltips =====
(function(){
  const labels = {
    "Equity Curve":     { sub: "How ₹1,50,000 grew over 121 backtest days (Oct 2025 → Apr 2026)", info: "Stepped line = daily equity. Dotted = starting capital. Rising line = strategy is profitable over time." },
    "Daily P&L":        { sub: "Per-day realised profit/loss from closed trades",                    info: "Green bar = profitable day · Red bar = losing day · No bar = no trades that day. Height = ₹ amount." },
    "Drawdown":         { sub: "How far equity fell from its running peak (risk view)",              info: "0% = at all-time high. -3.65% = worst peak-to-trough loss. Small drawdown = stable strategy." },
    "Backtest Metrics": { sub: "Risk/return stats from 121-day historical simulation",               info: "Sharpe 3.25 = excellent risk-adj return. PF 2.35 = earned ₹2.35 for every ₹1 lost. 62.5% win rate." },
    "Live Portfolio":   { sub: "Real-time Angel broker balance (paper mode = ₹0 used)",              info: "Available = deposit. Margin Used = locked for open positions. Paper mode uses zero margin." },
    "Trade History":    { sub: "Every trade the bot has taken this session",                         info: "Empty = no signals fired yet today. Bot waits for z-score ≥ |1.5| after 40-bar warm-up (~09:55 AM)." },
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
          <div class="lbl">BANKNIFTY FUT · LTP</div>
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
      const __sym = (window.__ouActiveSymbol || localStorage.getItem("ou_mrs_active_symbol") || "BNF");
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
        document.getElementById("ltp-val").textContent = "₹" + Number(d.ltp).toLocaleString("en-IN",{minimumFractionDigits:2,maximumFractionDigits:2});
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
const SYM_NAMES_8M2 = { BNF: "BANKNIFTY", NF: "NIFTY", FNF: "FINNIFTY" };
const SYM_COLORS_8M2 = { in_trade: "#3ce04f", cooldown: "#ff5566", warming_up: "#ffaa3c", idle: "#94a3b8", offline: "#475569" };
const SPARK_BUFFER = { BNF: [], NF: [], FNF: [] };
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
  for (const sym of ["BNF", "NF", "FNF"]) {
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

// Phase 8q — Premium daily P&L heatmap (GitHub-contrib style)
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
      }
      cell.dataset.date = key;
      cell.dataset.pnl = pnl != null ? pnl : "";
      cell.dataset.trades = rec ? rec.trades : 0;
      cell.dataset.wins = rec ? rec.wins : 0;
      cell.dataset.live = rec ? (rec.live||0) : 0;
      cell.dataset.bt = rec ? (rec.bt||0) : 0;
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

  // Tooltip
  const tip = document.getElementById("hm-tooltip");
  cells.forEach(cell => {
    cell.addEventListener("mouseenter", () => {
      const date = cell.dataset.date;
      const pnl = cell.dataset.pnl;
      const trades = cell.dataset.trades;
      const wins = cell.dataset.wins;
      const live = parseInt(cell.dataset.live)||0;
      const bt = parseInt(cell.dataset.bt)||0;
      let html = '<div class="ht-date">' + date + '</div>';
      if(pnl === ""){ html += '<div class="ht-row">no trades</div>'; }
      else {
        const p = parseFloat(pnl);
        html += '<div class="ht-pnl ' + (p>=0?"pos":"neg") + '">' + (p>=0?"+":"") + "Rs " + Math.round(p).toLocaleString("en-IN") + '</div>';
        html += '<div class="ht-row">' + trades + ' trade' + (trades==1?"":"s") + ' · ' + wins + ' win' + (wins==1?"":"s") + '</div>';
        if(live > 0) html += '<span class="ht-tag live">LIVE ' + live + '</span>';
        if(bt > 0) html += '<span class="ht-tag bt">BT ' + bt + '</span>';
      }
      tip.innerHTML = html;
      tip.classList.add("show");
    });
    cell.addEventListener("mousemove", (e) => {
      tip.style.left = Math.min(window.innerWidth - 200, e.clientX + 14) + "px";
      tip.style.top = (e.clientY + 14) + "px";
    });
    cell.addEventListener("mouseleave", () => { tip.classList.remove("show"); });
  });
}

function setText(id, v){ const e = document.getElementById(id); if(e) e.textContent = v; }

// Phase 8q — Latency tracking
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

// Phase 8q — Adaptive cadence (1s/5s during market hours, 5s/30s when closed)
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
