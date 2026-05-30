"""Phase 8e: Prop-firm rule monitor for live paper validation.

Phase 9.5e (refactored A7): sticky halt persistence integrated as proper class
methods instead of module-load monkey patches. Halt state survives process
restarts within the same trading day via state/pfm_halt.json.
"""
import json
import os
from datetime import date, datetime
from pathlib import Path

from account import equity_log_path  # Phase 8f.2

EQUITY_LOG = equity_log_path()
# Phase A5; Phase 9.8h.N+: overridable via OU_PFM_HALT_PATH so backtests and
# unit tests never mutate the live trading halt state.
HALT_PATH = Path(
    os.environ.get(
        "OU_PFM_HALT_PATH",
        str(Path(__file__).resolve().parent / "state" / "pfm_halt.json"),
    )
)


def _today_iso():
    return date.today().isoformat()


class PropFirmMonitor:
    def __init__(self, capital, daily_loss_pct=0.05, max_dd_pct=0.10,
                 profit_target_pct=0.10, soft_halt_frac=0.80, min_trading_days=4):
        self.capital = float(capital)
        self.daily_loss = daily_loss_pct * self.capital
        self.max_dd = max_dd_pct * self.capital
        self.profit_target = profit_target_pct * self.capital
        self.soft_halt_frac = soft_halt_frac
        self.min_trading_days = min_trading_days
        self.peak_equity = self.capital
        self.cumulative_pnl = 0.0
        self.days_traded = 0
        self.daily_history = []
        self._sticky_halt = None  # Phase 9.5e
        self._load_history()

    def _load_history(self):
        EQUITY_LOG.parent.mkdir(parents=True, exist_ok=True)
        if not EQUITY_LOG.exists():
            return
        try:
            with open(EQUITY_LOG) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    self.daily_history.append(rec)
                    pnl = float(rec.get("pnl", 0))
                    self.cumulative_pnl += pnl
                    if pnl != 0:
                        self.days_traded += 1
            running = self.capital
            for r in self.daily_history:
                running += float(r.get("pnl", 0))
                self.peak_equity = max(self.peak_equity, running)
        except Exception:
            pass

    def _load_halt_state(self):
        """Phase 9.5e: load today's persisted halt record if any."""
        if not HALT_PATH.exists():
            return None
        try:
            rec = json.loads(HALT_PATH.read_text())
            if rec.get("date") == _today_iso():
                return rec
        except Exception:
            pass
        return None

    def _persist_halt(self, reason, pnl_today, dd):
        """Phase 9.5e: atomically persist a hard-halt record."""
        HALT_PATH.parent.mkdir(parents=True, exist_ok=True)
        rec = {"date": _today_iso(), "ts": datetime.now().isoformat(),
               "reason": reason, "pnl_today": float(pnl_today),
               "dd": float(dd), "peak": float(self.peak_equity)}
        try:
            tmp = HALT_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(rec))
            tmp.replace(HALT_PATH)
        except Exception:
            pass
        self._sticky_halt = rec
        return rec

    def is_halted_today(self):
        """Phase 9.5e: True if a hard-halt was already triggered today."""
        if self._sticky_halt is None:
            rec = self._load_halt_state()
            if rec is not None:
                self._sticky_halt = rec
        if self._sticky_halt and self._sticky_halt.get("date") == _today_iso():
            return True
        return False

    def check(self, pnl_today):
        # Phase 9.5e: sticky-halt short-circuit
        if self.is_halted_today():
            rec = self._sticky_halt or {}
            return {"state": "hard_halt",
                    "reason": rec.get("reason", "sticky_halt"),
                    "pnl_today": pnl_today,
                    "dd": rec.get("dd", 0.0),
                    "peak": rec.get("peak", self.peak_equity)}
        equity = self.capital + self.cumulative_pnl + pnl_today
        peak = max(self.peak_equity, equity)
        dd = peak - equity
        if pnl_today <= -self.daily_loss:
            result = {"state": "hard_halt", "reason": "daily_loss_hard",
                      "pnl_today": pnl_today, "dd": dd, "peak": peak}
        elif dd >= self.max_dd:
            result = {"state": "hard_halt", "reason": "max_dd_hard",
                      "pnl_today": pnl_today, "dd": dd, "peak": peak}
        elif pnl_today <= -self.daily_loss * self.soft_halt_frac:
            result = {"state": "soft_halt", "reason": "daily_loss_soft",
                      "pnl_today": pnl_today, "dd": dd, "peak": peak}
        elif dd >= self.max_dd * self.soft_halt_frac:
            result = {"state": "soft_halt", "reason": "dd_soft",
                      "pnl_today": pnl_today, "dd": dd, "peak": peak}
        else:
            result = {"state": "ok", "reason": "within_limits",
                      "pnl_today": pnl_today, "dd": dd, "peak": peak}
        # Phase 9.5e: persist on hard_halt to survive process restart
        if result["state"] == "hard_halt":
            self._persist_halt(result["reason"], pnl_today, result["dd"])
        return result

    def end_of_day(self, pnl_today):
        EQUITY_LOG.parent.mkdir(parents=True, exist_ok=True)
        self.cumulative_pnl += pnl_today
        equity = self.capital + self.cumulative_pnl
        self.peak_equity = max(self.peak_equity, equity)
        if pnl_today != 0:
            self.days_traded += 1
        rec = {"date": date.today().isoformat(),
               "pnl": round(pnl_today, 2),
               "equity_close": round(equity, 2),
               "peak_equity": round(self.peak_equity, 2),
               "cumulative_pnl": round(self.cumulative_pnl, 2)}
        self.daily_history.append(rec)
        with open(EQUITY_LOG, "a") as f:
            f.write(json.dumps(rec) + "\n")
        return rec

    def status_summary(self):
        pnls = [float(r.get("pnl", 0)) for r in self.daily_history]
        best = max(pnls, default=0.0)
        consistency = (best / self.cumulative_pnl) if self.cumulative_pnl > 0 else 0.0
        return {"peak_equity": round(self.peak_equity, 2),
                "cumulative_pnl": round(self.cumulative_pnl, 2),
                "days_traded": self.days_traded,
                "min_days_remaining": max(0, self.min_trading_days - self.days_traded),
                "profit_target_progress": round(self.cumulative_pnl / self.profit_target, 3) if self.profit_target > 0 else 0.0,
                "best_day_pnl": round(best, 2),
                "consistency_frac": round(consistency, 3),
                "consistency_flag": consistency > 0.45}
