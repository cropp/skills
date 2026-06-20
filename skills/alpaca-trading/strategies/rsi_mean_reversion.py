"""
RSI Mean Reversion Strategy
──────────────────────────
Entry:  RSI(14) crosses below oversold threshold (default 30) → BUY
Exit:   RSI crosses above overbought threshold (default 70) OR
        stop loss hit (default 2%) OR take profit hit (default 4%)

2:1 risk/reward ratio built in.
"""
from .base import BaseStrategy, Signal


class RSIMeanReversionStrategy(BaseStrategy):
    name = "rsi_mean_reversion"

    @property
    def rsi_period(self)  -> int:   return int(self.params.get("rsi_period", 14))
    @property
    def oversold(self)    -> float: return float(self.params.get("rsi_oversold", 30))
    @property
    def overbought(self)  -> float: return float(self.params.get("rsi_overbought", 70))
    @property
    def stop_loss_pct(self) -> float: return float(self.params.get("stop_loss_pct", 2.0))
    @property
    def take_profit_pct(self) -> float: return float(self.params.get("take_profit_pct", 4.0))

    def signals(self, symbol: str, bars: list[dict]) -> Signal:
        if len(bars) < self.rsi_period + 2:
            return Signal(symbol=symbol, action="hold", strength=0,
                         reason=f"Not enough bars ({len(bars)} < {self.rsi_period + 2})")

        closes = [b["close"] for b in bars]

        # Current and previous RSI to detect crossover
        rsi_now  = self.compute_rsi(closes,       self.rsi_period)
        rsi_prev = self.compute_rsi(closes[:-1],  self.rsi_period)

        if rsi_now is None or rsi_prev is None:
            return Signal(symbol=symbol, action="hold", strength=0,
                         reason="RSI could not be computed")

        current_price = closes[-1]

        # BUY: RSI crossed below oversold
        if rsi_prev >= self.oversold and rsi_now < self.oversold:
            strength = (self.oversold - rsi_now) / self.oversold
            return Signal(
                symbol=symbol, action="buy",
                strength=round(min(strength, 1.0), 3),
                reason=f"RSI crossed below {self.oversold} ({rsi_prev:.1f} → {rsi_now:.1f})",
                price=current_price
            )

        # SELL signal: RSI crossed above overbought
        if rsi_prev <= self.overbought and rsi_now > self.overbought:
            strength = (rsi_now - self.overbought) / (100 - self.overbought)
            return Signal(
                symbol=symbol, action="sell",
                strength=round(min(strength, 1.0), 3),
                reason=f"RSI crossed above {self.overbought} ({rsi_prev:.1f} → {rsi_now:.1f})",
                price=current_price
            )

        return Signal(
            symbol=symbol, action="hold", strength=0,
            reason=f"RSI={rsi_now:.1f} (no crossover)",
            price=current_price
        )

    def should_exit(self, position: dict, current_price: float) -> tuple[bool, str]:
        """
        Check stop loss and take profit for an open position.
        position: dict with avg_entry, unrealized_plpc, symbol
        """
        entry = float(position.get("avg_entry", 0))
        if entry <= 0:
            return False, "No entry price"

        pl_pct = ((current_price - entry) / entry) * 100

        if pl_pct <= -self.stop_loss_pct:
            return True, f"Stop loss hit: {pl_pct:.2f}% (threshold: -{self.stop_loss_pct}%)"

        if pl_pct >= self.take_profit_pct:
            return True, f"Take profit hit: {pl_pct:.2f}% (threshold: +{self.take_profit_pct}%)"

        return False, f"Holding: P&L={pl_pct:.2f}%"
