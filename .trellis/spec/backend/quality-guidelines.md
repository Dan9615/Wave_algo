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
  directions=None, htf_state=None, pivot_params=None, scan_all=True,
  point_in_time=True) -> list[TradeSignal]`.
- Backtest: `run_backtest(market_data, signals, *, threshold=70.0, config=None)`.
- CLI command: `wave-algo backtest --data-dir data/ohlcv --symbols BTCUSDT,ETHUSDT,SOLUSDT
  --timeframes 1h --thresholds 60,70,80`.

### 3. Contracts
- Local OHLCV files use `data/ohlcv/{symbol}_{timeframe}.parquet`.
- Required columns are `timestamp`, `open`, `high`, `low`, `close`, and `volume`.
- Treat `timestamp` as the bar-open time. Completion checks for higher timeframes should
  add the timeframe duration and include only bars whose end time is at or before the
  signal timestamp.
- OHLCV-generated signals must be point-in-time safe by default. The default scanner must
  use confirmed pivot windows only and must not assign Wave 3/Wave 5 signal timestamps
  earlier than the latest pivot-confirmation bar in the candidate window.
- Triangle signals generated from OHLCV must not scan for breakouts before the full
  five-pivot window is confirmed; the signal timestamp is the breakout bar.
- A full-frame OHLCV scanner may exist only as an explicit diagnostic opt-out such as
  `point_in_time=False`, and generated signals must identify that mode in params (for
  example `generation_mode="full_frame"`). CLI backtests must use the point-in-time path
  by default.
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
- Adding future bars must not create or change signal timestamps at or before the previous
  frame end when `point_in_time=True`.

### 5. Good/Base/Bad Cases
- Good: candidate signal has a next bar, valid risk distance, and exits by stop, target, or
  time stop.
- Base: generated candidates below threshold are excluded from trades but counted in skipped
  diagnostics.
- Bad: tests must not require real market data files; use synthetic temp Parquet fixtures.

### 6. Tests Required
- Loader schema, missing-file, and bad-type tests.
- OHLCV-generated Wave 3, Wave 5, and triangle candidate tests.
- Regression tests for point-in-time signal generation: prefix-generated signals must match
  the full-frame signals whose `signal_time` is at or before the prefix end, and Wave
  3/Wave 5 signal indexes must equal the latest source pivot confirmation index.
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

## Scenario: Higher-Timeframe Elliott Wave Filter MVP

### 1. Scope / Trigger
- Trigger: Milestone 3 optional 4h/daily Parquet loading, HTF state inference, signal
  filtering, and CLI diagnostics.

### 2. Signatures
- HTF state from pivots: `infer_htf_state_from_pivots(pivots, timeframe=None) -> HTFState`.
- HTF state from OHLCV: `infer_htf_state_from_ohlcv(df, *, timeframe=None,
  pivot_params=None) -> HTFState`.
- Optional context loader: `load_htf_context(symbol, data_dir, *, alignment_timeframe="4h",
  veto_timeframes=("1d", "daily"), pivot_params=None) -> HTFContext`.
- Signal filter: `filter_signals_by_htf(signals, contexts, *, alignment_timeframe="4h")
  -> HTFFilterResult`.
- CLI default: `wave-algo backtest` applies HTF filtering unless `--no-htf-filter` is passed.

### 3. Contracts
- Optional HTF files use the same local contract: `data/ohlcv/{symbol}_{timeframe}.parquet`.
- The 4h alignment timeframe is required for filtered signals. Long requires 4h `bullish`;
  short requires 4h `bearish`.
- Daily/1d is a veto only. Daily `bearish` blocks long; daily `bullish` blocks short; daily
  `neutral` or unavailable does not block if 4h aligns.
- HTF state inference is bounded: use deterministic pivots and latest hard-rule validator
  windows (`validate_impulse`, `validate_wave_1_to_4`, then `validate_wave_1_to_2`). Do not
  add a recursive wave classifier for this milestone.
- Filtered backtests must be point-in-time safe: the filter recomputes 4h/daily state for
  each signal using only HTF bars completed by that signal timestamp. Full-file/latest HTF
  state is diagnostic availability only and must not decide historical signals.
- Generate the raw signal set with neutral/no HTF scoring before applying the HTF filter;
  the filter updates each allowed/blocked signal's HTF state and HTF score from the
  point-in-time alignment result.
- CLI reports must keep generated counts separate from `backtested_signal_count`, and include
  HTF availability, allowed/blocked counts, block reasons, and threshold summaries for the
  filtered signal set.

### 4. Validation & Error Matrix
- Missing 4h file -> alignment state `neutral`, unavailable, filtered signals blocked with
  `4h_unavailable`.
- Missing daily/1d file -> veto state `neutral`, unavailable, no veto block.
- Insufficient or invalid HTF pivots -> state `neutral` with diagnostic reason; 4h neutral
  blocks filtered signals, daily neutral does not.
- Bad optional HTF schema -> unavailable HTF result with error text in diagnostics, not a
  required-market-data CLI failure.

### 5. Good/Base/Bad Cases
- Good: valid 4h bullish pivots allow long signals unless daily is bearish.
- Base: daily neutral/missing leaves aligned 4h signals eligible for backtest.
- Bad: 4h missing, neutral, bearish-for-long, or bullish-for-short blocks filtered signals
  while preserving generated unfiltered counts.

### 6. Tests Required
- Unit tests for bullish, bearish, neutral, invalid, and insufficient HTF inference.
- Unit tests for 4h alignment, daily veto, and missing-4h block reasons.
- Regression tests that prove a future/latest 4h or daily state cannot allow or veto a signal
  before the relevant HTF bars are complete.
- CLI smoke/integration tests using temp Parquet fixtures for 1h plus optional 4h/daily data.
- Filtered backtest diagnostics must assert generated, allowed, blocked, and threshold
  processed counts.

### 7. Wrong vs Correct

#### Wrong
```python
signals = generate_signals_from_ohlcv(df, symbol=symbol, timeframe="1h")
result = run_backtest(market_data, signals)
```

#### Correct
```python
contexts = {
    symbol: load_htf_context(symbol, data_dir, pivot_params=pivot_params)
    for symbol in symbols
}
signals = generate_signals_from_ohlcv(
    df,
    symbol=symbol,
    timeframe="1h",
    htf_state="neutral",
    pivot_params=pivot_params,
)
filtered = filter_signals_by_htf(signals, contexts)
result = run_backtest(market_data, filtered.allowed_signals)
```
