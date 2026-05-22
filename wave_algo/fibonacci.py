"""Fibonacci retracement and projection helpers."""

from __future__ import annotations

from collections.abc import Sequence

from wave_algo.models import Direction, Pivot, normalize_direction

FIB_382 = 0.382
FIB_500 = 0.5
FIB_618 = 0.618
FIB_1000 = 1.0
FIB_1618 = 1.618
FIB_2618 = 2.618


def retracement_price(start: float, end: float, ratio: float, direction: Direction | str) -> float:
    """Return a retracement price from an impulse start/end pair."""

    sign = normalize_direction(direction).sign
    return float(end) - sign * abs(float(end) - float(start)) * ratio


def retracement_ratio(
    start: float,
    end: float,
    retracement: float,
    direction: Direction | str,
) -> float:
    """Return how much of an impulse has been retraced."""

    length = abs(float(end) - float(start))
    if length == 0:
        return 0.0
    sign = normalize_direction(direction).sign
    return sign * (float(end) - float(retracement)) / length


def wave2_retracement_levels(
    wave1_start: float,
    wave1_end: float,
    direction: Direction | str,
) -> dict[str, float]:
    """Return the first-milestone Wave 2 retracement zone levels."""

    return {
        "50.0%": retracement_price(wave1_start, wave1_end, FIB_500, direction),
        "61.8%": retracement_price(wave1_start, wave1_end, FIB_618, direction),
    }


def wave4_retracement_level(
    wave3_start: float,
    wave3_end: float,
    direction: Direction | str,
) -> float:
    """Return the Wave 4 38.2% retracement level."""

    return retracement_price(wave3_start, wave3_end, FIB_382, direction)


def projection_from(
    anchor: float,
    impulse_start: float,
    impulse_end: float,
    ratio: float,
    direction: Direction | str,
) -> float:
    """Project an impulse length from an anchor price."""

    sign = normalize_direction(direction).sign
    return float(anchor) + sign * abs(float(impulse_end) - float(impulse_start)) * ratio


def wave3_targets(
    wave1_start: float,
    wave1_end: float,
    wave2_end: float,
    direction: Direction | str,
) -> dict[str, float]:
    """Return Wave 3 TP1/TP2 targets based on Wave 1 length."""

    return {
        "tp1_1.618": projection_from(wave2_end, wave1_start, wave1_end, FIB_1618, direction),
        "tp2_2.618": projection_from(wave2_end, wave1_start, wave1_end, FIB_2618, direction),
    }


def wave5_targets(
    wave1_start: float,
    wave1_end: float,
    wave3_end: float,
    wave4_end: float,
    direction: Direction | str,
) -> dict[str, float]:
    """Return first-milestone Wave 5 targets."""

    return {
        "tp1_equal_wave1": projection_from(
            wave4_end,
            wave1_start,
            wave1_end,
            FIB_1000,
            direction,
        ),
        "tp2_0.618_wave1_to_wave3": projection_from(
            wave4_end,
            wave1_start,
            wave3_end,
            FIB_618,
            direction,
        ),
    }


def triangle_measured_width(pivots: Sequence[Pivot]) -> float:
    """Return the widest high-low distance in a triangle candidate."""

    if not pivots:
        return 0.0
    prices = [pivot.price for pivot in pivots]
    return max(prices) - min(prices)


def triangle_measured_target(
    pivots: Sequence[Pivot],
    breakout_price: float,
    direction: Direction | str,
) -> float:
    """Map the triangle measured move from the breakout price."""

    sign = normalize_direction(direction).sign
    return float(breakout_price) + sign * triangle_measured_width(pivots)
