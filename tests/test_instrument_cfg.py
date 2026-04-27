"""Phase 8g: multi-instrument config tests."""
import importlib


def test_default_instruments(monkeypatch):
    monkeypatch.setenv("INSTRUMENTS", "BNF")
    import ou_mrs
    importlib.reload(ou_mrs)
    assert ou_mrs.INSTRUMENTS == ["BNF"]


def test_three_instruments(monkeypatch):
    monkeypatch.setenv("INSTRUMENTS", "BNF,NF,FNF")
    import ou_mrs
    importlib.reload(ou_mrs)
    assert ou_mrs.INSTRUMENTS == ["BNF", "NF", "FNF"]


def test_unknown_instrument_filtered(monkeypatch):
    monkeypatch.setenv("INSTRUMENTS", "BNF,XYZ,NF")
    import ou_mrs
    importlib.reload(ou_mrs)
    assert ou_mrs.INSTRUMENTS == ["BNF", "NF"]


def test_lowercase_normalized(monkeypatch):
    monkeypatch.setenv("INSTRUMENTS", "bnf,nf,fnf")
    import ou_mrs
    importlib.reload(ou_mrs)
    assert ou_mrs.INSTRUMENTS == ["BNF", "NF", "FNF"]


def test_cfg_required_keys():
    import ou_mrs
    importlib.reload(ou_mrs)
    required = ("symbol", "token", "lot_size", "margin_per_lot", "atr_mult", "exchange")
    for sym in ("BNF", "NF", "FNF"):
        cfg = ou_mrs.INSTRUMENT_CFG[sym]
        for key in required:
            assert key in cfg, f"{sym} missing {key}"
        assert cfg["lot_size"] > 0
        assert cfg["margin_per_lot"] > 0
        assert cfg["exchange"] == "NFO"

