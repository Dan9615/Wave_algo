"""Fixed MVP confidence scoring."""

from __future__ import annotations

from wave_algo.models import Direction, HTFState, ScoreBreakdown, normalize_direction

SCORE_WEIGHTS = {
    "fibonacci_fit": 25.0,
    "htf_alignment": 20.0,
    "channel_fit": 15.0,
    "volume_confirmation": 15.0,
    "momentum_confirmation": 15.0,
    "alternation_time": 10.0,
}


def clamp_unit(value: float) -> float:
    """Clamp a scalar to the 0..1 scoring interval."""

    return max(0.0, min(1.0, float(value)))


def fib_fit_score(ratio: float, ideal_ratios: tuple[float, ...], tolerance: float) -> float:
    """Return 0..1 closeness to one of the accepted Fibonacci ratios."""

    if tolerance <= 0:
        raise ValueError("tolerance must be positive")
    nearest_distance = min(abs(float(ratio) - ideal) for ideal in ideal_ratios)
    return clamp_unit(1.0 - nearest_distance / tolerance)


def htf_alignment_score(direction: Direction | str, htf_state: HTFState | str | None) -> float:
    """Return 0..1 score for higher-timeframe alignment."""

    normalized = normalize_direction(direction)
    if htf_state is None:
        state = "neutral"
    elif isinstance(htf_state, HTFState):
        state = htf_state.state
    else:
        state = htf_state.lower()

    if state == normalized.aligned_htf_state:
        return 1.0
    if state == "neutral":
        return 0.5
    return 0.0


def calculate_score(
    *,
    fibonacci_fit: float,
    htf_alignment: float,
    channel_fit: float = 0.5,
    volume_confirmation: float = 0.5,
    momentum_confirmation: float = 0.5,
    alternation_time: float = 0.5,
) -> ScoreBreakdown:
    """Calculate the fixed 0-100 confidence score."""

    return ScoreBreakdown(
        fibonacci_fit=round(clamp_unit(fibonacci_fit) * SCORE_WEIGHTS["fibonacci_fit"], 6),
        htf_alignment=round(clamp_unit(htf_alignment) * SCORE_WEIGHTS["htf_alignment"], 6),
        channel_fit=round(clamp_unit(channel_fit) * SCORE_WEIGHTS["channel_fit"], 6),
        volume_confirmation=round(
            clamp_unit(volume_confirmation) * SCORE_WEIGHTS["volume_confirmation"],
            6,
        ),
        momentum_confirmation=round(
            clamp_unit(momentum_confirmation) * SCORE_WEIGHTS["momentum_confirmation"],
            6,
        ),
        alternation_time=round(clamp_unit(alternation_time) * SCORE_WEIGHTS["alternation_time"], 6),
    )
