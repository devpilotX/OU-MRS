"""
Phase 9.8f.53 v2: Brokerage + charges calculator (Angel feature 4).
Indian F&O total trade costs per Angel One tariffs (May 2026). Stdlib only.
"""
FNO_BROKERAGE_PER_ORDER = 20.0
FNO_BROKERAGE_PCT = 0.0003
STT_FUT_SELL = 0.000125
STT_OPT_SELL_PREMIUM = 0.000625
EXCH_FUT = 0.000019
EXCH_OPT = 0.0005
SEBI_PCT = 0.000001
STAMP_FUT_BUY = 0.00002
STAMP_OPT_BUY = 0.00003
GST_PCT = 0.18


def calc_charges(instrument, side, qty, price):
	instrument = (instrument or "").lower()
	side = (side or "").lower()
	qty = float(qty)
	price = float(price)
	turnover = qty * price
	if turnover <= 0:
		return {"error": "turnover_zero", "turnover": 0.0}
	brokerage = min(FNO_BROKERAGE_PER_ORDER, turnover * FNO_BROKERAGE_PCT)
	stt = 0.0
	if side == "sell":
		if instrument == "fut":
			stt = turnover * STT_FUT_SELL
		elif instrument == "opt":
			stt = turnover * STT_OPT_SELL_PREMIUM
	if instrument == "fut":
		exch = turnover * EXCH_FUT
	else:
		exch = turnover * EXCH_OPT
	sebi = turnover * SEBI_PCT
	stamp = 0.0
	if side == "buy":
		if instrument == "fut":
			stamp = turnover * STAMP_FUT_BUY
		else:
			stamp = turnover * STAMP_OPT_BUY
	gst = (brokerage + exch + sebi) * GST_PCT
	total = brokerage + stt + exch + sebi + stamp + gst
	return {"instrument": instrument, "side": side, "qty": qty, "price": price, "turnover": round(turnover, 2), "brokerage": round(brokerage, 2), "stt": round(stt, 2), "exchange": round(exch, 4), "sebi": round(sebi, 4), "stamp_duty": round(stamp, 4), "gst": round(gst, 2), "total_charges": round(total, 4), "breakeven_points_per_unit": round(total / qty, 4) if qty > 0 else 0}


def calc_roundtrip(instrument, qty, buy_price, sell_price):
	buy = calc_charges(instrument, "buy", qty, buy_price)
	sell = calc_charges(instrument, "sell", qty, sell_price)
	gross = (float(sell_price) - float(buy_price)) * float(qty)
	tc = buy.get("total_charges", 0.0) + sell.get("total_charges", 0.0)
	net = gross - tc
	invested = float(buy_price) * float(qty)
	pnl_pct = (net / invested * 100.0) if invested > 0 else 0.0
	return {"instrument": instrument, "qty": float(qty), "buy_price": float(buy_price), "sell_price": float(sell_price), "gross_pnl": round(gross, 2), "total_charges": round(tc, 4), "net_pnl": round(net, 2), "pnl_pct": round(pnl_pct, 4), "buy_leg": buy, "sell_leg": sell}


# Phase 9.8f.63: F&O lot sizes for Underlying+Lots UX (NSE/BSE May 2026)
LOT_SIZES = {
    "NIFTY": 65,
    "BANKNIFTY": 30,
    "FINNIFTY": 60,
    "MIDCPNIFTY": 120,
    "SENSEX": 20,
    "BANKEX": 30,
    "RELIANCE": 500,
    "HDFCBANK": 550,
    "TCS": 175,
    "INFY": 400,
    "CUSTOM": 1,
}


def resolve_qty(underlying="", lots=0, qty=None):
    """Resolve effective qty from (underlying, lots) or legacy qty."""
    u = (underlying or "").upper().strip()
    if u and u in LOT_SIZES and u != "CUSTOM":
        ls = LOT_SIZES[u]
        return {"qty": int(float(lots or 0) * ls), "lot_size": ls, "underlying": u}
    return {"qty": int(float(qty or 0)), "lot_size": 1, "underlying": "CUSTOM"}


# Phase 9.8f.64: Margin Calculator - NSE-published SPAN + Exposure approximation
# Sourced from NSE Clearing average margins, May 2026 expiry cycle.
# Index futures 11-14% notional, stock futures 17-18%, options buy = full premium,
# options sell = SPAN + Exposure + premium held as collateral.
MARGIN_RATES = {
	"NIFTY":      {"span_pct": 0.080, "exposure_pct": 0.035, "type": "index"},
	"BANKNIFTY":  {"span_pct": 0.090, "exposure_pct": 0.035, "type": "index"},
	"FINNIFTY":   {"span_pct": 0.090, "exposure_pct": 0.035, "type": "index"},
	"MIDCPNIFTY": {"span_pct": 0.100, "exposure_pct": 0.040, "type": "index"},
	"SENSEX":     {"span_pct": 0.080, "exposure_pct": 0.035, "type": "index"},
	"BANKEX":     {"span_pct": 0.090, "exposure_pct": 0.035, "type": "index"},
	"RELIANCE":   {"span_pct": 0.130, "exposure_pct": 0.050, "type": "stock"},
	"HDFCBANK":   {"span_pct": 0.130, "exposure_pct": 0.050, "type": "stock"},
	"TCS":        {"span_pct": 0.130, "exposure_pct": 0.050, "type": "stock"},
	"INFY":       {"span_pct": 0.130, "exposure_pct": 0.050, "type": "stock"},
	"CUSTOM":     {"span_pct": 0.100, "exposure_pct": 0.040, "type": "index"},
}

def compute_margin(underlying="BANKNIFTY", lots=1, instrument="fut", side="buy", price=53780.0, premium=200.0, lot_size=None):
	u = (underlying or "BANKNIFTY").upper()
	rates = MARGIN_RATES.get(u, MARGIN_RATES["CUSTOM"])
	ls = lot_size if lot_size else LOT_SIZES.get(u, 1)
	qty = float(lots) * ls
	notional = qty * float(price)
	if instrument == "fut":
		span = notional * rates["span_pct"]
		exposure = notional * rates["exposure_pct"]
		premium_paid = 0.0
		total = span + exposure
	elif instrument in ("opt_buy", "ce_buy", "pe_buy"):
		span = 0.0
		exposure = 0.0
		premium_paid = float(premium) * qty
		total = premium_paid
	elif instrument in ("opt_sell", "ce_sell", "pe_sell"):
		span = notional * rates["span_pct"] * 1.2
		exposure = notional * rates["exposure_pct"]
		premium_paid = float(premium) * qty
		total = span + exposure + premium_paid
	else:
		span = notional * rates["span_pct"]
		exposure = notional * rates["exposure_pct"]
		premium_paid = 0.0
		total = span + exposure
	return {
		"underlying": u,
		"lots": float(lots),
		"lot_size": ls,
		"qty": int(qty),
		"instrument": instrument,
		"side": side,
		"price": float(price),
		"premium": float(premium),
		"notional": round(notional, 2),
		"span_pct": rates["span_pct"],
		"exposure_pct": rates["exposure_pct"],
		"span_margin": round(span, 2),
		"exposure_margin": round(exposure, 2),
		"premium_paid": round(premium_paid, 2),
		"initial_margin": round(total, 2),
		"leverage": round((notional / total), 2) if total > 0 else 0,
	}
