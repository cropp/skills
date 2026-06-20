"""
Alpaca Markets client wrapper.
Manages multiple accounts (paper + live) using alpaca-py.
"""
import sys
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

# Ensure scripts dir is on path for db import
sys.path.insert(0, str(Path(__file__).parent))
import db


def _get_trading_client(account_name: str):
    """Return a TradingClient for the named account."""
    try:
        from alpaca.trading.client import TradingClient
    except ImportError:
        print("ERROR: alpaca-py not installed. Run: pip install alpaca-py")
        sys.exit(1)

    acct = db.get_account(account_name)
    if not acct:
        print(f"ERROR: Account '{account_name}' not found. Run setup.py first.")
        sys.exit(1)

    return TradingClient(
        api_key=acct["api_key"],
        secret_key=acct["api_secret"],
        paper=bool(acct["paper"])
    )


def _get_data_client(account_name: str):
    """Return a StockHistoricalDataClient for the named account."""
    try:
        from alpaca.data.historical import StockHistoricalDataClient
    except ImportError:
        print("ERROR: alpaca-py not installed. Run: pip install alpaca-py")
        sys.exit(1)

    acct = db.get_account(account_name)
    return StockHistoricalDataClient(
        api_key=acct["api_key"],
        secret_key=acct["api_secret"]
    )


# ── Account Info ───────────────────────────────────────────────────────────────

def get_account_info(account_name: str) -> dict:
    client = _get_trading_client(account_name)
    acct = client.get_account()
    return {
        "equity":          float(acct.equity),
        "cash":            float(acct.cash),
        "buying_power":    float(acct.buying_power),
        "portfolio_value": float(acct.portfolio_value),
        "pnl_today":       float(acct.equity) - float(acct.last_equity),
        "pnl_today_pct":   ((float(acct.equity) - float(acct.last_equity)) / float(acct.last_equity) * 100)
                           if float(acct.last_equity) > 0 else 0,
        "day_trade_count": acct.daytrade_count,
        "account_number":  acct.account_number,
        "status":          acct.status.value if hasattr(acct.status, 'value') else str(acct.status),
        "paper":           bool(db.get_account(account_name)["paper"]),
    }


# ── Positions ──────────────────────────────────────────────────────────────────

def get_positions(account_name: str) -> list[dict]:
    client = _get_trading_client(account_name)
    positions = client.get_all_positions()
    result = []
    for p in positions:
        result.append({
            "symbol":       p.symbol,
            "qty":          float(p.qty),
            "side":         p.side.value if hasattr(p.side, 'value') else str(p.side),
            "avg_entry":    float(p.avg_entry_price),
            "current_price":float(p.current_price) if p.current_price else None,
            "market_value": float(p.market_value) if p.market_value else None,
            "cost_basis":   float(p.cost_basis) if p.cost_basis else None,
            "unrealized_pl":float(p.unrealized_pl) if p.unrealized_pl else None,
            "unrealized_plpc": float(p.unrealized_plpc) * 100 if p.unrealized_plpc else None,
            "change_today": float(p.change_today) * 100 if p.change_today else None,
        })
    return result


# ── Orders ─────────────────────────────────────────────────────────────────────

def place_market_order(account_name: str, symbol: str, qty: float,
                       side: str, strategy: str = None) -> dict:
    """Place a market order. side: 'buy' or 'sell'"""
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce

    client = _get_trading_client(account_name)
    order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL

    req = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=order_side,
        time_in_force=TimeInForce.DAY,
    )
    order = client.submit_order(req)
    order_id = str(order.id)

    # Log to DB
    db.log_trade(
        account_name=account_name,
        symbol=symbol,
        side=side.lower(),
        qty=qty,
        strategy=strategy,
        order_id=order_id,
        notes=f"Market order submitted"
    )

    return {
        "order_id":  order_id,
        "symbol":    symbol,
        "side":      side,
        "qty":       qty,
        "status":    str(order.status),
    }


def place_bracket_order(account_name: str, symbol: str, qty: float,
                        side: str, take_profit_pct: float, stop_loss_pct: float,
                        strategy: str = None) -> dict:
    """Place a bracket order with take profit and stop loss."""
    from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest
    from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass

    client = _get_trading_client(account_name)

    # Get current price to calculate TP/SL
    positions = {p["symbol"]: p for p in get_positions(account_name)}
    if symbol in positions:
        current_price = positions[symbol]["current_price"]
    else:
        # Use last trade price
        bars = get_latest_bars(account_name, [symbol])
        current_price = bars[symbol]["close"] if symbol in bars else None

    if not current_price:
        raise ValueError(f"Cannot get current price for {symbol}")

    if side.lower() == "buy":
        tp_price = round(current_price * (1 + take_profit_pct / 100), 2)
        sl_price = round(current_price * (1 - stop_loss_pct / 100), 2)
    else:
        tp_price = round(current_price * (1 - take_profit_pct / 100), 2)
        sl_price = round(current_price * (1 + stop_loss_pct / 100), 2)

    order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL

    req = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=order_side,
        time_in_force=TimeInForce.DAY,
        order_class=OrderClass.BRACKET,
        take_profit=TakeProfitRequest(limit_price=tp_price),
        stop_loss=StopLossRequest(stop_price=sl_price),
    )
    order = client.submit_order(req)
    order_id = str(order.id)

    db.log_trade(
        account_name=account_name,
        symbol=symbol,
        side=side.lower(),
        qty=qty,
        price=current_price,
        strategy=strategy,
        order_id=order_id,
        notes=f"Bracket order: TP={tp_price} SL={sl_price}"
    )

    return {
        "order_id":     order_id,
        "symbol":       symbol,
        "side":         side,
        "qty":          qty,
        "take_profit":  tp_price,
        "stop_loss":    sl_price,
        "status":       str(order.status),
    }


def get_open_orders(account_name: str) -> list[dict]:
    from alpaca.trading.requests import GetOrdersRequest
    from alpaca.trading.enums import QueryOrderStatus

    client = _get_trading_client(account_name)
    orders = client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN))
    return [{"order_id": str(o.id), "symbol": o.symbol, "side": str(o.side),
             "qty": float(o.qty or 0), "status": str(o.status)} for o in orders]


def cancel_all_orders(account_name: str) -> int:
    client = _get_trading_client(account_name)
    cancelled = client.cancel_orders()
    return len(cancelled) if cancelled else 0


# ── Market Data ────────────────────────────────────────────────────────────────

def get_bars(account_name: str, symbols: list[str],
             days: int = 30, timeframe: str = "1Day") -> dict:
    """Get OHLCV bars for a list of symbols."""
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    acct = db.get_account(account_name)
    client = StockHistoricalDataClient(
        api_key=acct["api_key"],
        secret_key=acct["api_secret"]
    )

    tf_map = {
        "1Min":  TimeFrame.Minute,
        "5Min":  TimeFrame(5, "Min"),
        "15Min": TimeFrame(15, "Min"),
        "1Hour": TimeFrame.Hour,
        "1Day":  TimeFrame.Day,
    }
    tf = tf_map.get(timeframe, TimeFrame.Day)

    req = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=tf,
        start=datetime.utcnow() - timedelta(days=days),
        end=datetime.utcnow(),
    )
    bars_df = client.get_stock_bars(req).df

    result = {}
    for symbol in symbols:
        try:
            if hasattr(bars_df.index, 'levels'):
                sym_bars = bars_df.xs(symbol, level=0)
            else:
                sym_bars = bars_df[bars_df.index.get_level_values(0) == symbol]

            result[symbol] = sym_bars[["open","high","low","close","volume"]].reset_index().to_dict("records")
        except (KeyError, Exception):
            result[symbol] = []

    return result


def get_latest_bars(account_name: str, symbols: list[str]) -> dict:
    """Get the latest bar snapshot for each symbol."""
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockLatestBarRequest

    acct = db.get_account(account_name)
    client = StockHistoricalDataClient(
        api_key=acct["api_key"],
        secret_key=acct["api_secret"]
    )
    req = StockLatestBarRequest(symbol_or_symbols=symbols)
    bars = client.get_stock_latest_bar(req)
    return {
        sym: {
            "open":   float(bar.open),
            "high":   float(bar.high),
            "low":    float(bar.low),
            "close":  float(bar.close),
            "volume": float(bar.volume),
            "time":   str(bar.timestamp),
        }
        for sym, bar in bars.items()
    }


# ── Portfolio History ──────────────────────────────────────────────────────────

def get_portfolio_history(account_name: str, days: int = 30) -> dict:
    """Get equity curve and daily P&L."""
    client = _get_trading_client(account_name)

    # period: 1D, 1W, 1M, 3M, 6M, 1A
    period_map = {7: "1W", 30: "1M", 90: "3M", 180: "6M", 365: "1A"}
    period = min(period_map.items(), key=lambda x: abs(x[0] - days))[1]

    history = client.get_portfolio_history(period=period, timeframe="1D")

    timestamps = history.timestamp or []
    equity     = history.equity or []
    profit_loss = history.profit_loss or []
    pl_pct     = history.profit_loss_pct or []

    return {
        "timestamps":      [datetime.fromtimestamp(t).strftime("%Y-%m-%d") for t in timestamps],
        "equity":          [float(e) if e is not None else None for e in equity],
        "profit_loss":     [float(p) if p is not None else None for p in profit_loss],
        "profit_loss_pct": [float(p) if p is not None else None for p in pl_pct],
        "base_value":      float(history.base_value) if history.base_value else None,
    }


if __name__ == "__main__":
    import json
    accounts = db.get_accounts()
    if not accounts:
        print("No accounts configured. Run setup.py first.")
    else:
        for acct in accounts:
            print(f"\n── {acct['name']} ({'PAPER' if acct['paper'] else 'LIVE'}) ──")
            info = get_account_info(acct["name"])
            print(json.dumps(info, indent=2))
