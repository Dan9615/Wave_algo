from wave_algo.models import Pivot
from wave_algo.rules import validate_alternation, validate_impulse, validate_wave_1_to_4


def p(index: int, price: float, kind: str) -> Pivot:
    return Pivot(index=index, time=index, price=price, kind=kind)


def test_valid_long_impulse_passes_hard_rules() -> None:
    pivots = [
        p(0, 100, "low"),
        p(1, 110, "high"),
        p(2, 104, "low"),
        p(3, 125, "high"),
        p(4, 112, "low"),
        p(5, 121, "high"),
    ]

    result = validate_impulse(pivots, "long")

    assert result.valid
    assert result.violations == ()


def test_invalid_wave2_breach_rejected() -> None:
    pivots = [
        p(0, 100, "low"),
        p(1, 110, "high"),
        p(2, 99, "low"),
        p(3, 125, "high"),
        p(4, 112, "low"),
        p(5, 121, "high"),
    ]

    result = validate_impulse(pivots, "long")

    assert not result.valid
    assert "wave2_breach" in {violation.code for violation in result.violations}


def test_invalid_wave3_shortest_rejected() -> None:
    pivots = [
        p(0, 100, "low"),
        p(1, 110, "high"),
        p(2, 105, "low"),
        p(3, 113, "high"),
        p(4, 111, "low"),
        p(5, 124, "high"),
    ]

    result = validate_impulse(pivots, "long")

    assert not result.valid
    assert "wave3_shortest" in {violation.code for violation in result.violations}


def test_invalid_wave4_overlap_rejected() -> None:
    pivots = [
        p(0, 100, "low"),
        p(1, 110, "high"),
        p(2, 104, "low"),
        p(3, 125, "high"),
        p(4, 109, "low"),
    ]

    result = validate_wave_1_to_4(pivots, "long")

    assert not result.valid
    assert "wave4_overlap" in {violation.code for violation in result.violations}


def test_short_impulse_uses_inverted_hard_rules() -> None:
    pivots = [
        p(0, 100, "high"),
        p(1, 90, "low"),
        p(2, 96, "high"),
        p(3, 75, "low"),
        p(4, 88, "high"),
        p(5, 80, "low"),
    ]

    result = validate_impulse(pivots, "short")

    assert result.valid


def test_alternation_accepts_deep_wave2_and_shallow_wave4() -> None:
    result = validate_alternation(wave2_ratio=0.618, wave4_ratio=0.382)

    assert result.valid


def test_alternation_rejects_matching_depths() -> None:
    result = validate_alternation(wave2_ratio=0.55, wave4_ratio=0.52)

    assert not result.valid
    assert result.violations[0].code == "alternation_missing"
