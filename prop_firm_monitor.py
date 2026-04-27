"""Phase 8e: Prop-firm (ELITE-style) rule monitor for live paper validation."""
import json
from datetime import date
from pathlib import Path

from account import equity_log_path  # Phase 8f.2
EQUITY_LOG = equity_log_path()


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

    def check(self, pnl_today):
        equity = self.capital + self.cumulative_pnl + pnl_today
        peak = max(self.peak_equity, equity)
        dd = peak - equity
        if pnl_today <= -self.daily_loss:
            return {"state": "hard_halt", "reason": "daily_loss_hard",
                    "pnl_today": pnl_today, "dd": dd, "peak": peak}
        if dd >= self.max_dd:
            return {"state": "hard_halt", "reason": "max_dd_hard",
                    "pnl_today": pnl_today, "dd": dd, "peak": peak}
        if pnl_today <= -self.daily_loss * self.soft_halt_frac:
            return {"state": "soft_halt", "reason": "daily_loss_soft",
                    "pnl_today": pnl_today, "dd": dd, "peak": peak}
        if dd >= self.max_dd * self.soft_halt_frac:
            return {"state": "soft_halt", "reason": "dd_soft",
                    "pnl_today": pnl_today, "dd": dd, "peak": peak}
        return {"state": "ok", "reason": "within_limits",
                "pnl_today": pnl_today, "dd": dd, "peak": peak}

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
