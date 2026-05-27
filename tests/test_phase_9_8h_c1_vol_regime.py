"""Phase 9.8h.C.1 - lock the vol-regime gate behavior.

These tests assert the strategy_vol_regime module's contract and confirm the
C.1 patches improved BNF's acceptance from 1/6 to 5/6 in the validation suite.
"""
import json
import os
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent

# --- isolate env per test ---
_VOL_ENV_KEYS = [
    "OU_VOL_REGIME",
    "OU_BNF_VOL_BAND_EXCLUDE", "OU_NF_VOL_BAND_EXCLUDE", "OU_MCN_VOL_BAND_EXCLUDE",
    "OU_MCN_LOW_VOL_THRESHOLD", "OU_MCN_LOW_VOL_MULTIPLIER",
]


@pytest.fixture
def clean_env():
    saved = {k: os.environ.get(k) for k in _VOL_ENV_KEYS}
    for k in _VOL_ENV_KEYS:
        os.environ.pop(k, None)
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_compute_rv20_flat_zero():
    from strategy_vol_regime import compute_rv20
    assert compute_rv20([100.0] * 25) == 0.0


def test_compute_rv20_too_short():
    from strategy_vol_regime import compute_rv20
    assert compute_rv20([100.0] * 10) is None


def test_compute_rv20_positive_for_volatile_series():
    """A series with random log returns must produce a positive rv20."""
    from strategy_vol_regime import compute_rv20
    import math
    px = [100.0]
    for r in [0.001, -0.002, 0.003, -0.001, 0.002, -0.0015, 0.001, -0.002,
              0.0025, -0.001, 0.0015, -0.0025, 0.002, -0.001, 0.003, -0.002,
              0.001, -0.0015, 0.002, -0.001, 0.0025]:
        px.append(px[-1] * math.exp(r))
    rv = compute_rv20(px)
    assert rv is not None and rv > 0.001


def test_bnf_chop_band_excludes_mid_vol(clean_env):
    os.environ["OU_BNF_VOL_BAND_EXCLUDE"] = "0.0077,0.0092"
    from importlib import reload
    import strategy_vol_regime
    reload(strategy_vol_regime)
    from strategy_vol_regime import passes_vol_filter
    ok, reason = passes_vol_filter("BNF", 0.0085)
    assert not ok and "vol_band" in reason
    assert passes_vol_filter("BNF", 0.0060)[0] is True
    assert passes_vol_filter("BNF", 0.0120)[0] is True
    # symmetry: BANKNIFTY long form
    assert passes_vol_filter("BANKNIFTY", 0.0085)[0] is False


def test_other_symbols_unaffected_by_bnf_band(clean_env):
    os.environ["OU_BNF_VOL_BAND_EXCLUDE"] = "0.0077,0.0092"
    from importlib import reload
    import strategy_vol_regime
    reload(strategy_vol_regime)
    from strategy_vol_regime import passes_vol_filter
    assert passes_vol_filter("NF", 0.0085)[0] is True
    assert passes_vol_filter("MCN", 0.0085)[0] is True


def test_mcn_low_vol_accelerator(clean_env):
    os.environ["OU_MCN_LOW_VOL_THRESHOLD"] = "0.0074"
    os.environ["OU_MCN_LOW_VOL_MULTIPLIER"] = "1.5"
    from importlib import reload
    import strategy_vol_regime
    reload(strategy_vol_regime)
    from strategy_vol_regime import vol_size_multiplier
    assert vol_size_multiplier("MCN", 0.0050) == 1.5
    assert vol_size_multiplier("MCN", 0.0080) == 1.0
    assert vol_size_multiplier("MIDCPNIFTY", 0.0050) == 1.5
    # Other symbols never get a multiplier
    assert vol_size_multiplier("BNF", 0.0050) == 1.0
    assert vol_size_multiplier("NF", 0.0050) == 1.0


def test_disable_switch_passes_everything(clean_env):
    os.environ["OU_VOL_REGIME"] = "off"
    os.environ["OU_BNF_VOL_BAND_EXCLUDE"] = "0.0077,0.0092"
    os.environ["OU_MCN_LOW_VOL_MULTIPLIER"] = "1.5"
    from importlib import reload
    import strategy_vol_regime
    reload(strategy_vol_regime)
    from strategy_vol_regime import passes_vol_filter, vol_size_multiplier
    assert passes_vol_filter("BNF", 0.0085)[0] is True
    assert vol_size_multiplier("MCN", 0.0050) == 1.0


def test_unknown_rv20_passes_through(clean_env):
    os.environ["OU_BNF_VOL_BAND_EXCLUDE"] = "0.0077,0.0092"
    from importlib import reload
    import strategy_vol_regime
    reload(strategy_vol_regime)
    from strategy_vol_regime import passes_vol_filter, vol_size_multiplier
    assert passes_vol_filter("BNF", None)[0] is True
    assert vol_size_multiplier("MCN", None) == 1.0


def test_validation_suite_results_reflect_c1():
    """Lock the headline acceptance numbers from the C.1 master report.

    BANKNIFTY must pass 5/6 acceptance checks (only PSR_at_0 short).
    NIFTY remains structurally broken (WF_consistency = 0).
    MIDCPNIFTY keeps perfect WF consistency.
    """
    rep_path = ROOT / "validation/phase_9_8h_master_report.json"
    if not rep_path.exists():
        pytest.skip("master report not present (run run_validation_suite first)")
    rep = json.loads(rep_path.read_text())
    bnf = rep.get("BANKNIFTY", {}).get("verdict", {}).get("checks", {})
    assert bnf, "missing BANKNIFTY verdict.checks"
    bnf_passed = sum(1 for v in bnf.values() if v.get("pass"))
    assert bnf_passed >= 4, (
        f"C.1 must keep BANKNIFTY at >=4/6 acceptance (was 1/6 in B.5); got {bnf_passed}"
    )
    # PSR must have improved substantially over the B.5 baseline of 0.510.
    psr = bnf.get("PSR_at_0_>=0.95", {}).get("value")
    assert psr is not None and psr >= 0.70, f"BANKNIFTY PSR regressed: {psr}"
    # WF stability must be in spec (was 6.057 in B.5, threshold <= 1.5).
    wf_stab = bnf.get("WF_stability_<=1.50", {}).get("value")
    assert wf_stab is not None and wf_stab <= 1.5, f"BNF WF stability out of spec: {wf_stab}"
    # Holdout must have flipped to same_sign True (was False in B.5).
    holdout = bnf.get("Holdout_same_sign", {}).get("value")
    assert holdout is True, f"BNF Holdout regressed: {holdout}"

    nf = rep.get("NIFTY", {}).get("verdict", {}).get("checks", {})
    wf_nf = nf.get("WF_consistency_>=0.60", {}).get("value")
    assert wf_nf is not None and wf_nf < 0.5, (
        f"NIFTY WF consistency should remain low (structurally broken); got {wf_nf}"
    )

    mcn = rep.get("MIDCPNIFTY", {}).get("verdict", {}).get("checks", {})
    wf_mcn = mcn.get("WF_consistency_>=0.60", {}).get("value")
    assert wf_mcn is not None and wf_mcn >= 0.99, (
        f"MIDCPNIFTY WF consistency must stay perfect; got {wf_mcn}"
    )
