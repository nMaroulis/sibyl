"""Virtual order sizing shared by paper and historical runs, with a backtest ledger."""

from dataclasses import dataclass

import pandas as pd

from sibyl.models import BacktestLimits


def buy_size(cash: float, price: float, fee: float, cap: float | None) -> tuple[float, float, bool]:
    """Return the quantity, fee-inclusive debit and whether the gross cap limited the order."""
    affordable = cash / (price * (1 + fee))
    quantity = min(affordable, cap / price) if cap is not None else affordable
    capped = quantity < affordable
    debit = price * quantity * (1 + fee) if capped else cash
    return quantity, debit, capped


def sell_size(holding: float, price: float, cap: float | None) -> float:
    """Size a single sale up to the gross quote cap and currently owned quantity."""
    return min(holding, cap / price) if cap is not None else holding


def loss_floor(capital: float, limits: BacktestLimits) -> float:
    """Use the configured loss from the original allocation."""
    return capital * (1 - limits.max_loss_pct / 100)


@dataclass
class Position:
    """One entry and any number of subsequent partial exits."""

    entry: dict
    quantity: float
    entry_debit: float
    gross_proceeds: float = 0.0
    exit_fees: float = 0.0
    exit_count: int = 0

    @property
    def initial_basis(self) -> float:
        return self.entry["price"] * self.entry["quantity"] + self.entry["fee"]

    @property
    def remaining_basis(self) -> float:
        return self.initial_basis * self.quantity / self.entry["quantity"]

    @property
    def realized_pnl(self) -> float:
        return self.gross_proceeds - self.exit_fees - (self.initial_basis - self.remaining_basis)

    def completed_trade(self, last_exit: dict, identity: int) -> dict:
        """Record one round trip with a volume-weighted exit price."""
        entry = self.entry
        return {
            "id": identity,
            "entry_time": entry["timestamp"],
            "exit_time": last_exit["timestamp"],
            "entry_price": entry["price"],
            "exit_price": last_exit["price"]
            if self.exit_count == 1
            else self.gross_proceeds / entry["quantity"],
            "quantity": entry["quantity"],
            "entry_fee": entry["fee"],
            "exit_fee": self.exit_fees,
            "pnl": self.realized_pnl,
            "return_pct": self.realized_pnl / self.initial_basis * 100,
            "reason": last_exit["reason"],
            "holding_seconds": (
                pd.Timestamp(last_exit["timestamp"]) - pd.Timestamp(entry["timestamp"])
            ).total_seconds(),
        }

    def marked(self, price: float) -> dict:
        """Value the unsold units at the supplied close and keep their cost basis."""
        value = self.quantity * price
        return {
            "quantity": self.quantity,
            "price": price,
            "market_value": value,
            "cost_basis": self.remaining_basis,
            "unrealized_pnl": value - self.remaining_basis,
        }


class BacktestLedger:
    """Book simulated fills and keep partial exits attached to the original entry."""

    def __init__(self, capital: float, fee: float, limits: BacktestLimits | None):
        self.cash = capital
        self.fee = fee
        self.cap = limits.max_order_quote if limits else None
        self.position: Position | None = None
        self.fills: list[dict] = []
        self.round_trips: list[dict] = []
        self.trade_returns: list[float] = []
        self.capped_orders = 0
        self.partial_exits = 0

    @property
    def quantity(self) -> float:
        return self.position.quantity if self.position else 0.0

    def equity(self, price: float) -> float:
        return self.cash + self.quantity * price

    def buy(self, timestamp: str, price: float) -> None:
        """Size the entry using quote cash, the gross order cap and separate fees."""
        quantity, debit, capped = buy_size(self.cash, price, self.fee, self.cap)
        self.capped_orders += capped
        fill = {
            "timestamp": timestamp,
            "side": "buy",
            "price": price,
            "quantity": quantity,
            "fee": price * quantity * self.fee,
        }
        self.cash -= debit
        self.position = Position(fill, quantity, debit)
        self.fills.append(fill)

    def sell(self, timestamp: str, price: float, reason: str) -> None:
        """Apply one sell signal. Residual units remain owned after a capped sale."""
        position = self.position
        if position is None:
            return
        quantity = sell_size(position.quantity, price, self.cap)
        if quantity < position.quantity:
            self.capped_orders += 1
            self.partial_exits += 1
        gross = price * quantity
        fee = gross * self.fee
        fill = {
            "timestamp": timestamp,
            "side": "sell",
            "price": price,
            "quantity": quantity,
            "fee": fee,
            "reason": reason,
        }
        self.fills.append(fill)
        self.cash += gross * (1 - self.fee)
        position.quantity -= quantity
        position.gross_proceeds += gross
        position.exit_fees += fee
        position.exit_count += 1
        if not position.quantity:
            trade = position.completed_trade(fill, len(self.round_trips) + 1)
            self.round_trips.append(trade)
            self.trade_returns.append(
                trade["return_pct"] if self.cap is not None else (self.cash / position.entry_debit - 1) * 100
            )
            self.position = None
