"""
Abstract base class for all trading strategies.
Every strategy must implement: signals(), should_exit(), position_size()
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class Signal:
    symbol:    str
    action:    str          # 'buy', 'sell', 'hold'
    strength:  float        # 0.0–1.0 (1.0 = strongest conviction)
    reason:    str
    price:     Optional[float] = None


class BaseStrategy(ABC):
    name: str = "base"

    def __init__(self, params: dict):
        self.params = params

    @abstractmethod
    def signals(self, symbol: str, bars: list[dict]) -> Signal:
        """
        Given a list of OHLCV bar dicts (oldest first), return a Signal.
        bars: [{"open":..., "high":..., "low":..., "close":..., "volume":...}, ...]
        """
        ...

    @abstractmethod
    def should_exit(self, position: dict, current_price: float) -> tuple[bool, str]:
        """
        Given an open position dict and the current price,
        return (should_exit, reason).
        """
        ...

    def position_size(self, equity: float, price: float) -> float:
        """
        Calculate number of shares to buy given portfolio equity and entry price.
        Default: max_position_pct% of equity, rounded down to whole shares.
        """
        max_pct = float(self.params.get("max_position_pct", 5.0))
        dollars = equity * (max_pct / 100)
        shares  = dollars / price if price > 0 else 0
        return max(1, int(shares))  # at least 1 share

    @staticmethod
    def compute_rsi(closes: list[float], period: int = 14) -> Optional[float]:
        """Calculate RSI for the most recent bar."""
        if len(closes) < period + 1:
            return None

        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        gains  = [max(d, 0) for d in deltas]
        losses = [abs(min(d, 0)) for d in deltas]

        # Initial averages
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        # Wilder's smoothing
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            return 100.0
        rs  = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return round(rsi, 2)

    @staticmethod
    def compute_sma(closes: list[float], period: int) -> Optional[float]:
        if len(closes) < period:
            return None
        return sum(closes[-period:]) / period

    @staticmethod
    def compute_ema(closes: list[float], period: int) -> Optional[float]:
        if len(closes) < period:
            return None
        k = 2 / (period + 1)
        ema = sum(closes[:period]) / period
        for price in closes[period:]:
            ema = price * k + ema * (1 - k)
        return round(ema, 4)
