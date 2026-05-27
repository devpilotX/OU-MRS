/* OU-MRS dashboard v9.8h.J2 — premium SPA, reads REAL API fields */
(function(){
'use strict';

/* ---------- utils ---------- */
const $  = (s,r)=>{ return (r||document).querySelector(s); };
const $$ = (s,r)=>{ return Array.from((r||document).querySelectorAll(s)); };
const INR = (n)=> {
  if (n===null||n===undefined||isNaN(n)) return '—';
  const sign = n<0 ? '-' : '';
  const abs = Math.abs(n);
  if (abs>=1e7) return sign+'₹'+(abs/1e7).toFixed(2)+'Cr';
  if (abs>=1e5) return sign+'₹'+(abs/1e5).toFixed(2)+'L';
  if (abs>=1e3) return sign+'₹'+(abs/1e3).toFixed(1)+'k';
  return sign+'₹'+abs.toFixed(0);
};
const INR_FULL = (n)=> {
  if (n===null||n===undefined||isNaN(n)) return '—';
  const sign = n<0 ? '-' : '';
  return sign+'₹'+Math.abs(n).toLocaleString('en-IN',{maximumFractionDigits:0});
};
const NUM = (n,d=2)=> (n===null||n===undefined||isNaN(n))?'—':Number(n).toLocaleString('en-IN',{minimumFractionDigits:d,maximumFractionDigits:d});
const PCT = (n,d=2)=> (n===null||n===undefined||isNaN(n))?'—':(n>=0?'+':'')+Number(n).toFixed(d)+'%';
const TS  = (s)=> { if(!s) return '—'; const d=new Date(s); if(isNaN(d)) return s; return d.toLocaleTimeString('en-IN',{hour12:false,hour:'2-digit',minute:'2-digit'}); };
const TSD = (s)=> { if(!s) return '—'; const d=new Date(s); if(isNaN(d)) return s; return d.toLocaleString('en-IN',{day:'2-digit',month:'short',hour12:false,hour:'2-digit',minute:'2-digit'}); };
const todayIso = ()=> new Date().toISOString().slice(0,10);
const signClass = (n)=> n>0?'pos':(n<0?'neg':'');
async function getJ(url){
  try{
    const r = await fetch(url,{credentials:'same-origin'});
    if(!r.ok) return null;
    return await r.json();
  }catch(e){ return null; }
}

/* ---------- symbol inference from entry price ---------- */
function symFrom(t){
  if (t.symbol) return t.symbol;
  const p = t.entry||0;
  if (p>=40000) return 'BNF';
  if (p>=20000) return 'NF';
  if (p>=8000)  return 'MCN';
  return '?';
}
function symClass(s){ const m={BNF:'sym-bnf',NF:'sym-nf',MCN:'sym-mcn'}; return m[s]||'sym-bnf'; }
function sideClass(s){ return s==='LONG'?'side-long':(s==='SHORT'?'side-short':''); }
function reasonClass(r){
  const x = String(r||'').toLowerCase();
  if (x.includes('target')) return 'target';
  if (x.includes('kill')||x.includes('stop')) return 'kill';
  if (x.includes('eod')||x.includes('time')) return 'eod';
  if (x.includes('stall')) return 'stall';
  return '';
}

/* ---------- sparkline ---------- */
function spark(values, color){
  if (!values || values.length<2) return '';
  const w=120, h=32, pad=2;
  const min=Math.min(...values), max=Math.max(...values);
  const range=(max-min)||1;
  const xs=values.map((_,i)=> pad + (i/(values.length-1))*(w-2*pad));
  const ys=values.map(v=> h-pad - ((v-min)/range)*(h-2*pad));
  const d='M'+xs.map((x,i)=>x.toFixed(1)+','+ys[i].toFixed(1)).join(' L');
  const last=values[values.length-1], first=values[0];
  const c = color || (last>=first?'var(--profit)':'var(--loss)');
  const fc = last>=first?'rgba(45,209,120,.18)':'rgba(255,84,112,.18)';
  const area = d+` L${xs[xs.length-1].toFixed(1)},${h} L${xs[0].toFixed(1)},${h} Z`;
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><path d="${area}" fill="${fc}"/><path d="${d}" stroke="${c}" stroke-width="1.5" fill="none"/></svg>`;
}

/* ---------- SVG line chart with gradient area ---------- */
function lineChart(elId, points, opts){
  const el = $('#'+elId); if(!el) return;
  opts = opts||{};
  const w = el.clientWidth||600, h = el.clientHeight||220;
  const padL=40, padR=12, padT=8, padB=22;
  if (!points || points.length<2){ el.innerHTML = '<div style="color:var(--text-mute);text-align:center;padding-top:30%;font-size:12px">No data</div>'; return; }
  const xs = points.map((p,i)=> p.x!==undefined? p.x : i);
  const ys = points.map(p=> p.y);
  const xmin=Math.min(...xs), xmax=Math.max(...xs);
  const ymin=Math.min(...ys, 0), ymax=Math.max(...ys, 0);
  const xr=(xmax-xmin)||1, yr=(ymax-ymin)||1;
  const sx = (x)=> padL + ((x-xmin)/xr)*(w-padL-padR);
  const sy = (y)=> h-padB - ((y-ymin)/yr)*(h-padT-padB);
  const cls = opts.cls||'eq';
  const grad = cls==='eq'?'eqGrad':'ddGrad';
  const stroke = cls==='eq'? 'var(--profit)' : 'var(--loss)';
  const stop = cls==='eq'? 'rgba(45,209,120,' : 'rgba(255,84,112,';
  let d = 'M' + points.map(p=> sx(p.x!==undefined?p.x:points.indexOf(p))+','+sy(p.y)).join(' L');
  let area = d + ' L'+sx(xmax)+','+sy(0)+' L'+sx(xmin)+','+sy(0)+' Z';
  // y-axis ticks
  let yticks='';
  for (let i=0;i<=4;i++){
    const y = ymin + (yr*i/4);
    const py = sy(y);
    yticks += `<line class="chart-grid-line" x1="${padL}" x2="${w-padR}" y1="${py}" y2="${py}"/>`;
    yticks += `<text class="chart-axis-text" x="${padL-6}" y="${py+3}" text-anchor="end">${INR(y)}</text>`;
  }
  el.innerHTML = `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
    <defs>
      <linearGradient id="${grad}" x1="0" x2="0" y1="0" y2="1">
        <stop offset="0%" stop-color="${stop}.55)"/>
        <stop offset="100%" stop-color="${stop}0)"/>
      </linearGradient>
    </defs>
    ${yticks}
    <path d="${area}" fill="url(#${grad})"/>
    <path d="${d}" stroke="${stroke}" stroke-width="2" fill="none"/>
  </svg>`;
}

/* ---------- bar chart ---------- */
function barChart(elId, points){
  const el = $('#'+elId); if(!el) return;
  const w=el.clientWidth||600, h=el.clientHeight||220;
  const padL=40, padR=12, padT=8, padB=22;
  if(!points||!points.length){ el.innerHTML='<div style="color:var(--text-mute);text-align:center;padding-top:30%;font-size:12px">No data</div>'; return; }
  const ys = points.map(p=>p.y);
  const ymax = Math.max(0, ...ys), ymin = Math.min(0, ...ys);
  const yr = (ymax-ymin)||1;
  const bw = (w-padL-padR)/points.length * 0.78;
  const zeroY = padT + (ymax/yr)*(h-padT-padB);
  let bars='';
  points.forEach((p,i)=>{
    const cx = padL + (i+0.5) * ((w-padL-padR)/points.length);
    const bh = Math.abs(p.y)/yr*(h-padT-padB);
    const by = p.y>=0 ? zeroY-bh : zeroY;
    bars += `<rect class="chart-bar ${p.y>=0?'pos':'neg'}" x="${cx-bw/2}" y="${by}" width="${bw}" height="${bh}" rx="2"/>`;
  });
  let yticks='';
  for (let i=0;i<=4;i++){
    const y = ymin + (yr*i/4);
    const py = padT + ((ymax-y)/yr)*(h-padT-padB);
    yticks += `<line class="chart-grid-line" x1="${padL}" x2="${w-padR}" y1="${py}" y2="${py}"/>`;
    yticks += `<text class="chart-axis-text" x="${padL-6}" y="${py+3}" text-anchor="end">${INR(y)}</text>`;
  }
  el.innerHTML = `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">${yticks}${bars}</svg>`;
}

/* ---------- THEME ---------- */
function initTheme(){
  const saved = localStorage.getItem('ou-mrs-theme') || 'dark';
  document.documentElement.setAttribute('data-theme', saved);
  const btn = $('#theme-toggle');
  btn.textContent = saved==='dark' ? '☾' : '☀';
  btn.onclick = ()=>{
    const cur = document.documentElement.getAttribute('data-theme');
    const next = cur==='dark'?'light':'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('ou-mrs-theme', next);
    btn.textContent = next==='dark' ? '☾' : '☀';
    if (state.lastEqPts) lineChart('chart-eq-overview', state.lastEqPts, {cls:'eq'});
  };
}

/* ---------- TABS ---------- */
let currentTab = 'overview';
function initTabs(){
  $$('.tab').forEach(t=>{
    t.onclick = ()=>{
      $$('.tab').forEach(x=>x.classList.remove('active'));
      t.classList.add('active');
      currentTab = t.dataset.tab;
      $$('.tab-panel').forEach(p=>p.classList.toggle('active', p.dataset.panel===currentTab));
      refreshAll();
    };
  });
}

/* ---------- STATE ---------- */
const state = {
  status:null, trades:null, tradesArr:[],
  prevLtp:{BNF:null,NF:null,MCN:null}, prevClose:{BNF:null,NF:null,MCN:null},
  lastEqPts:null,
};

/* ---------- TOPBAR / TICKER ---------- */
function renderTopbar(){
  const s = state.status||{};
  const modePill = $('#mode-pill'); const modeText = $('#mode-text');
  const live = !!s.live_mode;
  modePill.classList.toggle('pill-live', live);
  modePill.classList.toggle('pill-paper', !live);
  modeText.textContent = live? 'LIVE' : (s.mode||'PAPER');

  const botPill = $('#bot-pill'); const botText = $('#bot-text');
  botPill.setAttribute('data-sev', s.bot_status_severity||'info');
  botText.textContent = s.bot_status || '—';

  const mkPill = $('#market-pill'); const mkText = $('#market-text');
  const mk = s.market_status||'—';
  mkPill.setAttribute('data-sev', mk==='open'?'ok':(mk==='pre_open'?'info':'warn'));
  mkText.textContent = mk.replace('_',' ').toUpperCase();
}
function renderTicker(liveStates, equity, todayPnl, winRate, hbAge){
  $$('.tick[data-sym]').forEach(el=>{
    const sym = el.dataset.sym;
    const ls = liveStates[sym];
    const ltpEl = $('.ltp', el); const chgEl = $('.chg', el);
    if (ls && ls.ltp!=null){
      ltpEl.textContent = NUM(ls.ltp, 2);
      const prev = state.prevLtp[sym];
      if (prev!=null && prev!==ls.ltp){
        const d = ls.ltp - prev;
        const pct = (d/prev*100);
        chgEl.textContent = (d>0?'▲ ':'▼ ')+Math.abs(d).toFixed(1)+' ('+PCT(pct,2)+')';
        chgEl.className = 'chg '+(d>0?'up':'down');
      } else if (prev==null) {
        chgEl.textContent = '—'; chgEl.className='chg';
      }
      state.prevLtp[sym] = ls.ltp;
    } else {
      ltpEl.textContent = '—'; chgEl.textContent='stale'; chgEl.className='chg';
    }
  });
  $('#tick-eq').textContent  = INR_FULL(equity);
  const dayEl = $('#tick-day');
  dayEl.textContent = INR_FULL(todayPnl);
  dayEl.style.color = todayPnl>0?'var(--profit)':(todayPnl<0?'var(--loss)':'');
  $('#tick-wr').textContent  = winRate!=null? (winRate*100).toFixed(1)+'%' : '—';
  const hbEl = $('#tick-hb');
  hbEl.textContent = hbAge!=null? Math.round(hbAge)+'s ago' : '—';
  hbEl.style.color = hbAge!=null && hbAge>60 ? 'var(--warn)' : '';
}

/* ---------- OVERVIEW ---------- */
function renderKpis(metrics){
  const k = (label, value, sub, cls, sparkVals)=>`
    <div class="kpi ${cls||''}">
      <div class="kpi-label">${label}</div>
      <div class="kpi-value ${cls&&cls.includes('profit')?'pos':(cls&&cls.includes('loss')?'neg':'')}">${value}</div>
      <div class="kpi-sub">${sub||''}</div>
      ${sparkVals && sparkVals.length>1 ? `<div class="kpi-spark">${spark(sparkVals)}</div>` : ''}
    </div>`;
  const cum = metrics.cumPnl;
  const today = metrics.todayPnl;
  const wr = metrics.winRate;
  const exp = metrics.expectancy;
  const dd = metrics.maxDD;
  const ddPct = metrics.maxDDPct;
  const trades = metrics.tradeCount;
  const html = [
    k('Cumulative P&L', INR_FULL(cum), `<span>${trades||0} trades</span>${metrics.cumPnlChange?`<span class="kpi-trend ${metrics.cumPnlChange>0?'up':'down'}">${PCT(metrics.cumPnlChange,1)}</span>`:''}`, cum>=0?'k-profit':'k-loss', metrics.equitySpark),
    k("Today's P&L", INR_FULL(today), `<span>${metrics.tradesToday||0} trades today</span>`, today>=0?'k-profit':'k-loss'),
    k('Win rate', wr!=null?(wr*100).toFixed(1)+'%':'—', `<span>${metrics.wins||0}W / ${metrics.losses||0}L</span>`, 'k-info'),
    k('Expectancy', exp!=null?INR(exp):'—', `<span>per trade</span>`, exp>=0?'k-profit':'k-loss'),
    k('Drawdown', ddPct!=null? PCT(-ddPct,1) : '—', `<span>${dd!=null?INR(dd):'—'} from peak</span>`, 'k-warn'),
    k('Bot health', metrics.botStatus||'—', `<span>HB ${metrics.hbAge!=null?Math.round(metrics.hbAge)+'s':'—'}</span>`, metrics.botSev==='ok'?'k-profit':(metrics.botSev==='err'?'k-loss':'k-info')),
  ].join('');
  $('#kpi-grid').innerHTML = html;
}
function renderRecent(trades){
  const el = $('#recent-list');
  if (!trades || !trades.length){ el.innerHTML='<div style="color:var(--text-mute);padding:14px;text-align:center;font-size:12px">No trades yet</div>'; return; }
  const rows = trades.slice(-8).reverse().map(t=>{
    const sym = symFrom(t);
    const pnlClass = t.pnl>0?'pos':(t.pnl<0?'neg':'');
    return `<div class="recent-row">
      <span class="ts">${TSD(t.entry_ts)}</span>
      <span class="sym ${symClass(sym)}">${sym}</span>
      <span class="desc"><span class="tag ${sideClass(t.side)}">${t.side||'—'}</span> ${t.qty||''} × ${NUM(t.entry,1)} → ${NUM(t.exit,1)} <span class="reason-tag ${reasonClass(t.reason)}">${t.reason||''}</span></span>
      <span class="pnl ${pnlClass}" style="color:var(--${t.pnl>0?'profit':(t.pnl<0?'loss':'text')})">${INR(t.pnl)}</span>
    </div>`;
  }).join('');
  el.innerHTML = rows;
}

/* ---------- TRADES ---------- */
let tradeFilters = { sym:'', side:'', reason:'', q:'' };
function setupTradeFilters(){
  $$('#flt-sym .chip').forEach(c=> c.onclick = ()=>{
    $$('#flt-sym .chip').forEach(x=>x.classList.remove('active')); c.classList.add('active');
    tradeFilters.sym = c.dataset.v; renderTradesTab();
  });
  $$('#flt-side .chip').forEach(c=> c.onclick = ()=>{
    $$('#flt-side .chip').forEach(x=>x.classList.remove('active')); c.classList.add('active');
    tradeFilters.side = c.dataset.v; renderTradesTab();
  });
  $('#flt-reason').onchange = (e)=>{ tradeFilters.reason = e.target.value; renderTradesTab(); };
  $('#flt-search').oninput = (e)=>{ tradeFilters.q = e.target.value.toLowerCase(); renderTradesTab(); };
  $('#export-csv').onclick = ()=>{ window.location = '/api/export/trades'; };
}
function renderTradesTab(){
  const arr = state.tradesArr || [];
  // reason options
  const reasons = Array.from(new Set(arr.map(t=>t.reason).filter(Boolean))).sort();
  const sel = $('#flt-reason');
  if (sel.options.length-1 !== reasons.length){
    sel.innerHTML = '<option value="">All reasons</option>' + reasons.map(r=>`<option value="${r}">${r}</option>`).join('');
    sel.value = tradeFilters.reason;
  }
  // filter
  const f = arr.filter(t=>{
    if (tradeFilters.sym && symFrom(t)!==tradeFilters.sym) return false;
    if (tradeFilters.side && t.side!==tradeFilters.side) return false;
    if (tradeFilters.reason && t.reason!==tradeFilters.reason) return false;
    if (tradeFilters.q){
      const s = JSON.stringify(t).toLowerCase();
      if (!s.includes(tradeFilters.q)) return false;
    }
    return true;
  }).slice().reverse();
  // stats
  const wins = f.filter(t=>t.pnl>0).length;
  const losses = f.filter(t=>t.pnl<0).length;
  const sumPnl = f.reduce((s,t)=>s+(t.pnl||0),0);
  const best = f.length? Math.max(...f.map(t=>t.pnl||0)) : null;
  const worst = f.length? Math.min(...f.map(t=>t.pnl||0)) : null;
  const avg = f.length? sumPnl/f.length : null;
  $('#trades-stats').innerHTML = [
    {l:'Trades shown',v:f.length, cls:''},
    {l:'Net P&L',v:INR_FULL(sumPnl), cls:signClass(sumPnl)},
    {l:'Wins / Losses',v:`${wins} / ${losses}`, cls:''},
    {l:'Best',v:INR(best), cls:'pos'},
    {l:'Worst',v:INR(worst), cls:'neg'},
  ].map(s=>`<div class="stat"><div class="stat-label">${s.l}</div><div class="stat-value ${s.cls}">${s.v}</div></div>`).join('');
  // table
  let cum = 0; const cumMap = new Map();
  arr.forEach((t,i)=>{ cum += (t.pnl||0); cumMap.set(t, cum); });
  $('#trades-tbody').innerHTML = f.map(t=>{
    const sym = symFrom(t);
    return `<tr>
      <td>${TSD(t.entry_ts)}</td>
      <td>${TSD(t.exit_ts)}</td>
      <td><span class="tag ${symClass(sym)}">${sym}</span></td>
      <td><span class="tag ${sideClass(t.side)}">${t.side||'—'}</span></td>
      <td class="r">${t.qty||''}</td>
      <td class="r">${NUM(t.entry,2)}</td>
      <td class="r">${NUM(t.exit,2)}</td>
      <td class="r ${t.pnl>0?'pnl-pos':(t.pnl<0?'pnl-neg':'')}">${INR(t.pnl)}</td>
      <td class="r">${INR(cumMap.get(t))}</td>
      <td><span class="reason-tag ${reasonClass(t.reason)}">${t.reason||'—'}</span></td>
    </tr>`;
  }).join('') || `<tr><td colspan="10" style="text-align:center;padding:30px;color:var(--text-mute)">No trades match the filter</td></tr>`;
}

/* ---------- LIVE ---------- */
async function refreshLive(){
  const symbols=['BNF','NF','MCN'];
  const [bnf, nf, mcn, pf, regime] = await Promise.all([
    getJ('/api/live/state?symbol=BNF'),
    getJ('/api/live/state?symbol=NF'),
    getJ('/api/live/state?symbol=MCN'),
    getJ('/api/portfolio'),
    getJ('/api/regime'),
  ]);
  const map={BNF:bnf, NF:nf, MCN:mcn};
  $('#live-grid').innerHTML = symbols.map(sym=>{
    const d = map[sym] || {};
    const ok = d.ok!==false;
    const stale = d.stale || (d.age_sec!=null && d.age_sec>60);
    return `<div class="live-card ${sym.toLowerCase()}">
      ${stale?'<span class="live-stale">stale</span>':''}
      <div class="live-head"><span class="live-sym">${sym}</span><span class="reason-tag">${(regime&&regime.current)||'—'}</span></div>
      <div class="live-ltp">${NUM(d.ltp,2)}</div>
      <div class="live-meta">
        <div><div class="l">Z-score</div><div class="v">${NUM(d.z_score,2)}</div></div>
        <div><div class="l">Position</div><div class="v">${d.position||'—'}</div></div>
        <div><div class="l">Lots</div><div class="v">${d.lots_open!=null?d.lots_open:'—'} / ${d.max_lots||'—'}</div></div>
        <div><div class="l">Mean</div><div class="v">${NUM(d.mean,2)}</div></div>
        <div><div class="l">Day P&L</div><div class="v">${INR(d.pnl_today)}</div></div>
        <div><div class="l">Age</div><div class="v">${d.age_sec!=null?Math.round(d.age_sec)+'s':'—'}</div></div>
      </div>
    </div>`;
  }).join('');
  // portfolio
  if (pf && pf.ok){
    const r = pf.rms||{}, p = pf.position||{};
    const kv = [
      ['Equity', INR_FULL(r.equity)],
      ['Day P&L', INR(r.pnl_day||r.day_pnl)],
      ['Max DD today', INR(r.max_dd_today)],
      ['Peak equity', INR_FULL(r.peak_equity)],
      ['Open positions', (p.symbols && Object.keys(p.symbols).length) || 0],
      ['Source', pf.source||'—'],
      ['Age', pf.age_sec!=null?Math.round(pf.age_sec)+'s':'—'],
      ['Stale', pf.stale?'YES':'NO'],
    ];
    $('#pf-body').innerHTML = kv.map(([k,v])=>`<div class="kv"><span class="k">${k}</span><span class="v">${v}</span></div>`).join('');
    $('#pf-sub').textContent = pf.live_mode? 'live' : 'paper';
  } else {
    $('#pf-body').innerHTML = '<div style="color:var(--text-mute);font-size:12px;padding:8px">Portfolio snapshot not ready: '+(pf&&pf.reason||'—')+'</div>';
  }
  // reasons feed — pull from live state reasons_log
  const reasons = [];
  symbols.forEach(sym=>{
    const d = map[sym] || {};
    (d.reasons_log||[]).slice(-10).forEach(r=> reasons.push({sym, ts:r.ts||r.time, text:r.reason||r.text||JSON.stringify(r)}));
  });
  reasons.sort((a,b)=> (b.ts||'').localeCompare(a.ts||''));
  $('#reasons-feed').innerHTML = reasons.slice(0,30).map(r=>`<div class="reason-row"><span class="ts">${TS(r.ts)}</span><span class="sym ${symClass(r.sym)}" style="padding:1px 6px;border-radius:4px;font-size:10px;font-weight:700">${r.sym}</span><span>${r.text}</span></div>`).join('')
    || '<div style="color:var(--text-mute);font-size:12px;padding:8px">No recent reasons recorded</div>';
}

/* ---------- PERFORMANCE ---------- */
async function refreshPerf(){
  const [dd, daily, rolling] = await Promise.all([
    getJ('/api/drawdown'), getJ('/api/daily-pnl'), getJ('/api/rolling-metrics'),
  ]);
  if (dd && dd.rows){
    const eqPts = dd.rows.map((r,i)=>({x:i, y:r.equity!=null?r.equity:0}));
    lineChart('chart-eq', eqPts, {cls:'eq'});
    state.lastEqPts = eqPts;
    $('#perf-eq-sub').textContent = `${dd.rows.length} days · BT+live blended`;
    const ddPts = dd.rows.map((r,i)=>({x:i, y:r.dd_pct!=null?-r.dd_pct:0}));
    lineChart('chart-dd', ddPts, {cls:'dd'});
    const worst = Math.min(...ddPts.map(p=>p.y));
    $('#dd-sub').textContent = `Worst ${PCT(worst,1)}`;
  }
  if (daily && daily.rows){
    const last30 = daily.rows.slice(-30).map((r,i)=>({x:i, y:r.pnl||0}));
    barChart('chart-daily', last30);
    const sum = last30.reduce((s,p)=>s+p.y,0);
    $('#dp-sub').textContent = `${last30.length} days · Net ${INR(sum)}`;
  }
  const rm = rolling || {};
  const metrics = [
    ['Sharpe', NUM(rm.sharpe,2)],
    ['Sortino', NUM(rm.sortino,2)],
    ['Win 30d', rm.win_rate_30d!=null?(rm.win_rate_30d*100).toFixed(1)+'%':'—'],
    ['Avg trade', INR(rm.avg_trade)],
    ['Profit factor', NUM(rm.profit_factor,2)],
    ['Max DD %', rm.max_dd_pct!=null?PCT(-rm.max_dd_pct,1):'—'],
  ];
  $('#metric-grid').innerHTML = metrics.map(([l,v])=>`<div class="metric"><div class="metric-label">${l}</div><div class="metric-value">${v}</div></div>`).join('');
}

/* ---------- SYSTEM ---------- */
async function refreshSystem(){
  const [health, mkt, regime, strat, log] = await Promise.all([
    getJ('/api/health'), getJ('/api/market-status'), getJ('/api/regime'), getJ('/api/strategy'), getJ('/api/log?n=60'),
  ]);
  // host
  if (health){
    const bar = (val, label)=>{
      const cls = val>85?'err':(val>65?'warn':'');
      return `<div class="health-row"><div class="head"><span>${label}</span><span class="v">${val!=null?val.toFixed(1)+'%':'—'}</span></div><div class="health-bar ${cls}"><div style="width:${val||0}%"></div></div></div>`;
    };
    const up = health.uptime_seconds;
    const upStr = up!=null? `${Math.floor(up/86400)}d ${Math.floor((up%86400)/3600)}h ${Math.floor((up%3600)/60)}m` : '—';
    $('#host-body').innerHTML = bar(health.cpu_percent,'CPU') + bar(health.memory_percent,'Memory') + bar(health.disk_percent,'Disk') +
      `<div class="kv" style="margin-top:6px"><span class="k">Uptime</span><span class="v">${upStr}</span></div>`;
    $('#host-sub').textContent = 'Live';
  } else {
    $('#host-body').innerHTML = '<div style="color:var(--text-mute);font-size:12px">health unavailable</div>';
  }
  // bot state
  const s = state.status||{};
  $('#bot-state-body').innerHTML = [
    ['Bot status', s.bot_status||'—'],
    ['Severity', s.bot_status_severity||'—'],
    ['Reason', s.bot_status_reason||'—'],
    ['Heartbeat age', s.heartbeat_age_s!=null?Math.round(s.heartbeat_age_s)+'s':'—'],
    ['HB count today', s.heartbeat_count_today||0],
    ['Latest HB', TSD(s.latest_heartbeat)],
    ['Bot state', s.bot_state||'—'],
    ['Timer', s.timer_state||'—'],
    ['Mode', s.mode||'—'],
    ['Live', s.live_mode?'YES':'NO'],
    ['Capital', INR_FULL(s.capital)],
    ['Server time', TSD(s.server_time)],
  ].map(([k,v])=>`<div class="kv"><span class="k">${k}</span><span class="v">${v}</span></div>`).join('');
  // strategy
  if (strat){
    $('#strat-body').innerHTML = [
      ['Capital', INR_FULL(strat.capital)],
      ['Tier', strat.capital_tier||'—'],
      ['Z entry', NUM(strat.z_entry,2)],
      ['Z stop', NUM(strat.z_stop,2)],
      ['Window', strat.window||'—'],
      ['Live mode', strat.live_mode?'YES':'NO'],
      ['Symbols', (strat.symbols||[]).map(x=>x.key).join(', ')||'—'],
      ['Lots/sym', (strat.symbols||[]).map(x=>`${x.key}:${x.max_lots}`).join(' ')||'—'],
    ].map(([k,v])=>`<div class="kv"><span class="k">${k}</span><span class="v">${v}</span></div>`).join('');
  }
  // regime
  if (regime){
    $('#regime-body').innerHTML = [
      ['Current', regime.current||'—'],
      ['ADX', NUM(regime.current_adx,2)],
      ['Regimes seen', (regime.regimes&&Object.keys(regime.regimes).length)||0],
    ].map(([k,v])=>`<div class="kv"><span class="k">${k}</span><span class="v">${v}</span></div>`).join('');
  }
  // market
  if (mkt) $('#strat-sub').textContent = `Market: ${mkt.status}`;
  // log tail
  if (log){
    let lines = [];
    if (Array.isArray(log)) lines = log;
    else if (log.lines) lines = log.lines;
    else if (log.tail) lines = log.tail.split('\n');
    else if (typeof log==='string') lines = log.split('\n');
    const fmt = (l)=>{
      const s = String(l);
      let cls = '';
      if (/ERROR|Traceback|Exception/i.test(s)) cls='log-err';
      else if (/WARN/i.test(s)) cls='log-warn';
      else cls='log-info';
      return `<span class="${cls}">${s.replace(/</g,'&lt;')}</span>`;
    };
    $('#log-tail').innerHTML = lines.slice(-60).map(fmt).join('\n');
  }
}

/* ---------- ORCHESTRATION ---------- */
async function refreshCore(){
  const [status, trades] = await Promise.all([ getJ('/api/status'), getJ('/api/trades') ]);
  state.status = status||{};
  state.trades = trades||{};
  state.tradesArr = (trades && trades.trades) || [];
  renderTopbar();
  // metrics
  const today = todayIso();
  const todayTrades = state.tradesArr.filter(t=> (t.entry_ts||'').startsWith(today) || (t.exit_ts||'').startsWith(today));
  const todayPnl = todayTrades.reduce((s,t)=>s+(t.pnl||0),0);
  const wins = state.tradesArr.filter(t=>t.pnl>0).length;
  const losses = state.tradesArr.filter(t=>t.pnl<0).length;
  const exp = state.tradesArr.length? state.tradesArr.reduce((s,t)=>s+(t.pnl||0),0)/state.tradesArr.length : null;
  // build equity spark from cumulative pnl
  let cum = 0;
  const equityCurve = state.tradesArr.map(t=>{ cum+=(t.pnl||0); return cum; });
  const peak = equityCurve.length? Math.max(...equityCurve) : 0;
  const dd = equityCurve.length? peak - equityCurve[equityCurve.length-1] : 0;
  const ddPct = peak>0? (dd/peak*100) : 0;
  // live LTPs for ticker
  const [bnf, nf, mcn] = await Promise.all([ getJ('/api/live/state?symbol=BNF'), getJ('/api/live/state?symbol=NF'), getJ('/api/live/state?symbol=MCN') ]);
  renderTicker({BNF:bnf,NF:nf,MCN:mcn}, trades.total_pnl, todayPnl, trades.win_rate, status&&status.heartbeat_age_s);
  // overview
  renderKpis({
    cumPnl: trades.total_pnl,
    todayPnl, tradesToday: todayTrades.length,
    winRate: trades.win_rate, wins, losses,
    expectancy: exp,
    maxDD: dd, maxDDPct: ddPct,
    tradeCount: trades.count,
    botStatus: status&&status.bot_status, botSev: status&&status.bot_status_severity,
    hbAge: status&&status.heartbeat_age_s,
    equitySpark: equityCurve.slice(-30),
  });
  renderRecent(state.tradesArr);
  const eqPts = equityCurve.map((y,i)=>({x:i, y}));
  lineChart('chart-eq-overview', eqPts, {cls:'eq'});
  state.lastEqPts = eqPts;
  $('#eq-sub').textContent = `${equityCurve.length} trades · peak ${INR(peak)}`;
  $('#refresh-status').textContent = 'Live · updated '+new Date().toLocaleTimeString('en-IN',{hour12:false});
}
async function refreshAll(){
  await refreshCore();
  if (currentTab==='trades')       renderTradesTab();
  if (currentTab==='live')         await refreshLive();
  if (currentTab==='performance')  await refreshPerf();
  if (currentTab==='system')       await refreshSystem();
}

/* ---------- BOOT ---------- */
document.addEventListener('DOMContentLoaded', ()=>{
  initTheme(); initTabs(); setupTradeFilters();
  refreshAll();
  setInterval(refreshAll, 5000);
});
})();
