"""Phase 8f.2: account isolation tests."""
import os
import importlib
import shutil
from pathlib import Path


def test_default_account_id():
    os.environ.pop("ACCOUNT_ID", None)
    import account
    importlib.reload(account)
    assert account.ACCOUNT_ID == "primary"


def test_state_dir_creates_path():
    import account
    importlib.reload(account)
    d = account.state_dir("test_isolated_xyz")
    try:
        assert d.exists() and d.is_dir()
        assert d.name == "test_isolated_xyz"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_equity_log_per_account():
    from account import equity_log_path
    p1 = equity_log_path("alpha_test")
    p2 = equity_log_path("beta_test")
    try:
        assert p1 != p2
        assert "alpha_test" in str(p1)
        assert "beta_test" in str(p2)
    finally:
        shutil.rmtree(p1.parent, ignore_errors=True)
        shutil.rmtree(p2.parent, ignore_errors=True)


def test_sl_orders_log_per_account():
    from account import sl_orders_log_path
    p = sl_orders_log_path("gamma_test")
    try:
        assert p.name == "sl_orders.jsonl"
        assert "gamma_test" in str(p)
    finally:
        shutil.rmtree(p.parent, ignore_errors=True)


def test_env_var_override():
    os.environ["ACCOUNT_ID"] = "ff_pool_42"
    import account
    importlib.reload(account)
    try:
        assert account.ACCOUNT_ID == "ff_pool_42"
        assert "ff_pool_42" in str(account.equity_log_path())
    finally:
        os.environ.pop("ACCOUNT_ID", None)
        importlib.reload(account)
        shutil.rmtree(Path("state") / "ff_pool_42", ignore_errors=True)


# Phase 8g.3: per-symbol path scoping
def test_sl_orders_log_path_with_symbol(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from account import sl_orders_log_path
    p = sl_orders_log_path(account_id="alpha8g3", symbol="BNF")
    assert "alpha8g3" in str(p)
    assert "BNF" in str(p)
    assert str(p).endswith("sl_orders.jsonl")
    assert p.parent.exists()


def test_sl_orders_log_path_no_symbol_backcompat(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from account import sl_orders_log_path
    p = sl_orders_log_path("legacy8g3")
    assert "legacy8g3" in str(p)
    assert p.parent.name == "legacy8g3"
    assert "/BNF/" not in str(p)


def test_state_dir_symbol_isolation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import account
    bnf = account.state_dir("isoacct8g3", symbol="BNF")
    nf = account.state_dir("isoacct8g3", symbol="NF")
    assert bnf != nf
    assert bnf.exists() and nf.exists()
    assert bnf.parent == nf.parent
