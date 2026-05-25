"""Phase 8g: multi-instrument config tests.

Phase 9.8g.9 (25 May 2026 audit Track 1): FNF -> MCN throughout.
FNF was deprecated in Phase 9.7O (15 May 2026); production
INSTRUMENT_CFG keys are now {BNF, NF, MCN}.
"""
import importlib


def test_default_instruments(monkeypatch):
    monkeypatch.setenv("INSTRUMENTS", "BNF")
    import ou_mrs
    importlib.reload(ou_mrs)
    assert ou_mrs.INSTRUMENTS == ["BNF"]


def test_three_instruments(monkeypatch):
    monkeypatch.setenv("INSTRUMENTS", "BNF,NF,MCN")
    import ou_mrs
    importlib.reload(ou_mrs)
    assert ou_mrs.INSTRUMENTS == ["BNF", "NF", "MCN"]


def test_unknown_instrument_filtered(monkeypatch):
    monkeypatch.setenv("INSTRUMENTS", "BNF,XYZ,NF")
    import ou_mrs
    importlib.reload(ou_mrs)
    assert ou_mrs.INSTRUMENTS == ["BNF", "NF"]


def test_lowercase_normalized(monkeypatch):
    monkeypatch.setenv("INSTRUMENTS", "bnf,nf,mcn")
    import ou_mrs
    importlib.reload(ou_mrs)
    assert ou_mrs.INSTRUMENTS == ["BNF", "NF", "MCN"]


def test_cfg_required_keys():
    import ou_mrs
    importlib.reload(ou_mrs)
    required = ("symbol", "token", "lot_size", "margin_per_lot", "atr_mult", "exchange")
    for sym in ("BNF", "NF", "MCN"):
        cfg = ou_mrs.INSTRUMENT_CFG[sym]
        for key in required:
            assert key in cfg, f"{sym} missing {key}"
        assert cfg["lot_size"] > 0
        assert cfg["margin_per_lot"] > 0
        assert cfg["exchange"] == "NFO"
