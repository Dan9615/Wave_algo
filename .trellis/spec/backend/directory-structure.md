# Directory Structure

> How backend code is organized in this project.

---

## Overview

Backend code for this repo is currently a Python quant package. Keep strategy logic in a
single importable package named `wave_algo`; avoid notebook-only implementations and avoid
spreading first-milestone logic across premature subpackages.

---

## Directory Layout

```
wave_algo/
├── __init__.py
├── data.py        # local OHLCV Parquet loading and schema validation
├── models.py      # shared dataclasses/enums/contracts
├── pivots.py      # deterministic swing-pivot detection
├── rules.py       # Elliott Wave hard-rule and setup validation
├── fibonacci.py   # retracement/projection helpers
├── signals.py     # Wave 3, Wave 5, Triangle signal calculators
├── scoring.py     # confidence scoring weights and breakdowns
├── htf.py         # higher-timeframe regime skeleton/helpers
├── ltf.py         # optional lower-timeframe entry confirmation helpers
├── timeframes.py  # shared timeframe duration and completed-bar slicing helpers
├── backtest.py    # backtest skeleton/helpers
└── cli.py         # CLI entrypoint skeleton/helpers

tests/
├── test_fibonacci.py
├── test_pivots.py
├── test_rules.py
├── test_scoring.py
└── test_signals.py
```

---

## Module Organization

Use focused modules with stable contracts:

- Put reusable data contracts in `models.py`, not in setup-specific modules.
- Put local file I/O and OHLCV schema normalization in `data.py`; do not make signal
  calculators read market-data files directly.
- Put price/math helpers in `fibonacci.py`; do not duplicate Fibonacci formulas in
  signal calculators.
- Put Elliott Wave invalidation logic in `rules.py`; signal calculators should call
  validators instead of re-implementing hard rules inline.
- Put setup construction in `signals.py`; Wave 3, Wave 5, and Triangle setup functions
  should emit the same diagnostic `TradeSignal` contract.
- Put point-in-time higher-timeframe filtering in `htf.py`; do not make CLI or backtest
  code decide 4h/daily alignment inline.
- Put optional lower-timeframe entry confirmation in `ltf.py`; do not make signal
  calculators or backtest code read 15m files directly.
- Put shared timeframe parsing and completed-bar slicing in `timeframes.py`; do not
  duplicate timestamp-boundary logic between HTF and LTF filters.
- Keep `htf.py`, `ltf.py`, `backtest.py`, and `cli.py` thin enough that core rules remain
  in `rules.py`, `pivots.py`, and `signals.py`.

---

## Naming Conventions

- Python package name: `wave_algo`.
- Project distribution name: `wave-algo`.
- Setup names should use stable strings such as `wave3`, `wave5`, and
  `triangle_breakout`.
- Directions are `long` and `short`.
- Higher-timeframe states are `bullish`, `bearish`, and `neutral`.

---

## Examples

- `wave_algo/models.py` is the source of truth for pivot, wave, score, target, HTF, and
  signal payload structures.
- `wave_algo/data.py` is the source of truth for local Parquet OHLCV loading from
  `data/ohlcv/{symbol}_{timeframe}.parquet`.
- `wave_algo/signals.py` is the source of truth for first-milestone setup calculators.
- `wave_algo/timeframes.py` is the source of truth for interpreting compact labels such as
  `15m`, `1h`, `4h`, `1d`, and `daily` when slicing completed bars.
