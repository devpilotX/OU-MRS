/* OU-MRS Dashboard 2.0 (v2) - Phase 9.8h.I parallel mount
 *
 * Reads from existing /api/* endpoints (auth handled by FastAPI session cookie).
 * Builds 4-6 Card components + recent-trades table. Refreshes every 5s.
 */
(function () {
	"use strict";

	function fmtInr(n) {
		if (n == null || Number.isNaN(Number(n))) return "\u2014";
		const sign = n >= 0 ? "+" : "\u2212";
		return sign + "\u20b9" + Math.abs(Number(n)).toLocaleString("en-IN", { maximumFractionDigits: 0 });
	}
	function fmtPct(n) {
		if (n == null || Number.isNaN(Number(n))) return "\u2014";
		return (n >= 0 ? "+" : "") + Number(n).toFixed(2) + "%";
	}
	function $(s, p) { return (p || document).querySelector(s); }

	async function fetchJson(url) {
		try {
			const r = await fetch(url, { credentials: "same-origin" });
			if (!r.ok) return null;
			return await r.json();
		} catch (_) { return null; }
	}

	function makeCard({ header, metric, supporting, tone }) {
		const el = document.createElement("div");
		el.className = "ou-card" + (tone ? " " + tone : "");
		const h = document.createElement("div");
		h.className = "ou-card-header";
		h.textContent = header;
		el.appendChild(h);
		const m = document.createElement("div");
		m.className = "ou-card-metric";
		m.textContent = metric;
		el.appendChild(m);
		if (supporting && supporting.length) {
			const s = document.createElement("div");
			s.className = "ou-card-supporting";
			supporting.forEach(function (t) {
				const span = document.createElement("span");
				span.textContent = t;
				s.appendChild(span);
			});
			el.appendChild(s);
		}
		return el;
	}

	async function render() {
		const grid = $("#v2-grid");
		const status = await fetchJson("/api/status");
		const metrics = await fetchJson("/api/metrics");
		const trades = await fetchJson("/api/trades");
		const portfolio = await fetchJson("/api/portfolio");
		const health = await fetchJson("/api/health");

		grid.innerHTML = "";

		const cumPnl = (portfolio && portfolio.pfm && portfolio.pfm.cumulative_pnl) || 0;
		const todayPnl = (status && status.pnl_today) || 0;
		const tradesToday = (status && status.trades_today) || 0;
		const daysTraded = (portfolio && portfolio.pfm && portfolio.pfm.days_traded) || 0;

		grid.appendChild(makeCard({
			header: "Cumulative P&L",
			metric: fmtInr(cumPnl),
			supporting: ["days traded: " + daysTraded, "all-time"],
			tone: cumPnl >= 0 ? "ou-profit" : "ou-loss",
		}));
		grid.appendChild(makeCard({
			header: "Today's P&L",
			metric: fmtInr(todayPnl),
			supporting: ["trades: " + tradesToday],
			tone: todayPnl > 0 ? "ou-profit" : todayPnl < 0 ? "ou-loss" : "ou-idle",
		}));
		grid.appendChild(makeCard({
			header: "Bot status",
			metric: (status && status.bot_active) ? "ALIVE" : "OFFLINE",
			supporting: [
				"dashboard: " + (health && health.dashboard ? "up" : "down"),
				"feed: " + (health && health.feed ? health.feed : "\u2014"),
			],
			tone: (status && status.bot_active) ? "ou-profit" : "ou-critical",
		}));
		grid.appendChild(makeCard({
			header: "Metrics",
			metric: metrics && metrics.win_rate != null ? fmtPct(metrics.win_rate * 100) : "\u2014",
			supporting: [
				"win rate",
				metrics && metrics.expectancy_inr != null ? "E[\u20b9]: " + fmtInr(metrics.expectancy_inr) : "\u2014",
			],
			tone: "ou-idle",
		}));

		const tbody = $("#v2-trades tbody");
		tbody.innerHTML = "";
		const arr = (trades && Array.isArray(trades) ? trades : (trades && trades.trades) || []).slice(-10).reverse();
		arr.forEach(function (t) {
			const tr = document.createElement("tr");
			function td(text, cls) {
				const c = document.createElement("td");
				if (cls) c.className = cls;
				c.textContent = text == null ? "\u2014" : text;
				return c;
			}
			const entry = t.entry_ts || t.entry_ts_ist || "";
			const pnl = Number(t.pnl || 0);
			let sym = "";
			const e = Number(t.entry || 0);
			if (e > 40000) sym = "BNF"; else if (e > 20000) sym = "NF"; else if (e > 8000) sym = "MCN";
			tr.appendChild(td(entry));
			tr.appendChild(td(sym));
			tr.appendChild(td(t.side));
			tr.appendChild(td(t.qty));
			tr.appendChild(td(t.entry));
			tr.appendChild(td(t.exit));
			tr.appendChild(td(fmtInr(pnl), pnl >= 0 ? "pnl-pos" : "pnl-neg"));
			tr.appendChild(td(t.reason));
			tbody.appendChild(tr);
		});

		const now = new Date().toLocaleTimeString("en-IN", { hour12: false });
		$("#v2-refresh-status").textContent = "updated " + now;
	}

	render();
	setInterval(render, 5000);
})();
