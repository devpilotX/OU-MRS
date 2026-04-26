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
  const s=await fetchJSON("/api/status");if(!s)return;
  const el=$("#bot-status");el.textContent=(s.bot_state||"--").toUpperCase();
  el.style.color=s.bot_state==="active"?"var(--green)":"var(--muted)";
  $("#bot-sub").textContent="Timer: "+(s.timer_state||"--");
  $("#capital").textContent=fmtMoney(s.capital);
  $("#mode-label").textContent=s.live_mode?"🔴 LIVE":"📝 Paper";
  const mc=$("#mode-chip");mc.textContent=s.live_mode?"🔴 LIVE":"📝 Paper";mc.className="chip "+(s.live_mode?"err":"info");
  $("#heartbeat-info").textContent="Today heartbeats: "+(s.heartbeat_count_today||0);
  $("#server-time").textContent=new Date(s.server_time).toLocaleTimeString();
  if(s.next_run_usec){const us=parseInt(s.next_run_usec);if(us>0){const dt=new Date(us/1000);$("#schedule-time").textContent=dt.toLocaleString("en-IN",{weekday:"short",day:"2-digit",month:"short",hour:"2-digit",minute:"2-digit"});}}
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
  const m=await fetchJSON("/api/market-status");if(!m)return;
  const c=$("#market-chip");c.textContent="Market: "+m.status.toUpperCase().replace("_"," ");
  c.className="chip "+(m.status==="open"?"ok":m.status==="pre_open"?"warn":"");
}

async function refreshStrategy(){
  const s=await fetchJSON("/api/strategy");if(!s)return;
  $("#strategy-detail").innerHTML=`<div>📊 <b>${s.symbol||"--"}</b></div><div>💰 ₹${(s.capital||0).toLocaleString("en-IN")} · lot ${s.lot_size}</div><div>📏 z_e ${s.z_entry} · z_s ${s.z_stop} · w ${s.window}</div>`;
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
  const m=await fetchJSON("/api/metrics");if(!m)return;
  const el=$("#metrics-view");
  if(!m||Object.keys(m).length===0){el.innerHTML='<div class="muted">No backtest yet</div>';return;}
  const fmt=(k,v)=>typeof v==="number"?(["win_rate","profit_factor"].includes(k)?v.toFixed(3):v.toFixed(2)):v;
  el.innerHTML="";
  for(const[k,v]of Object.entries(m)){if(typeof v==="object"&&v!==null)continue;const d=document.createElement("div");d.innerHTML=`<span class="mk">${k}</span><span>${fmt(k,v)}</span>`;el.appendChild(d);}
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
async function refreshSlow(){await Promise.all([refreshMetrics(),refreshEquity(),refreshDailyPnl(),refreshDrawdown(),refreshStrategy(),refreshPortfolio()]);}

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
      const r = await fetch("/api/live/state", { credentials:"same-origin" });
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
    } catch(e) {}
  }

  function boot(){ injectDOM(); refreshLive(); setInterval(refreshLive, 5000); }
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

// Phase 8g.6: per-symbol cards polling
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
      continue;
    }
    const state = data.state || "idle";
    card.className = "symbol-card sc-" + state;
    const se = document.getElementById(lower + "-state");
    if (se) se.textContent = state.toUpperCase().replace(/_/g, " ");
    const pe = document.getElementById(lower + "-pnl");
    if (pe) {
      const pnl = Number(data.pnl_today || 0);
      pe.textContent = (pnl >= 0 ? "+Rs " : "Rs ") + Math.round(pnl).toLocaleString("en-IN");
      pe.className = "sc-pnl " + (pnl > 0 ? "pnl-pos" : pnl < 0 ? "pnl-neg" : "pnl-flat");
    }
    const te = document.getElementById(lower + "-trades");
    if (te) te.textContent = (data.trades_today || 0) + " trades";
    const po = document.getElementById(lower + "-pos");
    if (po) {
      if (data.position) {
        const p = data.position;
        po.textContent = p.side + " " + p.qty + "L @ " + Math.round(p.entry).toLocaleString("en-IN");
      } else {
        po.textContent = "no position";
      }
    }
  }
}
setInterval(refreshSymbols, 5000);
refreshSymbols();
