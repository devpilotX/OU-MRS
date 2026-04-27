"""Phase 8g.6: tests for per-symbol live state writer."""
import json
import live_hook


def test_tick_symbol_writes_per_symbol_file(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setattr(live_hook, "_STATE", state_dir / "live.json")
    live_hook.tick_symbol(symbol="BNF", ltp=56500, state="idle", trades_today=0, pnl_today=0.0, max_lots=2, lot_size=30)
    out = state_dir / "live_BNF.json"
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["symbol"] == "BNF"
    assert data["ltp"] == 56500
    assert data["state"] == "idle"
    assert data["max_lots"] == 2
    assert data["lot_size"] == 30


def test_tick_symbol_writes_position(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setattr(live_hook, "_STATE", state_dir / "live.json")
    pos = {"side": "BUY", "qty": 2, "entry": 56400.0, "unrealized_pnl": 120.0}
    live_hook.tick_symbol(symbol="NF", state="in_trade", position=pos, trades_today=1, pnl_today=120.0)
    data = json.loads((state_dir / "live_NF.json").read_text())
    assert data["position"]["side"] == "BUY"
    assert data["position"]["qty"] == 2
    assert data["pnl_today"] == 120.0
    assert data["state"] == "in_trade"


def test_tick_symbol_never_raises_on_bad_path(tmp_path, monkeypatch):
    bad_path = tmp_path / "nonexistent_dir" / "live.json"
    monkeypatch.setattr(live_hook, "_STATE", bad_path)
    try:
        live_hook.tick_symbol(symbol="FNF", state="idle")
    except Exception as e:
        raise AssertionError(f"tick_symbol raised: {e}")


def test_tick_symbol_isolates_state_per_symbol(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setattr(live_hook, "_STATE", state_dir / "live.json")
    live_hook.tick_symbol(symbol="BNF", state="in_trade", pnl_today=100.0)
    live_hook.tick_symbol(symbol="NF", state="cooldown", pnl_today=-50.0)
    bnf = json.loads((state_dir / "live_BNF.json").read_text())
    nf = json.loads((state_dir / "live_NF.json").read_text())
    assert bnf["state"] == "in_trade" and bnf["pnl_today"] == 100.0
    assert nf["state"] == "cooldown" and nf["pnl_today"] == -50.0


def test_tick_symbol_writes_rich_fields_8o3c():
    """8o.3c: tick_symbol writes z, mean, std, intraday_candles, depth, ohlc_today, portfolio, etc."""
    import live_hook, json
    from pathlib import Path
    live_hook.tick_symbol(
        symbol="TEST8O3C",
        ltp=100.5, z=1.8, mean=99.2, std=0.7, window=40,
        z_entry=1.5, z_stop=3.5, candles_count=42,
        intraday_candles=[{"o": 100, "h": 101, "l": 99, "c": 100.5}],
        depth={"bids": [{"price": 100.4, "qty": 30}], "asks": [{"price": 100.6, "qty": 30}]},
        ohlc_today={"o": 100, "h": 102, "l": 99, "c": 100.5},
        next_check_in_sec=15, portfolio={"cash": 1000, "pnl": 50},
        state="idle", position=None,
        trades_today=2, pnl_today=150.0, kill=False,
        max_lots=10, lot_size=30, reasons_log=["test reason"],
    )
    p = Path(live_hook.__file__).parent / "state" / "live_TEST8O3C.json"
    d = json.loads(p.read_text())
    # Verify all 8o.3c rich fields propagate
    assert d["z"] == 1.8
    assert d["mean"] == 99.2
    assert d["std"] == 0.7
    assert d["window"] == 40
    assert d["z_entry"] == 1.5
    assert d["z_stop"] == 3.5
    assert d["candles_count"] == 42
    assert d["intraday_candles"][0]["c"] == 100.5
    assert d["depth"]["bids"][0]["price"] == 100.4
    assert d["ohlc_today"]["h"] == 102
    assert d["next_check_in_sec"] == 15
    assert d["portfolio"]["cash"] == 1000
    assert d["max_lots"] == 10
    assert d["lot_size"] == 30
    assert d["reasons_log"] == ["test reason"]
    p.unlink()  # cleanup