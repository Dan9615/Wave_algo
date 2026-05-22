"""Shared data contracts for pivots, waves, validation, scoring, and signals."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Direction(StrEnum):
    """Trade or impulse direction."""

    LONG = "long"
    SHORT = "short"

    @property
    def sign(self) -> int:
        return 1 if self is Direction.LONG else -1

    @property
    def aligned_htf_state(self) -> str:
        return "bullish" if self is Direction.LONG else "bearish"


class PivotKind(StrEnum):
    """Swing pivot type."""

    HIGH = "high"
    LOW = "low"


def normalize_direction(direction: Direction | str) -> Direction:
    """Normalize user-facing direction values."""

    if isinstance(direction, Direction):
        return direction
    try:
        return Direction(direction.lower())
    except ValueError as exc:
        raise ValueError(f"Unsupported direction: {direction!r}") from exc


def normalize_pivot_kind(kind: PivotKind | str) -> PivotKind:
    """Normalize user-facing pivot-kind values."""

    if isinstance(kind, PivotKind):
        return kind
    try:
        return PivotKind(kind.lower())
    except ValueError as exc:
        raise ValueError(f"Unsupported pivot kind: {kind!r}") from exc


def _serialize_time(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


@dataclass(frozen=True)
class Pivot:
    """A deterministic swing point produced by pivot detection or synthetic tests."""

    index: int
    time: Any
    price: float
    kind: PivotKind | str
    atr: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", normalize_pivot_kind(self.kind))
        object.__setattr__(self, "price", float(self.price))
        if self.atr is not None:
            object.__setattr__(self, "atr", float(self.atr))

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "time": _serialize_time(self.time),
            "price": self.price,
            "kind": self.kind.value,
            "atr": self.atr,
        }


@dataclass(frozen=True)
class Wave:
    """A wave segment connecting two pivots."""

    label: str
    start: Pivot
    end: Pivot
    degree: str = "minor"
    volume: float | None = None

    @property
    def start_price(self) -> float:
        return self.start.price

    @property
    def end_price(self) -> float:
        return self.end.price

    @property
    def duration(self) -> int:
        return self.end.index - self.start.index

    @property
    def length(self) -> float:
        return abs(self.end.price - self.start.price)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "degree": self.degree,
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
            "start_price": self.start_price,
            "end_price": self.end_price,
            "duration": self.duration,
            "length": self.length,
            "volume": self.volume,
        }


@dataclass(frozen=True)
class RuleViolation:
    """A failed Elliott Wave validation rule."""

    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True)
class RuleValidationResult:
    """Validation result for hard rules and first-milestone setup filters."""

    valid: bool
    violations: tuple[RuleViolation, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "violations": [violation.to_dict() for violation in self.violations],
        }


@dataclass(frozen=True)
class SignalTarget:
    """Take-profit target for a signal."""

    label: str
    price: float
    size_fraction: float = 1.0

    def to_dict(self) -> dict[str, float | str]:
        return {
            "label": self.label,
            "price": self.price,
            "size_fraction": self.size_fraction,
        }


@dataclass(frozen=True)
class ScoreBreakdown:
    """Fixed-confidence scoring contract for MVP candidates."""

    fibonacci_fit: float = 0.0
    htf_alignment: float = 0.0
    channel_fit: float = 0.0
    volume_confirmation: float = 0.0
    momentum_confirmation: float = 0.0
    alternation_time: float = 0.0

    @property
    def total(self) -> float:
        return round(
            self.fibonacci_fit
            + self.htf_alignment
            + self.channel_fit
            + self.volume_confirmation
            + self.momentum_confirmation
            + self.alternation_time,
            6,
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "fibonacci_fit": self.fibonacci_fit,
            "htf_alignment": self.htf_alignment,
            "channel_fit": self.channel_fit,
            "volume_confirmation": self.volume_confirmation,
            "momentum_confirmation": self.momentum_confirmation,
            "alternation_time": self.alternation_time,
            "total": self.total,
        }


@dataclass(frozen=True)
class HTFState:
    """Higher-timeframe diagnostic state."""

    state: str = "neutral"
    timeframe: str | None = None
    reason: str = "not evaluated"

    def __post_init__(self) -> None:
        normalized = self.state.lower()
        if normalized not in {"bullish", "bearish", "neutral"}:
            raise ValueError(f"Unsupported HTF state: {self.state!r}")
        object.__setattr__(self, "state", normalized)

    def to_dict(self) -> dict[str, str | None]:
        return {
            "state": self.state,
            "timeframe": self.timeframe,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class TradeSignal:
    """Full diagnostic signal contract used by signal generation and later backtests."""

    symbol: str
    timeframe: str
    setup_type: str
    direction: Direction | str
    signal_time: Any
    entry: float
    stop: float
    targets: tuple[SignalTarget, ...]
    confidence: float
    score_breakdown: ScoreBreakdown
    htf_state: HTFState = field(default_factory=HTFState)
    invalidation: str = ""
    source_pivots: tuple[Pivot, ...] = ()
    params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "direction", normalize_direction(self.direction))
        object.__setattr__(self, "entry", float(self.entry))
        object.__setattr__(self, "stop", float(self.stop))
        object.__setattr__(self, "confidence", float(self.confidence))

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "setup_type": self.setup_type,
            "direction": self.direction.value,
            "signal_time": _serialize_time(self.signal_time),
            "entry": self.entry,
            "stop": self.stop,
            "targets": [target.to_dict() for target in self.targets],
            "confidence": self.confidence,
            "score_breakdown": self.score_breakdown.to_dict(),
            "htf_state": self.htf_state.to_dict(),
            "invalidation": self.invalidation,
            "source_pivots": [pivot.to_dict() for pivot in self.source_pivots],
            "params": self.params,
        }
