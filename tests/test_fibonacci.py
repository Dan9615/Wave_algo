from pytest import approx

from wave_algo.fibonacci import (
    triangle_measured_target,
    wave3_targets,
    wave5_targets,
)
from wave_algo.models import Pivot


def p(index: int, price: float, kind: str) -> Pivot:
    return Pivot(index=index, time=index, price=price, kind=kind)


def test_wave3_targets_project_long_from_wave2() -> None:
    targets = wave3_targets(100, 110, 104, "long")

    assert targets["tp1_1.618"] == approx(120.18)
    assert targets["tp2_2.618"] == approx(130.18)


def test_wave3_targets_project_short_from_wave2() -> None:
    targets = wave3_targets(100, 90, 96, "short")

    assert targets["tp1_1.618"] == approx(79.82)
    assert targets["tp2_2.618"] == approx(69.82)


def test_wave5_targets_project_long() -> None:
    targets = wave5_targets(100, 110, 125, 113.54, "long")

    assert targets["tp1_equal_wave1"] == approx(123.54)
    assert targets["tp2_0.618_wave1_to_wave3"] == approx(129.0 - 0.01, abs=0.02)


def test_wave5_targets_project_short() -> None:
    targets = wave5_targets(100, 90, 75, 86.46, "short")

    assert targets["tp1_equal_wave1"] == approx(76.46)
    assert targets["tp2_0.618_wave1_to_wave3"] == approx(71.01)


def test_triangle_measured_move_projects_by_direction() -> None:
    pivots = [
        p(0, 100, "low"),
        p(1, 110, "high"),
        p(2, 103, "low"),
        p(3, 108, "high"),
        p(4, 105, "low"),
    ]

    assert triangle_measured_target(pivots, 109, "long") == approx(119)
    assert triangle_measured_target(pivots, 101, "short") == approx(91)
