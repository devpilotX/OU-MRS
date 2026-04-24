const $ = s => document.querySelector(s);
const fmtMoney = v => v==null||isNaN(v) ? "—" : (v<0?"-":"") + "₹" + Math.abs(v).toLocaleString("en-IN",{maximumFractionDigits:0});
const fmtPct = v => v==null ? "—" : (v*100).toFixed(2) + "%";
let equityChart = null;

async function fetchJSON(url) {
  const r = await fetch(url, {credentials:"same-origin"});
  if (r.status === 401) { location.href = "/login"; return null; }
  return r.json();
}

async function refreshStatus() {
  const s = await fetchJSON("/api/status"); if (!s) return;
  $("#bot-status").textContent = (s.bot_state||"—").toUpperCase();
  $("#bot-status").style.color = s.bot_state==="active" ? "var(--green)" : "var(--muted)";
  $("#bot-sub").textContent = "Timer: " + (s.timer_state||"—");
  $("#capital").textContent = fmtMoney(s.capital);
  $("#mode-label").textContent = s.live_mode ? "🔴 LIVE" : "📝 Paper";
  $("#heartbeat-info").textContent = "Today heartbeats: " + (s.heartbeat_count_today||0);
  $("#server-time").textContent = new Date(s.server_time).toLocaleTimeString();
  if (s.next_run_usec) {
    const us = parseInt(s.next_run_usec);
    if (us > 0) {
      const d = new Date(us/1000);
      $("#schedule-time").textContent = d.toLocaleString("en-IN",{weekday:"short",day:"2-digit",month:"short",hour:"2-digit",minute:"2-digit"});
    }
  }
}

async function refreshTrades() {
  const d = await fetchJSON("/api/trades"); if (!d) return;
  const pnl = d.total_pnl||0;
  const el = $("#total-pnl");
  el.textContent = fmtMoney(pnl);
  el.classList.toggle("positive", pnl>0);
  el.classList.toggle("negative", pnl<0);
  $("#pnl-pct").textContent = fmtPct(pnl/150000);
  $("#trade-count").textContent = d.count;
  $("#win-rate").textContent = "Win rate: " + fmtPct(d.win_rate);
  $("#trade-count-sub").textContent = d.count + " trades · " + fmtMoney(pnl);
  const tbody = $("#trades-table tbody");
  tbody.innerHTML = "";
  if (!d.trades.length) {
    tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--muted);padding:40px">No trades yet — bot is watching the market 👀</td></tr>';
    return;
  }
  d.trades.slice().reverse().forEach((t,i) => {
    const tr = document.createElement("tr");
    const p = Number(t.pnl||0);
    tr.innerHTML = `<td>${d.trades.length-i}</td>
      <td>${(t.entry_ts||"—").slice(0,16).replace("T"," ")}</td>
      <td>${(t.exit_ts||"—").slice(0,16).replace("T"," ")}</td>
      <td class="side-${(t.side||"").toLowerCase()}">${t.side||"—"}</td>
      <td>${t.qty||"—"}</td>
      <td>${t.entry!=null?Number(t.entry).toFixed(1):"—"}</td>
      <td>${t.exit!=null?Number(t.exit).toFixed(1):"—"}</td>
      <td class="${p>0?'pos':p<0?'neg':''}">${fmtMoney(p)}</td>
      <td>${t.reason||"—"}</td>`;
    tbody.appendChild(tr);
  });
}

async function refreshLog() {
  const d = await fetchJSON("/api/log?n=80"); if (!d) return;
  const pre = $("#log-view");
  pre.textContent = (d.lines||[]).join("\n");
  pre.scrollTop = pre.scrollHeight;
}

async function refreshMetrics() {
  const m = await fetchJSON("/api/metrics"); if (!m) return;
  const el = $("#metrics-view");
  if (!m || Object.keys(m).length === 0) { el.innerHTML = '<div class="muted">No backtest yet</div>'; return; }
  const fmt = (k,v) => typeof v==="number" ? (["win_rate","profit_factor"].includes(k)?v.toFixed(3):v.toFixed(2)) : v;
  el.innerHTML = "";
  for (const [k,v] of Object.entries(m)) {
    if (typeof v === "object" && v !== null) continue;
    const div = document.createElement("div");
    div.innerHTML = `<span class="mk">${k}</span><span>${fmt(k,v)}</span>`;
    el.appendChild(div);
  }
}

async function refreshEquity() {
  const d = await fetchJSON("/api/equity"); if (!d || !d.rows || !d.rows.length) return;
  const ctx = $("#equity-chart").getContext("2d");
  const labels = d.rows.map(r => r.date||r.ts||"");
  const equity = d.rows.map(r => Number(r.equity||0));
  const capital = 150000;
  const baseline = new Array(equity.length).fill(capital);
  const minV = Math.min(...equity, capital);
  const maxV = Math.max(...equity, capital);
  const pad = (maxV - minV) * 0.15 || 5000;
  const finalEq = equity[equity.length-1];
  const pnl = finalEq - capital;
  const pnlPct = (pnl/capital*100).toFixed(2);
  $("#equity-range").textContent = `${labels[0]} → ${labels[labels.length-1]}  ·  Final ₹${Math.round(finalEq).toLocaleString("en-IN")} (${pnl>=0?'+':''}${pnlPct}%)`;
  if (equityChart) equityChart.destroy();
  const dark = document.documentElement.getAttribute("data-theme") !== "light";
  const grid = dark?"rgba(139,148,158,0.08)":"rgba(100,116,139,0.08)";
  const axis = dark?"#8b949e":"#64748b";
  equityChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {label:"Equity",data:equity,borderColor:"rgba(99,102,241,1)",backgroundColor:"rgba(99,102,241,0.12)",fill:true,stepped:"before",pointRadius:0,pointHoverRadius:5,borderWidth:2,order:1},
        {label:"Capital (₹150,000)",data:baseline,borderColor:"rgba(139,148,158,0.6)",borderDash:[6,6],pointRadius:0,borderWidth:1.2,fill:false,order:2}
      ]
    },
    options: {
      responsive:true, maintainAspectRatio:false, animation:{duration:400},
      interaction:{intersect:false,mode:"index"},
      plugins:{
        legend:{display:true,position:"top",align:"end",labels:{color:axis,font:{size:11},usePointStyle:true,boxWidth:8,padding:12}},
        tooltip:{
          backgroundColor:dark?"rgba(18,24,38,0.95)":"rgba(255,255,255,0.98)",
          titleColor:dark?"#e6edf3":"#0f172a",
          bodyColor:dark?"#e6edf3":"#0f172a",
          borderColor:dark?"#1f2937":"#e2e8f0",borderWidth:1,
          padding:10,
          callbacks:{
            label:c=>c.dataset.label+": ₹"+Math.round(c.parsed.y).toLocaleString("en-IN"),
            afterBody:(items)=>{
              if (items.length && items[0].dataset.label==="Equity") {
                const v = items[0].parsed.y;
                const diff = v - capital;
                const pct = (diff/capital*100).toFixed(2);
                return ["", "P&L: " + (diff>=0?"+":"") + "₹" + Math.round(diff).toLocaleString("en-IN") + " (" + pct + "%)"];
              }
              return [];
            }
          }
        }
      },
      scales: {
        x:{ticks:{maxTicksLimit:8,color:axis,font:{size:10}},grid:{color:grid}},
        y:{min:Math.max(0,minV-pad),max:maxV+pad,ticks:{color:axis,font:{size:10},callback:v=>"₹"+(v/1000).toFixed(0)+"k"},grid:{color:grid}}
      }
    }
  });
}

async function refreshPortfolio() {
  const p = await fetchJSON("/api/portfolio"); if (!p) return;
  const el = $("#portfolio-view");
  if (!p.ok) { el.innerHTML = `<div class="muted">Angel connection: ${p.error||'—'}</div>`; return; }
  const rms = p.rms || {};
  const fmtN = k => fmtMoney(Number(rms[k]||0));
  el.innerHTML = `<div class="metrics-grid">
    <div><span class="mk">Available cash</span><span>${fmtN("availablecash")}</span></div>
    <div><span class="mk">Net balance</span><span>${fmtN("net")}</span></div>
    <div><span class="mk">Margin used</span><span>${fmtN("utiliseddebits")}</span></div>
    <div><span class="mk">Collateral</span><span>${fmtN("collateral")}</span></div>
  </div>`;
  $("#portfolio-ts").textContent = new Date().toLocaleTimeString();
}

async function refreshAll() {
  await Promise.all([refreshStatus(),refreshTrades(),refreshLog(),refreshMetrics()]);
  $("#last-update").textContent = new Date().toLocaleTimeString();
}

function initTheme() {
  const saved = localStorage.getItem("theme") || "dark";
  document.documentElement.setAttribute("data-theme", saved);
  $("#theme-toggle").textContent = saved==="dark" ? "☀️" : "🌙";
  $("#theme-toggle").onclick = () => {
    const cur = document.documentElement.getAttribute("data-theme");
    const next = cur === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("theme", next);
    $("#theme-toggle").textContent = next==="dark" ? "☀️" : "🌙";
    if (equityChart) refreshEquity();
  };
}

initTheme();
refreshAll();
refreshEquity();
setInterval(refreshAll, 5000);
setInterval(refreshEquity, 60000);
refreshPortfolio();
setInterval(refreshPortfolio, 30000);
