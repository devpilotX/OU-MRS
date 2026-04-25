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
