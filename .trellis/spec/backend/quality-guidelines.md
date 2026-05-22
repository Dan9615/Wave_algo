# Quality Guidelines

> Code quality standards for backend development.

---

## Overview

Backend quality is enforced with `pytest` and `ruff` from `pyproject.toml`. Strategy code
must be deterministic, testable with synthetic data, and explicit about trade-signal
contracts so later backtests can be reproduced.

---

## Forbidden Patterns

- Do not implement strategy logic only in notebooks.
- Do not duplicate long/short setup logic in separate implementations; use
  direction-aware helpers and tests for inversion.
- Do not emit minimal trading-only signals when the engine is still under research.
  Signals must include diagnostics for score breakdowns, source pivots, HTF state,
  invalidation, and parameters.
- Do not allow triangle breakout signals without checking the relevant trendline
  breakout level. Contraction/expansion alone is not enough.

---

## Required Patterns

- Use `pyproject.toml` for package metadata, dependencies, pytest config, and ruff config.
- Require Python `>=3.11` for backend strategy code.
- Runtime dependencies are currently `numpy`, `pandas`, and `pyarrow`; test/lint tooling is
  `pytest` and `ruff`.
- Keep first-milestone data contracts in dataclasses/enums under `wave_algo.models`.
- A diagnostic trade signal must carry these fields:
  `symbol`, `timeframe`, `setup_type`, `direction`, `signal_time`, `entry`, `stop`,
  `targets`, `confidence`, `score_breakdown`, `htf_state`, `invalidation`,
  `source_pivots`, and `params`.
- Confidence scores use the MVP 100-point breakdown:
  Fibonacci 25, HTF alignment 20, channel 15, volume 15, RSI/MACD 15,
  alternation/time 10.

---

## Testing Requirements

- Run `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest` before claiming tests pass.
- Run `python3 -m ruff check .` before claiming lint passes.
- Synthetic tests must cover:
  - valid and invalid Elliott Wave hard rules;
  - long/short direction inversion;
  - Wave 3 target/stop generation;
  - Wave 5 target/stop generation;
  - triangle measured-move targets;
  - false-positive rejection for invalid setups;
  - diagnostic signal contract fields and score breakdowns.

---

## Code Review Checklist

- Does new logic preserve the shared `TradeSignal` contract?
- Are hard rules centralized in `rules.py` rather than copied into setup calculators?
- Are Fibonacci calculations centralized in `fibonacci.py`?
- Do setup calculators reject invalid candidates with explicit invalidation reasons?
- Do tests include both `long` and `short` behavior where direction inversion matters?
- Does ruff still pass without widening excludes beyond pre-existing generated/support
  folders?

## Scenario: Elliott Wave Signal Engine MVP

### 1. Scope / Trigger
- Trigger: Python package plus CLI entrypoint and structured signal payloads for the
  Elliott Wave strategy engine.

### 2. Signatures
- CLI command: `wave-algo` maps to `wave_algo.cli:main`.
- Signal calculators should return `TradeSignal | None` for one candidate setup, where
  `None` means the setup is rejected.

### 3. Contracts
- Required signal fields:
  `symbol`, `timeframe`, `setup_type`, `direction`, `signal_time`, `entry`, `stop`,
  `targets`, `confidence`, `score_breakdown`, `htf_state`, `invalidation`,
  `source_pivots`, `params`.
- Valid `direction`: `long` or `short`.
- Valid HTF state: `bullish`, `bearish`, or `neutral`.

### 4. Validation & Error Matrix
- Unsupported direction -> raise `ValueError`.
- Unsupported pivot kind -> raise `ValueError`.
- Hard-rule failure -> reject candidate and expose violation/invalidation reason.
- Triangle without trendline breakout -> reject candidate.

### 5. Good/Base/Bad Cases
- Good: valid Wave 3 candidate with hard rules passing, two targets, score breakdown, and
  source pivots.
- Base: candidate below confidence threshold remains diagnostic-only for later reporting.
- Bad: candidate with Wave 2 breaching Wave 1 start is rejected before scoring.

### 6. Tests Required
- Unit tests for rule validators and Fibonacci helpers.
- Unit tests for each setup calculator.
- Regression tests for triangle no-breakout rejection.
- Contract tests for diagnostic signal serialization.

### 7. Wrong vs Correct

#### Wrong
```python
return {"entry": entry, "stop": stop, "target": target}
```

#### Correct
```python
return TradeSignal(
    symbol=symbol,
    timeframe=timeframe,
    setup_type="wave3",
    direction=direction,
    signal_time=signal_time,
    entry=entry,
    stop=stop,
    targets=targets,
    confidence=score.total,
    score_breakdown=score,
    htf_state=htf_state,
    invalidation="wave1_start",
    source_pivots=tuple(pivots),
    params=params,
)
```

## Scenario: Local OHLCV Backtest MVP

### 1. Scope / Trigger
- Trigger: Milestone 2 local Parquet loading, generated OHLCV candidates, and CLI
  backtesting.

### 2. Signatures
- Data loader: `load_ohlcv(symbol: str, timeframe: str, data_dir: str | Path) -> DataFrame`.
- Signal generation: `generate_signals_from_ohlcv(df, *, symbol, timeframe, direction=None,
  directions=None, htf_state=None, pivot_params=None, scan_all=True) -> list[TradeSignal]`.
- Backtest: `run_backtest(market_data, signals, *, threshold=70.0, config=None)`.
- CLI command: `wave-algo backtest --data-dir data/ohlcv --symbols BTCUSDT,ETHUSDT,SOLUSDT
  --timeframes 1h --thresholds 60,70,80`.

### 3. Contracts
- Local OHLCV files use `data/ohlcv/{symbol}_{timeframe}.parquet`.
- Required columns are `timestamp`, `open`, `high`, `low`, `close`, and `volume`.
- Backtest fills use signal bar close for eligibility and next-bar open for entry.
- Active trades only free symbol/portfolio capacity after exits strictly before a new
  candidate entry timestamp. Same-bar intrabar exits must not free capacity for another
  signal entering at that same open.
- Wave 3/Wave 5 use 50% TP1, breakeven stop after TP1, and 50% TP2.
- Triangle breakout uses one measured-move target.
- Default costs are 0.06% fee and 0.02% slippage per fill.
- Default sizing risks 1% of realized equity, caps notional to available equity, allows one
  open position per symbol, and allows at most three portfolio positions.

### 4. Validation & Error Matrix
- Missing Parquet file -> `FileNotFoundError`.
- Missing OHLCV column -> `OHLCVSchemaError`.
- Non-numeric OHLCV price/volume column -> `OHLCVSchemaError`.
- Signal below threshold -> skipped with `below_confidence_threshold`.
- Signal with no next bar -> skipped with `no_next_bar_for_entry`.
- Invalid entry/stop geometry -> skipped with `invalid_stop_for_entry`.

### 5. Good/Base/Bad Cases
- Good: candidate signal has a next bar, valid risk distance, and exits by stop, target, or
  time stop.
- Base: generated candidates below threshold are excluded from trades but counted in skipped
  diagnostics.
- Bad: tests must not require real market data files; use synthetic temp Parquet fixtures.

### 6. Tests Required
- Loader schema, missing-file, and bad-type tests.
- OHLCV-generated Wave 3, Wave 5, and triangle candidate tests.
- Backtest tests for next-open entries, stop-first same-bar collision, fees/slippage, sizing
  constraints, partial exits, breakeven stops, time stops, same-open ordering, and portfolio
  limits.
- CLI smoke test using temp Parquet data.

### 7. Wrong vs Correct

#### Wrong
```python
df = pd.read_parquet("data/ohlcv/BTCUSDT_1h.parquet")
signals = calculate_wave3_signal(detect_pivots(df)[-3:], symbol="BTCUSDT", timeframe="1h")
```

#### Correct
```python
df = load_ohlcv("BTCUSDT", "1h", data_dir)
signals = generate_signals_from_ohlcv(
    df,
    symbol="BTCUSDT",
    timeframe="1h",
    pivot_params=ZigZagParams(reversal_pct=0.03),
)
result = run_backtest({("BTCUSDT", "1h"): df}, signals, threshold=70.0)
```
