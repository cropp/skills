#!/usr/bin/env python3
"""
Interactive setup wizard for the Alpaca Trading Skill.
Configures paper and/or live accounts.
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db
from db import init_db


def test_connection(api_key: str, api_secret: str, paper: bool) -> tuple[bool, str]:
    """Test Alpaca API credentials. Returns (success, message)."""
    try:
        from alpaca.trading.client import TradingClient
    except ImportError:
        return False, "alpaca-py not installed. Run: pip install alpaca-py"

    try:
        client = TradingClient(api_key=api_key, secret_key=api_secret, paper=paper)
        acct = client.get_account()
        equity = float(acct.equity)
        return True, f"Connected! Equity: ${equity:,.2f}"
    except Exception as e:
        return False, f"Connection failed: {e}"


def setup_account():
    print("\n" + "═" * 55)
    print("  Alpaca Trading Skill — Account Setup")
    print("═" * 55)

    # Show existing accounts
    existing = db.get_accounts(enabled_only=False)
    if existing:
        print("\nExisting accounts:")
        for a in existing:
            status = "✓ enabled" if a["enabled"] else "✗ disabled"
            kind   = "PAPER" if a["paper"] else "LIVE"
            print(f"  • {a['name']} [{kind}] {status}")
        print()

    print("Get your API credentials from:")
    print("  Paper: https://app.alpaca.markets/paper/dashboard/overview → API Keys")
    print("  Live:  https://app.alpaca.markets/brokerage/dashboard/overview → API Keys\n")

    account_type = input("Set up (p)aper or (l)ive account? [p]: ").strip().lower() or "p"
    paper = account_type != "l"
    kind  = "PAPER" if paper else "LIVE"

    default_name = "paper" if paper else "live"
    name = input(f"Account name [{default_name}]: ").strip() or default_name

    api_key    = input(f"API Key ID ({kind}): ").strip()
    api_secret = input(f"API Secret ({kind}): ").strip()

    if not api_key or not api_secret:
        print("ERROR: API key and secret are required.")
        sys.exit(1)

    print(f"\nTesting connection to {'paper' if paper else 'live'} Alpaca API...")
    ok, msg = test_connection(api_key, api_secret, paper)

    if ok:
        print(f"  ✓ {msg}")
        db.save_account(name=name, api_key=api_key, api_secret=api_secret, paper=paper)
        print(f"  ✓ Account '{name}' saved.")
    else:
        print(f"  ✗ {msg}")
        retry = input("Save anyway? (y/N): ").strip().lower()
        if retry == "y":
            db.save_account(name=name, api_key=api_key, api_secret=api_secret, paper=paper)
            print(f"  Saved '{name}' (unverified).")
        else:
            print("Aborted.")
            return

    # Initialize default strategy params if not set
    _init_default_params()

    another = input("\nAdd another account? (y/N): ").strip().lower()
    if another == "y":
        setup_account()
    else:
        print("\n✓ Setup complete. Run the dashboard with:")
        print("  python3 ~/.claude/skills/alpaca-trading/scripts/dashboard.py\n")


def _init_default_params():
    """Set default strategy parameters if not already configured."""
    defaults = {
        "rsi_period":      "14",
        "rsi_oversold":    "30",
        "rsi_overbought":  "70",
        "take_profit_pct": "4.0",
        "stop_loss_pct":   "2.0",
        "max_position_pct":"5.0",
        "max_positions":   "8",
        "watchlist":       "SPY,QQQ,AAPL,MSFT,GOOGL,AMZN,NVDA,META",
    }
    for key, val in defaults.items():
        existing = db.get_param("rsi_mean_reversion", key)
        if existing is None:
            db.set_param("rsi_mean_reversion", key, val, updated_by="setup")

    print("  ✓ Default strategy parameters initialized.")


def show_status():
    accounts = db.get_accounts(enabled_only=False)
    if not accounts:
        print("No accounts configured. Run setup.py to add one.")
        return

    print("\n── Configured Accounts ──────────────────────────────")
    for a in accounts:
        kind   = "PAPER" if a["paper"] else "LIVE"
        status = "enabled" if a["enabled"] else "disabled"
        masked = a["api_key"][:4] + "..." + a["api_key"][-4:] if len(a["api_key"]) > 8 else "****"
        print(f"  {a['name']:15s} [{kind}]  key:{masked}  {status}")

    print("\n── Strategy Parameters (rsi_mean_reversion) ─────────")
    params = db.get_all_params("rsi_mean_reversion")
    for k, v in params.items():
        print(f"  {k:20s} = {v}")


if __name__ == "__main__":
    init_db()
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        show_status()
    else:
        setup_account()
