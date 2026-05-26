"""Phase 9.8h.B.2 regression tests.

Guard the data-quality fix that emits `symbol` on every trades.jsonl row.
The May 12 forensic (Phase 9.8h.B.1) was made significantly harder because
trades.jsonl rows had no symbol field and symbols had to be inferred from
price magnitude. These tests prevent silent regression of that fix.
"""
import ast
import re
from pathlib import Path

import pytest

OU_MRS = Path(__file__).resolve().parents[1] / "ou_mrs.py"


def _get_exit_fn_ast() -> ast.FunctionDef:
    """Return the AST node for the module-level `_exit` function."""
    tree = ast.parse(OU_MRS.read_text())
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_exit":
            return node
    pytest.fail("_exit function not found in ou_mrs.py")


def test_exit_signature_has_no_misleading_symbol_default():
    """Phase 9.8h.B.2: drop the symbol=\"BNF\" default that could silently
    mislabel trades if a caller forgot the kwarg."""
    fn = _get_exit_fn_ast()
    arg_names = [a.arg for a in fn.args.args]
    defaults = list(fn.args.defaults)
    default_map = dict(zip(arg_names[-len(defaults):] if defaults else [], defaults))
    assert "symbol" in arg_names, "_exit must accept `symbol` parameter"
    assert "symbol" not in default_map, (
        "_exit must not have a default value for `symbol` (Phase 9.8h.B.2): "
        "a silent default risks mislabeling trades."
    )


def test_exit_writes_symbol_field_to_trades_jsonl():
    """The trades.jsonl write block inside _exit must include `\"symbol\": symbol`."""
    src = OU_MRS.read_text()
    pattern = re.compile(
        r'"reason":\s*reason,\s*\n\s*"symbol":\s*symbol,'
    )
    assert pattern.search(src), (
        "trades.jsonl write block must include `\"symbol\": symbol,` after "
        '`\"reason\": reason,` (Phase 9.8h.B.2 data-quality fix).'
    )


def test_exit_callers_pass_symbol_explicitly():
    """All call sites of _exit must pass symbol=runner.symbol (not rely on
    positional ordering or a default).

    Match `_exit(` only when not preceded by an identifier character
    (so `publish_exit(` and similar function names don't false-positive).
    """
    src = OU_MRS.read_text()
    call_re = re.compile(r"(?<![A-Za-z0-9_])_exit\([^)]*\)")
    sig_re = re.compile(r"^\s*def\s+_exit\(")
    bad = []
    for lineno, line in enumerate(src.splitlines(), start=1):
        if sig_re.match(line):
            continue
        for m in call_re.finditer(line):
            call = m.group(0)
            if "symbol=" not in call:
                bad.append((lineno, line.strip()))
    assert not bad, (
        "Every _exit() call must pass `symbol=...` explicitly. Offending sites: "
        + repr(bad)
    )
