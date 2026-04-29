# Phase 9.5c: realistic FnO round-trip cost model

DEF_COSTS = {
    "brokerage_per_order": 20.0,
    "stt_pct_sell": 0.0125 / 100,
    "txn_pct": 0.0019 / 100,
    "sebi_pct": 0.0001 / 100,
    "gst_pct": 18.0 / 100,
    "stamp_pct_buy": 0.002 / 100,
}


def compute_rt_cost(entry_price, exit_price, lot_size, qty_lots=1, costs=None):
    if costs is None:
        costs = DEF_COSTS
    contracts = lot_size * qty_lots
    ne = entry_price * contracts
    nx = exit_price * contracts
    brokerage = costs["brokerage_per_order"] * 2
    sell_notional = max(ne, nx)
    stt = sell_notional * costs["stt_pct_sell"]
    txn = (ne + nx) * costs["txn_pct"]
    sebi = (ne + nx) * costs["sebi_pct"]
    gst = (brokerage + txn + sebi) * costs["gst_pct"]
    buy_notional = min(ne, nx)
    stamp = buy_notional * costs["stamp_pct_buy"]
    return brokerage + stt + txn + sebi + gst + stamp
