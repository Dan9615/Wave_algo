"""Conservative backtest execution for generated Wave strategy signals."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from wave_algo.data import validate_ohlcv_schema
from wave_algo.models import Direction, SignalTarget, TradeSignal, normalize_direction

MarketKey = tuple[str, str]
DEFAULT_TIME_STOPS = {
    "wave_3": 72,
    "wave_5": 72,
    "triangle_breakout": 48,
}
PARTIAL_EXIT_SETUPS = {"wave_3", "wave_5"}
EPSILON = 1e-9


@dataclass(frozen=True)
class BacktestConfig:
    """Execution, cost, sizing, and portfolio constraints for backtests."""

    initial_equity: float = 100_000.0
    risk_fraction: float = 0.01
    fee_rate: float = 0.0006
    slippage_rate: float = 0.0002
    max_positions: int = 3
    time_stops: Mapping[str, int] = field(default_factory=lambda: dict(DEFAULT_TIME_STOPS))

    def __post_init__(self) -> None:
        if self.initial_equity <= 0:
            raise ValueError("initial_equity must be positive")
        if not 0 < self.risk_fraction <= 1:
            raise ValueError("risk_fraction must be in the 0..1 interval")
        if self.fee_rate < 0:
            raise ValueError("fee_rate cannot be negative")
        if self.slippage_rate < 0:
            raise ValueError("slippage_rate cannot be negative")
        if self.max_positions <= 0:
            raise ValueError("max_positions must be positive")
        if any(bars <= 0 for bars in self.time_stops.values()):
            raise ValueError("time stops must be positive bar counts")

    def time_stop_bars(self, setup_type: str) -> int:
        """Return setup-specific maximum holding period in bars."""

        return int(self.time_stops.get(setup_type, DEFAULT_TIME_STOPS.get(setup_type, 72)))


@dataclass(frozen=True)
class BacktestFill:
    """One execution fill in the conservative simulator."""

    index: int
    time: Any
    side: str
    price: float
    quantity: float
    fee: float
    reason: str
    gross_pnl: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "time": _serialize_time(self.time),
            "side": self.side,
            "price": self.price,
            "quantity": self.quantity,
            "fee": self.fee,
            "reason": self.reason,
            "gross_pnl": self.gross_pnl,
        }


@dataclass(frozen=True)
class BacktestTrade:
    """A completed trade, including partial fills when applicable."""

    symbol: str
    timeframe: str
    setup_type: str
    direction: Direction
    signal_time: Any
    entry_time: Any
    exit_time: Any
    entry_index: int
    exit_index: int
    entry_price: float
    initial_stop: float
    quantity: float
    gross_pnl: float
    fees: float
    net_pnl: float
    r_multiple: float
    return_pct: float
    exit_reason: str
    confidence: float
    fills: tuple[BacktestFill, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "setup_type": self.setup_type,
            "direction": self.direction.value,
            "signal_time": _serialize_time(self.signal_time),
            "entry_time": _serialize_time(self.entry_time),
            "exit_time": _serialize_time(self.exit_time),
            "entry_index": self.entry_index,
            "exit_index": self.exit_index,
            "entry_price": self.entry_price,
            "initial_stop": self.initial_stop,
            "quantity": self.quantity,
            "gross_pnl": self.gross_pnl,
            "fees": self.fees,
            "net_pnl": self.net_pnl,
            "r_multiple": self.r_multiple,
            "return_pct": self.return_pct,
            "exit_reason": self.exit_reason,
            "confidence": self.confidence,
            "fills": [fill.to_dict() for fill in self.fills],
        }


@dataclass(frozen=True)
class BacktestResult:
    """Portfolio-level backtest result for one confidence threshold."""

    threshold: float
    config: BacktestConfig
    trades: tuple[BacktestTrade, ...]
    skipped_signals: tuple[dict[str, Any], ...]
    equity_curve: tuple[dict[str, Any], ...]

    @property
    def final_equity(self) -> float:
        if not self.equity_curve:
            return self.config.initial_equity
        return float(self.equity_curve[-1]["equity"])

    @property
    def summary(self) -> dict[str, Any]:
        trade_count = len(self.trades)
        wins = [trade for trade in self.trades if trade.net_pnl > 0]
        net_values = [trade.net_pnl for trade in self.trades]
        r_values = [trade.r_multiple for trade in self.trades]
        max_drawdown, max_drawdown_pct = _max_drawdown(self.equity_curve)
        return {
            "threshold": self.threshold,
            "initial_equity": self.config.initial_equity,
            "final_equity": self.final_equity,
            "net_pnl": self.final_equity - self.config.initial_equity,
            "total_return_pct": (
                (self.final_equity / self.config.initial_equity - 1.0) * 100.0
            ),
            "trade_count": trade_count,
            "win_rate": len(wins) / trade_count if trade_count else 0.0,
            "expectancy": sum(net_values) / trade_count if trade_count else 0.0,
            "expectancy_r": sum(r_values) / trade_count if trade_count else 0.0,
            "max_drawdown": max_drawdown,
            "max_drawdown_pct": max_drawdown_pct,
            "skipped_signals": len(self.skipped_signals),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "trades": [trade.to_dict() for trade in self.trades],
            "skipped_signals": list(self.skipped_signals),
            "equity_curve": list(self.equity_curve),
        }


@dataclass(frozen=True)
class _BacktestCandidate:
    signal: TradeSignal
    key: MarketKey
    df: pd.DataFrame
    signal_index: int
    entry_index: int
    entry_time: Any


@dataclass(frozen=True)
class _ActiveTrade:
    symbol: str
    exit_time: Any
    trade: BacktestTrade


def filter_signals_by_confidence(
    signals: Iterable[TradeSignal],
    threshold: float = 70.0,
) -> list[TradeSignal]:
    """Return signals that pass a confidence threshold."""

    return [signal for signal in signals if signal.confidence >= threshold]


def run_backtest(
    market_data: Mapping[MarketKey, pd.DataFrame],
    signals: Iterable[TradeSignal],
    *,
    threshold: float = 70.0,
    config: BacktestConfig | None = None,
) -> BacktestResult:
    """Run the conservative next-open backtest for one confidence threshold."""

    config = config or BacktestConfig()
    normalized_data = {
        key: validate_ohlcv_schema(frame)
        for key, frame in market_data.items()
    }
    candidates, skipped = _build_candidates(normalized_data, signals, threshold)
    equity = config.initial_equity
    active: list[_ActiveTrade] = []
    completed: list[BacktestTrade] = []
    equity_curve: list[dict[str, Any]] = [
        {"time": None, "equity": equity, "event": "initial"}
    ]

    for candidate in sorted(candidates, key=lambda item: (item.entry_time, item.key)):
        equity, active = _realize_closed_trades(
            candidate.entry_time,
            equity,
            active,
            completed,
            equity_curve,
        )

        if any(open_trade.symbol == candidate.signal.symbol for open_trade in active):
            skipped.append(_skip(candidate.signal, "symbol_position_open"))
            continue
        if len(active) >= config.max_positions:
            skipped.append(_skip(candidate.signal, "max_portfolio_positions"))
            continue

        trade, reason = _simulate_trade(candidate, equity, config)
        if trade is None:
            skipped.append(_skip(candidate.signal, reason or "unfilled"))
            continue
        active.append(_ActiveTrade(symbol=trade.symbol, exit_time=trade.exit_time, trade=trade))

    for open_trade in sorted(active, key=lambda item: item.exit_time):
        equity += open_trade.trade.net_pnl
        completed.append(open_trade.trade)
        equity_curve.append(
            {
                "time": _serialize_time(open_trade.trade.exit_time),
                "equity": equity,
                "event": "trade_exit",
                "symbol": open_trade.trade.symbol,
            }
        )

    completed.sort(key=lambda trade: (trade.entry_time, trade.symbol, trade.setup_type))
    return BacktestResult(
        threshold=float(threshold),
        config=config,
        trades=tuple(completed),
        skipped_signals=tuple(skipped),
        equity_curve=tuple(equity_curve),
    )


def run_threshold_sensitivity(
    market_data: Mapping[MarketKey, pd.DataFrame],
    signals: Iterable[TradeSignal],
    *,
    thresholds: Iterable[float] = (60.0, 70.0, 80.0),
    config: BacktestConfig | None = None,
) -> dict[float, BacktestResult]:
    """Run the same signal set through multiple confidence thresholds."""

    signal_list = list(signals)
    return {
        float(threshold): run_backtest(
            market_data,
            signal_list,
            threshold=float(threshold),
            config=config,
        )
        for threshold in thresholds
    }


def _build_candidates(
    market_data: Mapping[MarketKey, pd.DataFrame],
    signals: Iterable[TradeSignal],
    threshold: float,
) -> tuple[list[_BacktestCandidate], list[dict[str, Any]]]:
    candidates: list[_BacktestCandidate] = []
    skipped: list[dict[str, Any]] = []
    for signal in signals:
        if signal.confidence < threshold:
            skipped.append(_skip(signal, "below_confidence_threshold"))
            continue
        key = (signal.symbol, signal.timeframe)
        df = market_data.get(key)
        if df is None:
            skipped.append(_skip(signal, "missing_market_data"))
            continue
        signal_index = _find_signal_index(df, signal.signal_time)
        if signal_index is None:
            skipped.append(_skip(signal, "signal_time_not_found"))
            continue
        entry_index = signal_index + 1
        if entry_index >= len(df):
            skipped.append(_skip(signal, "no_next_bar_for_entry"))
            continue
        candidates.append(
            _BacktestCandidate(
                signal=signal,
                key=key,
                df=df,
                signal_index=signal_index,
                entry_index=entry_index,
                entry_time=df.iloc[entry_index]["timestamp"],
            )
        )
    return candidates, skipped


def _simulate_trade(
    candidate: _BacktestCandidate,
    equity: float,
    config: BacktestConfig,
) -> tuple[BacktestTrade | None, str | None]:
    signal = candidate.signal
    direction = normalize_direction(signal.direction)
    entry_row = candidate.df.iloc[candidate.entry_index]
    entry_price = _slipped_price(
        float(entry_row["open"]),
        direction,
        is_entry=True,
        config=config,
    )
    stop_price = float(signal.stop)
    if not _stop_is_valid(direction, entry_price, stop_price):
        return None, "invalid_stop_for_entry"

    risk_per_unit = abs(entry_price - stop_price)
    if risk_per_unit <= EPSILON:
        return None, "zero_risk_distance"

    risk_quantity = equity * config.risk_fraction / risk_per_unit
    cash_quantity = equity / entry_price
    quantity = min(risk_quantity, cash_quantity)
    if quantity <= EPSILON:
        return None, "zero_position_size"

    entry_fee = _fee(entry_price, quantity, config)
    fills: list[BacktestFill] = [
        BacktestFill(
            index=candidate.entry_index,
            time=entry_row["timestamp"],
            side=_entry_side(direction),
            price=entry_price,
            quantity=quantity,
            fee=entry_fee,
            reason="entry_next_open",
        )
    ]
    fees = entry_fee
    gross_pnl = 0.0
    remaining = quantity
    current_stop = stop_price
    breakeven_stop_active = False
    target_index = 0
    targets = _ordered_targets(signal, direction)
    time_stop_bars = config.time_stop_bars(signal.setup_type)
    last_exit_index = candidate.entry_index
    last_exit_time = entry_row["timestamp"]
    last_exit_reason = "entry_next_open"

    for row_index in range(
        candidate.entry_index,
        min(len(candidate.df), candidate.entry_index + time_stop_bars),
    ):
        row = candidate.df.iloc[row_index]
        while remaining > EPSILON:
            next_target = targets[target_index] if target_index < len(targets) else None
            stop_hit = _stop_hit(row, current_stop, direction)
            target_hit = (
                next_target is not None
                and _target_hit(row, next_target.price, direction)
            )

            if stop_hit:
                exit_reason = "breakeven_stop" if breakeven_stop_active else "stop_loss"
                fill, exit_gross = _exit_fill(
                    row_index,
                    row["timestamp"],
                    direction,
                    current_stop,
                    remaining,
                    entry_price,
                    config,
                    exit_reason,
                )
                fills.append(fill)
                fees += fill.fee
                gross_pnl += exit_gross
                last_exit_index = row_index
                last_exit_time = row["timestamp"]
                last_exit_reason = exit_reason
                remaining = 0.0
                break

            if target_hit and next_target is not None:
                target_quantity = min(quantity * next_target.size_fraction, remaining)
                fill, exit_gross = _exit_fill(
                    row_index,
                    row["timestamp"],
                    direction,
                    next_target.price,
                    target_quantity,
                    entry_price,
                    config,
                    next_target.label,
                )
                fills.append(fill)
                fees += fill.fee
                gross_pnl += exit_gross
                remaining -= target_quantity
                last_exit_index = row_index
                last_exit_time = row["timestamp"]
                last_exit_reason = next_target.label
                target_index += 1
                if (
                    signal.setup_type in PARTIAL_EXIT_SETUPS
                    and target_index == 1
                    and remaining > EPSILON
                ):
                    current_stop = entry_price
                    breakeven_stop_active = True
                continue

            break

        if remaining <= EPSILON:
            break

    if remaining > EPSILON:
        exit_index = candidate.entry_index + time_stop_bars
        if exit_index < len(candidate.df):
            row = candidate.df.iloc[exit_index]
            exit_price = float(row["open"])
            exit_reason = "time_stop"
        else:
            exit_index = len(candidate.df) - 1
            row = candidate.df.iloc[exit_index]
            exit_price = float(row["close"])
            exit_reason = "end_of_data"
        fill, exit_gross = _exit_fill(
            exit_index,
            row["timestamp"],
            direction,
            exit_price,
            remaining,
            entry_price,
            config,
            exit_reason,
            price_already_slipped=False,
        )
        fills.append(fill)
        fees += fill.fee
        gross_pnl += exit_gross
        last_exit_index = exit_index
        last_exit_time = row["timestamp"]
        last_exit_reason = exit_reason

    net_pnl = gross_pnl - fees
    initial_risk = risk_per_unit * quantity
    entry_notional = entry_price * quantity
    return (
        BacktestTrade(
            symbol=signal.symbol,
            timeframe=signal.timeframe,
            setup_type=signal.setup_type,
            direction=direction,
            signal_time=signal.signal_time,
            entry_time=entry_row["timestamp"],
            exit_time=last_exit_time,
            entry_index=candidate.entry_index,
            exit_index=last_exit_index,
            entry_price=entry_price,
            initial_stop=stop_price,
            quantity=quantity,
            gross_pnl=gross_pnl,
            fees=fees,
            net_pnl=net_pnl,
            r_multiple=net_pnl / initial_risk if initial_risk > EPSILON else 0.0,
            return_pct=net_pnl / entry_notional if entry_notional > EPSILON else 0.0,
            exit_reason=last_exit_reason,
            confidence=signal.confidence,
            fills=tuple(fills),
        ),
        None,
    )


def _realize_closed_trades(
    entry_time: Any,
    equity: float,
    active: list[_ActiveTrade],
    completed: list[BacktestTrade],
    equity_curve: list[dict[str, Any]],
) -> tuple[float, list[_ActiveTrade]]:
    still_active: list[_ActiveTrade] = []
    for open_trade in sorted(active, key=lambda item: item.exit_time):
        if open_trade.exit_time < entry_time:
            equity += open_trade.trade.net_pnl
            completed.append(open_trade.trade)
            equity_curve.append(
                {
                    "time": _serialize_time(open_trade.trade.exit_time),
                    "equity": equity,
                    "event": "trade_exit",
                    "symbol": open_trade.trade.symbol,
                }
            )
        else:
            still_active.append(open_trade)
    return equity, still_active


def _ordered_targets(signal: TradeSignal, direction: Direction) -> tuple[SignalTarget, ...]:
    reverse = direction is Direction.SHORT
    return tuple(sorted(signal.targets, key=lambda target: target.price, reverse=reverse))


def _find_signal_index(df: pd.DataFrame, signal_time: Any) -> int | None:
    try:
        normalized_time = pd.Timestamp(signal_time)
    except Exception:
        normalized_time = signal_time
    matches = df.index[df["timestamp"] == normalized_time].tolist()
    if not matches:
        return None
    return int(matches[0])


def _stop_is_valid(direction: Direction, entry_price: float, stop_price: float) -> bool:
    if direction is Direction.LONG:
        return stop_price < entry_price - EPSILON
    return stop_price > entry_price + EPSILON


def _stop_hit(row: pd.Series, stop_price: float, direction: Direction) -> bool:
    if direction is Direction.LONG:
        return float(row["low"]) <= stop_price
    return float(row["high"]) >= stop_price


def _target_hit(row: pd.Series, target_price: float, direction: Direction) -> bool:
    if direction is Direction.LONG:
        return float(row["high"]) >= target_price
    return float(row["low"]) <= target_price


def _slipped_price(
    raw_price: float,
    direction: Direction,
    *,
    is_entry: bool,
    config: BacktestConfig,
) -> float:
    if direction is Direction.LONG:
        return raw_price * (1.0 + config.slippage_rate if is_entry else 1.0 - config.slippage_rate)
    return raw_price * (1.0 - config.slippage_rate if is_entry else 1.0 + config.slippage_rate)


def _exit_fill(
    index: int,
    time: Any,
    direction: Direction,
    raw_price: float,
    quantity: float,
    entry_price: float,
    config: BacktestConfig,
    reason: str,
    *,
    price_already_slipped: bool = False,
) -> tuple[BacktestFill, float]:
    exit_price = (
        raw_price
        if price_already_slipped
        else _slipped_price(raw_price, direction, is_entry=False, config=config)
    )
    gross_pnl = _gross_pnl(direction, entry_price, exit_price, quantity)
    return (
        BacktestFill(
            index=index,
            time=time,
            side=_exit_side(direction),
            price=exit_price,
            quantity=quantity,
            fee=_fee(exit_price, quantity, config),
            reason=reason,
            gross_pnl=gross_pnl,
        ),
        gross_pnl,
    )


def _fee(price: float, quantity: float, config: BacktestConfig) -> float:
    return abs(price * quantity) * config.fee_rate


def _entry_side(direction: Direction) -> str:
    return "buy" if direction is Direction.LONG else "sell"


def _exit_side(direction: Direction) -> str:
    return "sell" if direction is Direction.LONG else "buy"


def _gross_pnl(
    direction: Direction,
    entry_price: float,
    exit_price: float,
    quantity: float,
) -> float:
    if direction is Direction.LONG:
        return (exit_price - entry_price) * quantity
    return (entry_price - exit_price) * quantity


def _skip(signal: TradeSignal, reason: str) -> dict[str, Any]:
    return {
        "symbol": signal.symbol,
        "timeframe": signal.timeframe,
        "setup_type": signal.setup_type,
        "direction": signal.direction.value,
        "signal_time": _serialize_time(signal.signal_time),
        "confidence": signal.confidence,
        "reason": reason,
    }


def _max_drawdown(equity_curve: Iterable[dict[str, Any]]) -> tuple[float, float]:
    peak = None
    max_drawdown = 0.0
    max_drawdown_pct = 0.0
    for point in equity_curve:
        equity = float(point["equity"])
        peak = equity if peak is None else max(peak, equity)
        drawdown = peak - equity
        if drawdown > max_drawdown:
            max_drawdown = drawdown
            max_drawdown_pct = drawdown / peak if peak else 0.0
    return max_drawdown, max_drawdown_pct


def _serialize_time(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
