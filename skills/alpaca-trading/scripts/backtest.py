#!/usr/bin/env python3
"""
Backtester — runs a strategy against Alpaca historical data.
Usage:
  python3 backtest.py --strategy rsi_mean_reversion --symbols AAPL,MSFT,SPY --days 90
"""
import sys
import argparse
import math
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

import db
from db import init_db
import alpaca_client as ac
from strategies import get_strategy


def backtest(account_name: str, strategy_name: str, symbols: list[str], days: int = 90):
    print(f"\n{'═'*60}")
    print(f"  Backtest: {strategy_name}")
    print(f"  Symbols: {', '.join(symbols)}")
    print(f"  Window:  {days} days  |  Account: {account_name}")
    print(f"{'═'*60}\n")

    params  = db.get_all_params(strategy_name)
    strategy = get_strategy(strategy_name, params)

    all_trades  = []
    equity      = 100_000.0  # Simulated starting equity
    cash        = equity
    positions   = {}  # symbol → {qty, entry_price, entry_bar}

    max_pos_pct = float(params.get("max_position_pct", 5.0))
    max_pos     = int(params.get("max_positions", 8))

    # Fetch bars for all symbols
    print("Fetching historical data...")
    bars_data = ac.get_bars(account_name, symbols, days=days, timeframe="1Day")

    for symbol in symbols:
        bars = bars_data.get(symbol, [])
        if len(bars) < 20:
            print(f"  {symbol}: Skipping — insufficient data ({len(bars)} bars)")
            continue
        print(f"  {symbol}: {len(bars)} bars loaded")

    print("\nSimulating strategy...\n")

    # Find the minimum bar count across symbols
    min_bars = min(len(bars_data.get(s, [])) for s in symbols if bars_data.get(s))
    if min_bars == 0:
        print("ERROR: No bar data available.")
        return

    # Align and iterate bar by bar
    for bar_idx in range(20, min_bars):
        for symbol in symbols:
            bars = bars_data.get(symbol, [])
            if bar_idx >= len(bars):
                continue

            current_bar   = bars[bar_idx]
            current_price = current_bar["close"]
            history       = bars[:bar_idx + 1]

            # Check exit if we have a position
            if symbol in positions:
                pos = positions[symbol]
                should_exit, reason = strategy.should_exit(
                    {"avg_entry": pos["entry_price"], "qty": pos["qty"]},
                    current_price
                )
                if should_exit:
                    pnl = (current_price - pos["entry_price"]) * pos["qty"]
                    proceeds = current_price * pos["qty"]
                    cash += proceeds
                    equity = cash + sum(
                        bars_data[s][bar_idx]["close"] * positions[s]["qty"]
                        for s in positions if s != symbol and bar_idx < len(bars_data.get(s, []))
                    )
                    all_trades.append({
                        "symbol": symbol, "side": "sell", "qty": pos["qty"],
                        "price": current_price, "bar": bar_idx, "pnl": pnl,
                        "reason": reason,
                        "date": str(current_bar.get("timestamp", bar_idx))[:10],
                    })
                    del positions[symbol]

            # Check entry if no position and below max
            elif len(positions) < max_pos:
                signal = strategy.signals(symbol, history)
                if signal.action == "buy":
                    qty = strategy.position_size(equity, current_price)
                    cost = qty * current_price
                    if cost <= cash and cost > 0:
                        cash -= cost
                        positions[symbol] = {
                            "qty":         qty,
                            "entry_price": current_price,
                            "entry_bar":   bar_idx,
                        }
                        all_trades.append({
                            "symbol": symbol, "side": "buy", "qty": qty,
                            "price": current_price, "bar": bar_idx, "pnl": None,
                            "reason": signal.reason,
                            "date": str(current_bar.get("timestamp", bar_idx))[:10],
                        })

    # Close any remaining positions at last bar
    for symbol, pos in positions.items():
        bars = bars_data.get(symbol, [])
        if bars:
            last_price = bars[-1]["close"]
            pnl = (last_price - pos["entry_price"]) * pos["qty"]
            cash += last_price * pos["qty"]
            all_trades.append({
                "symbol": symbol, "side": "sell", "qty": pos["qty"],
                "price": last_price, "bar": min_bars, "pnl": pnl,
                "reason": "End of backtest",
                "date": str(bars[-1].get("timestamp", ""))[:10],
            })

    # ── Results ────────────────────────────────────────────────────────────────
    final_equity = cash
    total_return = (final_equity - 100_000) / 100_000 * 100

    closed_trades = [t for t in all_trades if t["side"] == "sell"]
    wins          = [t for t in closed_trades if (t["pnl"] or 0) > 0]
    losses        = [t for t in closed_trades if (t["pnl"] or 0) < 0]
    win_rate      = len(wins) / len(closed_trades) * 100 if closed_trades else 0
    total_wins    = sum(t["pnl"] for t in wins)
    total_losses  = abs(sum(t["pnl"] for t in losses))
    profit_factor = total_wins / total_losses if total_losses > 0 else float("inf")
    avg_win       = total_wins / len(wins) if wins else 0
    avg_loss      = total_losses / len(losses) if losses else 0

    print(f"{'─'*60}")
    print(f"  BACKTEST RESULTS")
    print(f"{'─'*60}")
    print(f"  Starting Equity:  $100,000.00")
    print(f"  Final Equity:     ${final_equity:>12,.2f}")
    print(f"  Total Return:     {total_return:>+.2f}%")
    print(f"  Total Trades:     {len(closed_trades)}")
    print(f"  Win Rate:         {win_rate:.1f}%  ({len(wins)}W / {len(losses)}L)")
    print(f"  Profit Factor:    {profit_factor:.2f}" if profit_factor != float("inf") else f"  Profit Factor:    ∞")
    print(f"  Avg Win:          ${avg_win:,.2f}")
    print(f"  Avg Loss:         -${avg_loss:,.2f}")
    print(f"  Reward/Risk:      {avg_win/avg_loss:.2f}:1" if avg_loss > 0 else "  Reward/Risk:      ∞")
    print(f"{'─'*60}")

    if closed_trades:
        print(f"\n  Last 10 trades:")
        print(f"  {'Date':10s} {'Symbol':6s} {'Side':4s} {'Qty':>5s} {'Price':>8s} {'P&L':>10s}  Reason")
        for t in closed_trades[-10:]:
            pnl_str = f"${t['pnl']:>+,.2f}" if t["pnl"] is not None else "—"
            pnl_col = "\033[32m" if (t.get("pnl") or 0) >= 0 else "\033[31m"
            reset   = "\033[0m"
            print(f"  {t['date']:10s} {t['symbol']:6s} {t['side']:4s} {t['qty']:>5.0f} ${t['price']:>7.2f} {pnl_col}{pnl_str:>10s}{reset}  {t['reason'][:40]}")

    # Save results to analysis log
    db.log_analysis(
        account_name=account_name,
        strategy_name=strategy_name,
        reasoning=f"Backtest ({days}d, {','.join(symbols)}): "
                  f"Return={total_return:+.2f}%, WinRate={win_rate:.1f}%, "
                  f"PF={profit_factor:.2f}, Trades={len(closed_trades)}"
    )

    print(f"\n  ✓ Results saved to analysis log.")
    return {
        "total_return":   total_return,
        "win_rate":       win_rate,
        "profit_factor":  profit_factor,
        "total_trades":   len(closed_trades),
        "final_equity":   final_equity,
    }


def main():
    parser = argparse.ArgumentParser(description="Backtest a trading strategy")
    parser.add_argument("--strategy", default="rsi_mean_reversion")
    parser.add_argument("--account",  default="paper")
    parser.add_argument("--symbols",  default="AAPL,MSFT,SPY,QQQ")
    parser.add_argument("--days",     default=90, type=int)
    args = parser.parse_args()

    init_db()
    backtest(
        account_name=args.account,
        strategy_name=args.strategy,
        symbols=[s.strip() for s in args.symbols.split(",")],
        days=args.days
    )


if __name__ == "__main__":
    main()
