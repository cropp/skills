#!/usr/bin/env python3
"""
Self-analysis engine — reviews performance and updates strategy parameters.
Runs weekly (scheduled). Writes all changes and reasoning to analysis_log.

Usage:
  python3 self_analyze.py [--account paper] [--strategy rsi_mean_reversion] [--days 30]
"""
import sys
import argparse
import math
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

import db
from db import init_db
import alpaca_client as ac


# ── Performance Metrics ────────────────────────────────────────────────────────

def compute_sharpe(returns: list[float], risk_free_rate: float = 0.05) -> float | None:
    """Annualized Sharpe ratio from daily returns."""
    if len(returns) < 5:
        return None
    n       = len(returns)
    avg     = sum(returns) / n
    daily_rf = risk_free_rate / 252
    excess  = [r - daily_rf for r in returns]
    avg_ex  = sum(excess) / n
    variance = sum((r - avg_ex) ** 2 for r in excess) / (n - 1)
    std_dev  = math.sqrt(variance)
    if std_dev == 0:
        return None
    return round((avg_ex / std_dev) * math.sqrt(252), 3)


def compute_max_drawdown(equity_curve: list[float]) -> float:
    """Maximum drawdown as a negative percentage."""
    if len(equity_curve) < 2:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for val in equity_curve:
        if val > peak:
            peak = val
        dd = (val - peak) / peak * 100
        if dd < max_dd:
            max_dd = dd
    return round(max_dd, 3)


def compute_win_rate(trades: list[dict]) -> tuple[float, float, int]:
    """Returns (win_rate_pct, profit_factor, trade_count)."""
    closed = [t for t in trades if t.get("pnl") is not None]
    if not closed:
        return 0.0, 0.0, 0

    wins   = [t["pnl"] for t in closed if t["pnl"] > 0]
    losses = [abs(t["pnl"]) for t in closed if t["pnl"] < 0]

    win_rate = len(wins) / len(closed) * 100
    total_wins  = sum(wins)
    total_losses = sum(losses)
    profit_factor = (total_wins / total_losses) if total_losses > 0 else float("inf")

    return round(win_rate, 2), round(profit_factor, 3), len(closed)


# ── Parameter Adjustment Rules ─────────────────────────────────────────────────

def adjust_params(account_name: str, strategy_name: str, metrics: dict, params: dict) -> list[dict]:
    """
    Rule-based parameter adjustment.
    Returns list of changes: [{param, old_val, new_val, trigger, reasoning}]
    """
    changes = []
    sharpe      = metrics.get("sharpe")
    max_dd      = metrics.get("max_drawdown", 0)
    win_rate    = metrics.get("win_rate", 0)
    pf          = metrics.get("profit_factor", 0)
    trade_count = metrics.get("trade_count", 0)

    if trade_count < 5:
        return []  # Not enough data to adjust

    # ── Rule 1: High drawdown → tighten stop loss ──────────────────────────────
    sl = float(params.get("stop_loss_pct", 2.0))
    if max_dd < -8.0 and sl > 1.0:
        new_sl = max(1.0, round(sl - 0.25, 2))
        changes.append({
            "param":     "stop_loss_pct",
            "old_val":   sl,
            "new_val":   new_sl,
            "trigger":   f"max_drawdown={max_dd:.2f}%",
            "reasoning": f"Max drawdown of {max_dd:.2f}% exceeds -8% threshold. "
                         f"Tightening stop loss from {sl}% to {new_sl}% to limit downside."
        })

    # ── Rule 2: Low win rate → widen RSI oversold threshold (be more selective) ─
    oversold = float(params.get("rsi_oversold", 30))
    if win_rate < 45 and oversold < 25 and trade_count >= 10:
        new_oversold = max(20, round(oversold - 2, 0))
        changes.append({
            "param":     "rsi_oversold",
            "old_val":   oversold,
            "new_val":   new_oversold,
            "trigger":   f"win_rate={win_rate:.1f}%",
            "reasoning": f"Win rate of {win_rate:.1f}% below 45% threshold. "
                         f"Lowering RSI oversold from {oversold} to {new_oversold} to be more selective on entries."
        })

    # ── Rule 3: Good performance → relax stop loss slightly (let winners breathe) ─
    if sharpe and sharpe > 1.5 and win_rate > 60 and sl < 3.0:
        new_sl = round(sl + 0.25, 2)
        changes.append({
            "param":     "stop_loss_pct",
            "old_val":   sl,
            "new_val":   new_sl,
            "trigger":   f"sharpe={sharpe:.2f}, win_rate={win_rate:.1f}%",
            "reasoning": f"Strong performance (Sharpe {sharpe:.2f}, win rate {win_rate:.1f}%). "
                         f"Widening stop loss from {sl}% to {new_sl}% to reduce premature exits."
        })

    # ── Rule 4: Profit factor too low → increase take profit target ─────────────
    tp = float(params.get("take_profit_pct", 4.0))
    if pf < 1.2 and tp < 6.0 and trade_count >= 10:
        new_tp = round(tp + 0.5, 2)
        changes.append({
            "param":     "take_profit_pct",
            "old_val":   tp,
            "new_val":   new_tp,
            "trigger":   f"profit_factor={pf:.2f}",
            "reasoning": f"Profit factor of {pf:.2f} below 1.2 minimum. "
                         f"Increasing take profit target from {tp}% to {new_tp}% to improve reward/risk ratio."
        })

    # ── Rule 5: Negative Sharpe → reduce position size ────────────────────────
    max_pos_pct = float(params.get("max_position_pct", 5.0))
    if sharpe and sharpe < 0 and max_pos_pct > 2.0:
        new_pct = max(2.0, round(max_pos_pct - 0.5, 2))
        changes.append({
            "param":     "max_position_pct",
            "old_val":   max_pos_pct,
            "new_val":   new_pct,
            "trigger":   f"sharpe={sharpe:.2f}",
            "reasoning": f"Negative Sharpe ratio ({sharpe:.2f}) indicates strategy is losing money on risk-adjusted basis. "
                         f"Reducing position size from {max_pos_pct}% to {new_pct}% of equity to limit exposure."
        })

    return changes


# ── Main Analysis ──────────────────────────────────────────────────────────────

def run_analysis(account_name: str, strategy_name: str, days: int = 30):
    print(f"\n{'═'*55}")
    print(f"  Self-Analysis: {strategy_name}")
    print(f"  Account: {account_name} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Window: {days} days")
    print(f"{'═'*55}\n")

    # ── Pull portfolio history ─────────────────────────────────────────────────
    print("Fetching portfolio history...")
    try:
        history = ac.get_portfolio_history(account_name, days=days)
        equity_curve = [e for e in history["equity"] if e is not None]
        daily_returns = []
        for i in range(1, len(equity_curve)):
            if equity_curve[i-1] > 0:
                daily_returns.append((equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1])
    except Exception as e:
        print(f"  ERROR fetching portfolio history: {e}")
        equity_curve = []
        daily_returns = []

    # ── Pull trade history ─────────────────────────────────────────────────────
    print("Fetching trade history...")
    trades = db.get_trades(account_name=account_name, days=days)

    # ── Compute metrics ────────────────────────────────────────────────────────
    sharpe       = compute_sharpe(daily_returns)
    max_dd       = compute_max_drawdown(equity_curve)
    win_rate, pf, trade_count = compute_win_rate(trades)

    current_equity = equity_curve[-1] if equity_curve else None
    start_equity   = equity_curve[0]  if equity_curve else None
    total_return   = ((current_equity - start_equity) / start_equity * 100) if (current_equity and start_equity) else None

    metrics = {
        "sharpe":        sharpe,
        "max_drawdown":  max_dd,
        "win_rate":      win_rate,
        "profit_factor": pf,
        "trade_count":   trade_count,
        "total_return":  total_return,
    }

    print("\n── Performance Metrics ──────────────────────────────")
    print(f"  Total Return:    {total_return:+.2f}%" if total_return is not None else "  Total Return:    N/A")
    print(f"  Sharpe Ratio:    {sharpe:.3f}" if sharpe is not None else "  Sharpe Ratio:    N/A")
    print(f"  Max Drawdown:    {max_dd:.2f}%")
    print(f"  Win Rate:        {win_rate:.1f}%")
    print(f"  Profit Factor:   {pf:.2f}" if pf != float("inf") else "  Profit Factor:   ∞ (no losing trades)")
    print(f"  Trade Count:     {trade_count} (in last {days} days)")

    # ── Save snapshot ──────────────────────────────────────────────────────────
    if current_equity:
        try:
            acct_info = ac.get_account_info(account_name)
            db.save_snapshot(
                account_name=account_name,
                equity=acct_info["equity"],
                cash=acct_info["cash"],
                sharpe_ratio=sharpe,
                max_drawdown=max_dd,
                win_rate=win_rate,
                total_trades=trade_count,
                profit_factor=pf if pf != float("inf") else None
            )
            print("\n  ✓ Performance snapshot saved.")
        except Exception as e:
            print(f"\n  Warning: Could not save snapshot: {e}")

    # ── Parameter adjustment ───────────────────────────────────────────────────
    current_params = db.get_all_params(strategy_name)
    changes = adjust_params(account_name, strategy_name, metrics, current_params)

    print(f"\n── Parameter Adjustments ({len(changes)} changes) ──────────────")

    if not changes:
        print("  No parameter changes — performance within acceptable bounds.")
        db.log_analysis(
            account_name=account_name,
            strategy_name=strategy_name,
            reasoning=f"Weekly analysis complete. No parameter changes. "
                      f"Sharpe={sharpe:.3f if sharpe else 'N/A'}, "
                      f"MaxDD={max_dd:.2f}%, WinRate={win_rate:.1f}%, "
                      f"Trades={trade_count}"
        )
    else:
        for change in changes:
            old = change["old_val"]
            new = change["new_val"]
            param = change["param"]
            trigger = change["trigger"]
            reason  = change["reasoning"]

            print(f"\n  {param}: {old} → {new}")
            print(f"  Trigger: {trigger}")
            print(f"  Reason:  {reason}")

            # Apply the change
            db.set_param(strategy_name, param, new, updated_by="self_analyze")

            # Log it
            db.log_analysis(
                account_name=account_name,
                strategy_name=strategy_name,
                param_changed=param,
                old_value=old,
                new_value=new,
                metric_trigger=trigger,
                reasoning=reason
            )

        print(f"\n  ✓ {len(changes)} parameter(s) updated and logged.")

    print(f"\n── Analysis complete ──────────────────────────────")


def main():
    parser = argparse.ArgumentParser(description="Analyze performance and update strategy params")
    parser.add_argument("--account",  default="paper",               help="Account name")
    parser.add_argument("--strategy", default="rsi_mean_reversion",  help="Strategy name")
    parser.add_argument("--days",     default=30, type=int,           help="Analysis window in days")
    args = parser.parse_args()

    init_db()
    run_analysis(
        account_name=args.account,
        strategy_name=args.strategy,
        days=args.days
    )


if __name__ == "__main__":
    main()
