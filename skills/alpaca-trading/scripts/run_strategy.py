#!/usr/bin/env python3
"""
Strategy runner — execute the active strategy against a configured account.
Designed to run as a scheduled task every market day at 9:35am ET.

Usage:
  python3 run_strategy.py [--strategy rsi_mean_reversion] [--account paper] [--dry-run]
"""
import sys
import argparse
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

import db
from db import init_db
import alpaca_client as ac
from strategies import get_strategy
from market_filters import pre_entry_check


def is_market_open(account_name: str) -> bool:
    """Check if the market is currently open."""
    try:
        from alpaca.trading.client import TradingClient
        acct = db.get_account(account_name)
        client = TradingClient(api_key=acct["api_key"], secret_key=acct["api_secret"],
                               paper=bool(acct["paper"]))
        clock = client.get_clock()
        return clock.is_open
    except Exception as e:
        print(f"Warning: Could not check market clock: {e}")
        return True  # assume open if check fails


def run_strategy(account_name: str, strategy_name: str, dry_run: bool = False):
    print(f"\n{'═'*55}")
    print(f"  Strategy Runner: {strategy_name}")
    print(f"  Account: {account_name} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"{'═'*55}\n")

    # Check account exists
    acct = db.get_account(account_name)
    if not acct:
        print(f"ERROR: Account '{account_name}' not found. Run setup.py first.")
        sys.exit(1)

    # Check market hours
    if not is_market_open(account_name):
        print("Market is closed. Skipping strategy run.")
        db.log_analysis(account_name, strategy_name,
                        reasoning="Scheduled run skipped — market closed.")
        return

    # Load strategy with current params
    params = db.get_all_params(strategy_name)
    if not params:
        print(f"ERROR: No params found for '{strategy_name}'. Run setup.py first.")
        sys.exit(1)

    strategy = get_strategy(strategy_name, params)

    # Get account state
    print("Fetching account info...")
    account_info = ac.get_account_info(account_name)
    equity       = account_info["equity"]
    print(f"  Equity:        ${equity:,.2f}")
    print(f"  Buying Power:  ${account_info['buying_power']:,.2f}")
    print(f"  Today P&L:     ${account_info['pnl_today']:+,.2f} ({account_info['pnl_today_pct']:+.2f}%)")

    # Get current positions
    positions = ac.get_positions(account_name)
    position_map = {p["symbol"]: p for p in positions}
    print(f"\nOpen positions: {len(positions)}/{params.get('max_positions', 8)}")

    # ── EXIT CHECK: evaluate existing positions ────────────────────────────────
    print("\n── Checking exit conditions ──")
    if positions:
        symbols_held = list(position_map.keys())
        latest_bars  = ac.get_latest_bars(account_name, symbols_held)

        for symbol, position in position_map.items():
            current_price = latest_bars.get(symbol, {}).get("close") or position.get("current_price")
            if not current_price:
                continue

            should_exit, reason = strategy.should_exit(position, current_price)
            print(f"  {symbol}: {reason}")

            if should_exit:
                print(f"  → SELLING {symbol} ({reason})")
                if not dry_run:
                    result = ac.place_market_order(
                        account_name=account_name,
                        symbol=symbol,
                        qty=abs(position["qty"]),
                        side="sell",
                        strategy=strategy_name
                    )
                    # Calculate P&L
                    pnl = (current_price - position["avg_entry"]) * position["qty"]
                    db.log_trade(account_name, symbol, "sell", abs(position["qty"]),
                                 price=current_price, strategy=strategy_name,
                                 order_id=result.get("order_id"), pnl=pnl,
                                 notes=reason)
                    print(f"    Order placed: {result['order_id']}")
                else:
                    print(f"    [DRY RUN] Would sell {position['qty']} shares @ ${current_price:.2f}")
    else:
        print("  No open positions.")

    # ── ENTRY CHECK: scan watchlist for signals ────────────────────────────────
    max_positions = int(params.get("max_positions", 8))
    current_count = len(position_map)

    if current_count >= max_positions:
        print(f"\n── Entry scan skipped: at max positions ({max_positions}) ──")
        return

    watchlist = [s.strip() for s in params.get("watchlist", "SPY,QQQ,AAPL,MSFT").split(",")]
    # Skip symbols already held
    candidates = [s for s in watchlist if s not in position_map]

    print(f"\n── Scanning {len(candidates)} symbols for entry signals ──")

    buy_signals = []
    for symbol in candidates:
        try:
            bars_data = ac.get_bars(account_name, [symbol], days=60, timeframe="1Day")
            bars = bars_data.get(symbol, [])
            if not bars:
                print(f"  {symbol}: No bar data")
                continue

            signal = strategy.signals(symbol, bars)
            status = f"RSI signal={signal.action} strength={signal.strength:.2f}"
            print(f"  {symbol}: {signal.reason}")

            if signal.action == "buy" and signal.strength > 0:
                buy_signals.append(signal)
        except Exception as e:
            print(f"  {symbol}: Error — {e}")

    # ── Pre-entry filter: earnings + news sentiment ────────────────────────────
    if buy_signals:
        print(f"\n── Running pre-entry filters (earnings + news) ──")
        filtered_signals = []
        for signal in buy_signals:
            ok, reason, _ = pre_entry_check(account_name, signal.symbol)
            status = "✓" if ok else "✗"
            print(f"  {status} {signal.symbol}: {reason}")
            if ok:
                filtered_signals.append(signal)
        buy_signals = filtered_signals

    # Sort by signal strength
    buy_signals.sort(key=lambda s: s.strength, reverse=True)

    # ── Place buy orders ───────────────────────────────────────────────────────
    slots_available = max_positions - current_count
    orders_placed   = 0

    print(f"\n── Entry orders ({len(buy_signals)} signals, {slots_available} slots) ──")

    for signal in buy_signals[:slots_available]:
        symbol = signal.symbol
        price  = signal.price or 0

        if price <= 0:
            print(f"  {symbol}: Cannot determine price, skipping")
            continue

        qty = strategy.position_size(equity, price)
        cost = qty * price
        print(f"  {symbol}: BUY {qty} shares @ ~${price:.2f} = ${cost:,.2f} | {signal.reason}")

        if not dry_run:
            try:
                result = ac.place_bracket_order(
                    account_name=account_name,
                    symbol=symbol,
                    qty=qty,
                    side="buy",
                    take_profit_pct=strategy.take_profit_pct,
                    stop_loss_pct=strategy.stop_loss_pct,
                    strategy=strategy_name
                )
                print(f"    Order placed: {result['order_id']} | TP=${result['take_profit']} SL=${result['stop_loss']}")
                orders_placed += 1
            except Exception as e:
                print(f"    ERROR placing order: {e}")
        else:
            print(f"    [DRY RUN] Would place bracket order (TP=+{strategy.take_profit_pct}% SL=-{strategy.stop_loss_pct}%)")
            orders_placed += 1

    if not buy_signals:
        print("  No buy signals found this run.")

    # ── Summary ────────────────────────────────────────────────────────────────
    print(f"\n── Run complete ──")
    print(f"  Orders placed: {orders_placed}")
    print(f"  Positions: {current_count} → {current_count + orders_placed} / {max_positions}")

    db.log_analysis(
        account_name=account_name,
        strategy_name=strategy_name,
        reasoning=f"Strategy run complete. {orders_placed} orders placed. "
                  f"Equity: ${equity:,.2f}. Positions: {current_count + orders_placed}/{max_positions}."
    )

    # Save daily snapshot
    db.save_snapshot(account_name=account_name, equity=equity,
                     cash=account_info["cash"])


def main():
    parser = argparse.ArgumentParser(description="Run the active trading strategy")
    parser.add_argument("--strategy", default="rsi_mean_reversion",
                        help="Strategy name (default: rsi_mean_reversion)")
    parser.add_argument("--account", default="paper",
                        help="Account name (default: paper)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulate without placing real orders")
    args = parser.parse_args()

    init_db()
    run_strategy(
        account_name=args.account,
        strategy_name=args.strategy,
        dry_run=args.dry_run
    )


if __name__ == "__main__":
    main()
