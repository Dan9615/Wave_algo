"""Elliott Wave hard-rule and setup validation."""

from __future__ import annotations

from collections.abc import Sequence

from wave_algo.fibonacci import retracement_ratio
from wave_algo.models import (
    Direction,
    Pivot,
    PivotKind,
    RuleValidationResult,
    RuleViolation,
    normalize_direction,
)

EPSILON = 1e-9


def _result(violations: list[RuleViolation]) -> RuleValidationResult:
    return RuleValidationResult(valid=not violations, violations=tuple(violations))


def _violation(code: str, message: str) -> RuleViolation:
    return RuleViolation(code=code, message=message)


def _expected_kinds(direction: Direction, count: int) -> tuple[PivotKind, ...]:
    if direction is Direction.LONG:
        pattern = (PivotKind.LOW, PivotKind.HIGH)
    else:
        pattern = (PivotKind.HIGH, PivotKind.LOW)
    return tuple(pattern[index % 2] for index in range(count))


def _validate_count_and_kinds(
    pivots: Sequence[Pivot],
    direction: Direction,
    count: int,
) -> list[RuleViolation]:
    violations: list[RuleViolation] = []
    if len(pivots) != count:
        return [
            _violation(
                "pivot_count",
                f"Expected {count} pivots for this validation, received {len(pivots)}.",
            )
        ]

    expected = _expected_kinds(direction, count)
    actual = tuple(pivot.kind for pivot in pivots)
    if actual != expected:
        violations.append(
            _violation(
                "pivot_sequence",
                f"Expected pivot kinds {[kind.value for kind in expected]}, "
                f"received {[kind.value for kind in actual]}.",
            )
        )
    return violations


def _validate_impulse_progression(
    pivots: Sequence[Pivot],
    direction: Direction,
    usable_count: int,
) -> list[RuleViolation]:
    violations: list[RuleViolation] = []
    prices = [pivot.price for pivot in pivots[:usable_count]]
    sign = direction.sign

    for index in range(1, usable_count):
        expected_positive = index % 2 == 1
        move = sign * (prices[index] - prices[index - 1])
        if expected_positive and move <= EPSILON:
            violations.append(
                _violation(
                    "impulse_progression",
                    "Wave leg ending at pivot "
                    f"{index} does not advance in {direction.value} direction.",
                )
            )
        if not expected_positive and move >= -EPSILON:
            violations.append(
                _violation(
                    "impulse_progression",
                    f"Corrective leg ending at pivot {index} does not retrace.",
                )
            )

    return violations


def validate_wave_1_to_2(
    pivots: Sequence[Pivot],
    direction: Direction | str,
) -> RuleValidationResult:
    """Validate the minimum Wave 1/Wave 2 structure needed for a Wave 3 setup."""

    normalized = normalize_direction(direction)
    violations = _validate_count_and_kinds(pivots, normalized, 3)
    if violations:
        return _result(violations)

    violations.extend(_validate_impulse_progression(pivots, normalized, 3))
    p0, p1, p2 = pivots
    if normalized is Direction.LONG and p2.price < p0.price - EPSILON:
        violations.append(
            _violation("wave2_breach", "Wave 2 retraced below the Wave 1 start.")
        )
    if normalized is Direction.SHORT and p2.price > p0.price + EPSILON:
        violations.append(
            _violation("wave2_breach", "Wave 2 retraced above the Wave 1 start.")
        )
    if retracement_ratio(p0.price, p1.price, p2.price, normalized) <= EPSILON:
        violations.append(_violation("wave2_missing", "Wave 2 has no measurable retracement."))
    return _result(violations)


def validate_wave_1_to_4(
    pivots: Sequence[Pivot],
    direction: Direction | str,
    *,
    allow_diagonal: bool = False,
) -> RuleValidationResult:
    """Validate hard rules available once Wave 4 has formed."""

    normalized = normalize_direction(direction)
    violations = _validate_count_and_kinds(pivots, normalized, 5)
    if violations:
        return _result(violations)

    violations.extend(_validate_impulse_progression(pivots, normalized, 5))
    p0, p1, p2, p3, p4 = pivots

    if normalized is Direction.LONG and p2.price < p0.price - EPSILON:
        violations.append(
            _violation("wave2_breach", "Wave 2 retraced below the Wave 1 start.")
        )
    if normalized is Direction.SHORT and p2.price > p0.price + EPSILON:
        violations.append(
            _violation("wave2_breach", "Wave 2 retraced above the Wave 1 start.")
        )

    if not allow_diagonal:
        if normalized is Direction.LONG and p4.price <= p1.price + EPSILON:
            violations.append(
                _violation("wave4_overlap", "Wave 4 overlapped the Wave 1 price territory.")
            )
        if normalized is Direction.SHORT and p4.price >= p1.price - EPSILON:
            violations.append(
                _violation("wave4_overlap", "Wave 4 overlapped the Wave 1 price territory.")
            )

    if normalized.sign * (p3.price - p1.price) <= EPSILON:
        violations.append(_violation("wave3_no_break", "Wave 3 failed to exceed Wave 1."))

    return _result(violations)


def validate_impulse(
    pivots: Sequence[Pivot],
    direction: Direction | str,
    *,
    allow_diagonal: bool = False,
) -> RuleValidationResult:
    """Validate a complete 5-wave impulse against the three hard rules."""

    normalized = normalize_direction(direction)
    violations = _validate_count_and_kinds(pivots, normalized, 6)
    if violations:
        return _result(violations)

    violations.extend(_validate_impulse_progression(pivots, normalized, 6))
    p0, p1, p2, p3, p4, p5 = pivots

    if normalized is Direction.LONG and p2.price < p0.price - EPSILON:
        violations.append(
            _violation("wave2_breach", "Wave 2 retraced below the Wave 1 start.")
        )
    if normalized is Direction.SHORT and p2.price > p0.price + EPSILON:
        violations.append(
            _violation("wave2_breach", "Wave 2 retraced above the Wave 1 start.")
        )

    wave1 = abs(p1.price - p0.price)
    wave3 = abs(p3.price - p2.price)
    wave5 = abs(p5.price - p4.price)
    if wave3 <= min(wave1, wave5) + EPSILON:
        violations.append(
            _violation("wave3_shortest", "Wave 3 is the shortest motive wave.")
        )

    if not allow_diagonal:
        if normalized is Direction.LONG and p4.price <= p1.price + EPSILON:
            violations.append(
                _violation("wave4_overlap", "Wave 4 overlapped the Wave 1 price territory.")
            )
        if normalized is Direction.SHORT and p4.price >= p1.price - EPSILON:
            violations.append(
                _violation("wave4_overlap", "Wave 4 overlapped the Wave 1 price territory.")
            )

    return _result(violations)


def classify_retracement_depth(ratio: float) -> str:
    """Classify a corrective retracement for alternation checks."""

    if ratio >= 0.5:
        return "deep"
    if ratio <= 0.382:
        return "shallow"
    return "moderate"


def validate_alternation(wave2_ratio: float, wave4_ratio: float) -> RuleValidationResult:
    """Validate a first-milestone alternation heuristic."""

    wave2_depth = classify_retracement_depth(wave2_ratio)
    wave4_depth = classify_retracement_depth(wave4_ratio)
    if wave2_depth != wave4_depth and abs(wave2_ratio - wave4_ratio) >= 0.15:
        return RuleValidationResult(valid=True)
    return RuleValidationResult(
        valid=False,
        violations=(
            _violation(
                "alternation_missing",
                f"Wave 2 and Wave 4 do not alternate enough ({wave2_depth}/{wave4_depth}).",
            ),
        ),
    )
