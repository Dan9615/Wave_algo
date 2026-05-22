# brainstorm: wave strategy algo

## Goal

Design an Elliott Wave based algorithm from `wave_strategy.md` that can turn OHLCV market data into actionable, testable trade signals. The immediate goal is not to build the full theoretical engine at once, but to converge on a first implementable MVP with clear state, wave validation, scoring, risk rules, and backtestable outputs.

## What I Already Know

* Source document: `wave_strategy.md`.
* The strategy requires multi-timeframe analysis: weekly/monthly for Primary, daily for Intermediate, hourly for Minor/Minute.
* The strategy depends on Elliott Wave hard constraints:
  * Wave 2 must not retrace beyond Wave 1 start.
  * Wave 3 must not be the shortest among Waves 1, 3, and 5.
  * Wave 4 must not overlap Wave 1 territory, except diagonals.
* The document defines three candidate trading situations:
  * Situation A: catch Wave 3 after Wave 1 completes and Wave 2 retraces to 50% or 61.8%.
  * Situation B: catch Wave 5 after Wave 3 is confirmed and Wave 4 consolidates.
  * Situation C: trade triangle breakouts from a-b-c-d-e structures.
* The document asks for OOP wave objects, a market-state machine, backtracking/re-labeling, and unit tests for hard rules plus alternation.
* The current repo has no implementation code yet; it currently contains `AGENTS.md` and `wave_strategy.md`.

## Assumptions (Temporary)

* First implementation should be Python unless the user chooses another runtime.
* First version should be research/backtest focused, not live order execution.
* The engine should emit structured signals with entry, stop, take-profit, confidence score, and invalidation reason.
* The first MVP should focus on the highest edge / lowest complexity subset before expanding into full Elliott Wave classification.

## Open Questions

* None blocking for point-in-time backtest integrity implementation.

## Decisions

* MVP scope includes all three trading situations from `wave_strategy.md`:
  * Situation A: Wave 3 continuation after Wave 2 retracement.
  * Situation B: Wave 5 continuation/exhaustion after Wave 4 consolidation.
  * Situation C: Triangle breakout from a-b-c-d-e structure.
* Because all three setups are in scope, each setup must have a deliberately narrow first version:
  * Wave 3: deterministic Wave 1 / Wave 2 recognition, 50% / 61.8% entry zone, Wave 1 start invalidation, 1.618 / 2.618 targets.
  * Wave 5: confirmed Wave 1-4 structure, Wave 4 38.2% zone, Wave 1 overlap invalidation, channel / 0.618 projection targets, optional divergence score.
  * Triangle: five pivot contraction/expansion detection, trendline breakout trigger, Wave e invalidation, widest-range measured move target.
* First validation market/timeframe:
  * Assets: crypto majors, initially BTC, ETH, and SOL.
  * Primary signal timeframe: 1h.
  * Higher-timeframe trend filter: 4h and/or daily.
  * Lower-timeframe entry confirmation: optional 15m confirmation.
* First execution boundary:
  * Generate structured signals and run backtests only.
  * Do not place live orders in the first version.
  * Do not build paper-trading order state unless explicitly re-scoped later.
* First wave-labeling approach:
  * Use deterministic pivot detection to generate candidate wave endpoints.
  * Apply Elliott Wave hard-rule validation to reject impossible counts.
  * Rank remaining candidates with confidence scoring.
  * Do not use ML/probabilistic labeling in the first version.
  * Do not implement exhaustive recursive backtracking in the first version, though interfaces should not prevent adding relabeling later.
* First pivot detection approach:
  * Use a ZigZag-style percentage reversal threshold to identify swing highs/lows.
  * Add ATR and minimum-bar-distance filters to suppress 1h crypto noise.
  * Keep parameters configurable per asset/timeframe.
  * Do not use manual/annotated pivots for the automated MVP.
* First historical data source:
  * Use the user's existing local OHLCV data rather than downloading from CCXT/Binance in the first version.
  * The current workspace does not contain obvious `.csv`, `.parquet`, `.feather`, `.pkl`, `.json`, `.sqlite`, or `.db` market data files.
* First local data contract:
  * Standard path: `data/ohlcv/{symbol}_{timeframe}.parquet`.
  * Example files: `data/ohlcv/BTCUSDT_1h.parquet`, `data/ohlcv/ETHUSDT_1h.parquet`, `data/ohlcv/SOLUSDT_1h.parquet`.
  * Required schema: `timestamp`, `open`, `high`, `low`, `close`, `volume`.
  * The loader should normalize symbol/timeframe metadata outside the OHLCV columns when needed.
* Trade direction:
  * Generate both long and short signals in the MVP.
  * Use a shared setup engine with direction-aware rule inversion rather than separate duplicated long/short implementations.
* Backtest fill model:
  * Signals are evaluated on bar close.
  * Entries fill at the next bar open.
  * Stops and targets are evaluated using intrabar high/low after entry.
  * If stop and target are both touched in the same bar, assume the stop is hit first.
  * This conservative baseline is preferred over limit-zone or same-close fills for the first MVP.
* Position sizing and portfolio constraints:
  * Risk 1% of current equity per trade.
  * Position size is derived from entry-to-stop distance.
  * Allow at most one open position per symbol.
  * Allow at most three open portfolio positions total.
  * Do not use leverage in the first backtest.
* Fee and slippage model:
  * Charge 0.06% fee per fill.
  * Apply 0.02% slippage per fill.
  * Apply both costs on entry and exit fills.
  * Keep fee and slippage values configurable.
* Exit management:
  * Wave 3 and Wave 5 setups use partial exits: close 50% at TP1 and 50% at TP2.
  * After TP1 fills, move the stop on the remaining position to breakeven.
  * If price later hits the breakeven stop before TP2, exit the remaining 50% at breakeven, still applying costs.
  * Triangle breakout uses a single measured-move target in the first MVP.
* Time stop:
  * Wave 3 and Wave 5 setups have a maximum holding period of 72 bars on the 1h signal timeframe.
  * Triangle breakout setups have a maximum holding period of 48 bars on the 1h signal timeframe.
  * If no stop or target has exited the trade by expiry, exit at the next bar open.
* Higher-timeframe filter:
  * Use higher-timeframe Elliott Wave count rather than an EMA regime filter.
  * The higher-timeframe filter should reuse the same deterministic pivot plus hard-rule validation approach where possible.
  * To keep the MVP bounded, higher timeframes should emit only directional regime states: `bullish`, `bearish`, or `neutral`.
  * 4h alignment is required: long 1h signals require 4h bullish alignment; short 1h signals require 4h bearish alignment.
  * Daily alignment is a veto: daily bearish blocks long signals; daily bullish blocks short signals; daily neutral allows either side if 4h aligns.
  * Neutral or invalid 4h wave counts should block filtered signals but still be reported in diagnostics.
  * Avoid building a separate full recursive higher-timeframe wave classifier in the first MVP.
* Confidence gating:
  * Hard Elliott Wave rules must pass before any candidate can become a signal.
  * Use a 0-100 confidence score for soft constraints.
  * Baseline backtest threshold is 70.
  * Sensitivity runs should also report threshold 60, 70, and 80 results.
* Confidence score weights:
  * Fibonacci fit: 25 points.
  * Higher-timeframe Elliott Wave alignment: 20 points.
  * Channel fit: 15 points.
  * Volume confirmation: 15 points.
  * RSI/MACD divergence or momentum confirmation: 15 points.
  * Alternation and Fibonacci time windows: 10 points combined.
  * The first scoring model is intentionally price-structure and HTF heavy; indicators confirm rather than dominate.
* Implementation runtime and interface:
  * Build a Python package, not a notebook-only prototype.
  * Use a CLI backtester as the first user-facing interface.
  * Use pytest for unit and integration tests.
  * Use pandas and/or polars for OHLCV/parquet pipelines.
* First implementation milestone:
  * Build the core engine skeleton with synthetic tests before wiring real data backtests.
  * Include data models for pivots, waves, signals, targets, scoring breakdowns, and rule validation results.
  * Include deterministic pivot detection, hard-rule validation, Fibonacci target helpers, Wave 3/Wave 5/Triangle signal calculators, and confidence scoring.
  * Include pytest synthetic cases for valid/invalid hard rules, long/short direction inversion, Wave 3 targets, Wave 5 targets, and triangle measured moves.
  * Defer parquet data loading and full portfolio backtesting to the next milestone after wave logic is testable.
* Python package/module boundary:
  * Use a single package named `wave_algo`.
  * Use focused modules rather than one large file or many premature subpackages.
  * Initial modules: `models.py`, `pivots.py`, `rules.py`, `fibonacci.py`, `signals.py`, `scoring.py`, `htf.py`, `backtest.py`, and `cli.py`.
  * First milestone should primarily implement `models.py`, `pivots.py`, `rules.py`, `fibonacci.py`, `signals.py`, and `scoring.py`.
  * `htf.py`, `backtest.py`, and `cli.py` may start as thin/skeleton modules until real-data backtesting is in scope.
* Python dependency/tooling baseline:
  * Use `pyproject.toml` for project metadata and tool configuration.
  * Require Python >= 3.11.
  * Runtime dependencies: pandas, numpy, pyarrow.
  * Development/test dependencies: pytest, ruff.
  * Do not add polars in the first milestone; keep one dataframe API until performance pressure requires another.
* Structured signal output contract:
  * Use a full diagnostic signal contract rather than minimal trading-only fields.
  * Each signal should include at least: `symbol`, `timeframe`, `setup_type`, `direction`, `signal_time`, `entry`, `stop`, `targets`, `confidence`, `score_breakdown`, `htf_state`, `invalidation`, `source_pivots`, and `params`.
  * The contract must support backtesting, debugging, threshold sensitivity, and later chart visualization.
* Next step:
  * Milestone 1 is complete and pushed to `origin/main` at commit `c85bba7`.
  * Milestone 2 is complete and pushed to `origin/main` at commit `4b0b086`.
  * Start Milestone 3 implementation now.
  * Milestone 3 focuses on higher-timeframe Elliott Wave alignment and CLI/report diagnostics for filtered vs unfiltered backtests.
* Second implementation milestone:
  * Add a local OHLCV loader for `data/ohlcv/{symbol}_{timeframe}.parquet`.
  * Validate required schema: `timestamp`, `open`, `high`, `low`, `close`, `volume`.
  * Generate candidate Wave 3, Wave 5, and Triangle Breakout signals from detected pivots.
  * Implement the conservative backtest execution model: signal bar close, next-bar open entry, intrabar stop/target checks, stop-first same-bar collisions, setup time stops.
  * Implement 1% fixed-risk sizing, one position per symbol, max three portfolio positions, configurable fee/slippage, partial exits for Wave 3/Wave 5, and single-target Triangle exits.
  * Implement CLI reporting for configured symbols/timeframes and confidence thresholds 60/70/80.
  * Use synthetic/temp Parquet fixtures in tests; real market data files are optional and should not be required for tests.
* Third implementation milestone:
  * Load optional higher-timeframe OHLCV data from the same local Parquet contract for `4h` and `1d`/`daily` timeframes.
  * Infer HTF Elliott Wave regime states as `bullish`, `bearish`, or `neutral` using deterministic pivots plus existing hard-rule validators where possible.
  * Apply the agreed alignment rule: 4h alignment is required, and daily is a veto.
    * Long signals require 4h bullish; daily bearish blocks long.
    * Short signals require 4h bearish; daily bullish blocks short.
    * Daily neutral does not block if 4h aligns.
  * Preserve an unfiltered diagnostic mode so backtests can compare filtered vs unfiltered signal counts/results.
  * Apply HTF context point-in-time for each signal: filtered backtests must use only 4h/daily bars completed by the signal timestamp, not the latest state from the full HTF file.
  * CLI reports should include HTF data availability, allowed/blocked signal counts, block reasons, and per-threshold results for filtered signals.
  * Tests should use synthetic/temp Parquet fixtures and not require real BTC/ETH/SOL files.
* Point-in-time backtest integrity fix:
  * Signal generation from OHLCV must not detect pivots from the full future dataframe and then assign signals to historical timestamps.
  * Candidate signals must be emitted only using bars available at or before the signal timestamp.
  * If a pivot is only confirmed after later bars, the signal timestamp must be the confirmation bar, not the original pivot bar.
  * HTF filtering must keep using completed higher-timeframe bars as of each signal timestamp.
  * Regression tests must prove that adding future bars cannot create or alter earlier signal timestamps.

## Requirements (Evolving)

* Load local OHLCV data for BTC, ETH, and SOL on at least 1h from `data/ohlcv/{symbol}_{timeframe}.parquet`, with interfaces designed for 4h/daily Elliott Wave trend filters and optional 15m confirmation.
* Provide a command-line entry point for running signal generation and backtests.
* Define project metadata, dependencies, pytest configuration, and ruff configuration in `pyproject.toml`.
* Validate local data schema before running signals or backtests.
* Detect swing pivots from OHLCV data using ZigZag percentage reversal plus ATR/minimum-distance filtering.
* Represent waves as objects with start price, end price, duration, volume, degree, and pivot endpoints.
* Validate core Elliott Wave hard rules.
* Calculate Fibonacci retracement and projection levels.
* Maintain a market state such as `Searching_Wave_2`, `Candidate_Wave_3`, `In_Wave_3_Impulse`, or equivalent.
* Score candidate wave counts on a 0-100 scale using fixed MVP weights: Fibonacci 25, HTF alignment 20, channel 15, volume 15, RSI/MACD 15, alternation/time 10.
* Emit testable diagnostic signal objects rather than only plotting labels.
* Include signal direction (`long` or `short`) and direction-aware entry, stop, target, and invalidation logic.
* Backtest generated signals without exchange order placement using conservative next-open fills.
* Size backtest trades from fixed-risk 1% equity sizing and enforce max-position constraints.
* Deduct configurable fee and slippage costs on every entry and exit fill.
* Support partial exits and breakeven stop movement for Wave 3 / Wave 5 backtests.
* Enforce setup-specific time stops and record time-stop exits separately in backtest output.
* Support three MVP signal families: Wave 3, Wave 5, and Triangle Breakout.
* Provide per-asset and per-timeframe backtest segmentation so 1h signals can be evaluated with and without 4h/daily Elliott Wave filters.
* Report backtest threshold sensitivity for confidence scores 60, 70, and 80.
* Include unit tests for hard rules and alternation.
* First milestone may ship without real market-data backtests if the core engine and synthetic tests are complete.
* Use the `wave_algo` package/module boundary for first-milestone implementation.
* Use the Python >=3.11 / pandas / numpy / pyarrow / pytest / ruff baseline for the Python project.
* Implement Milestone 2 after the core engine and synthetic tests are complete.
* Add a focused local data-loading boundary if needed; keep it inside the `wave_algo` package and update specs if a new module such as `data.py` is introduced.
* Implement Milestone 3 HTF filtering after Milestone 2 local data/backtest infrastructure is complete.
* HTF filtering must be deterministic and diagnostic-first; do not introduce a full recursive wave classifier.
* Backtest integrity requires point-in-time signal generation for both base timeframe pivots and HTF filters.
* HTF filtering must be point-in-time safe for backtests; latest full-file HTF state may appear in availability diagnostics only.

## Acceptance Criteria (Evolving)

* [ ] Given synthetic pivots, the hard-rule validator accepts valid 5-wave structures and rejects invalid structures.
* [ ] Given synthetic Wave 1 and Wave 2 pivots, the engine can calculate Wave 3 entry zone, invalidation stop, and TP1/TP2 targets.
* [ ] Given inverse/downtrend synthetic pivots, the engine can calculate equivalent short-side Wave 3, Wave 5, and triangle breakout signals.
* [ ] Given synthetic Wave 1-4 pivots, the engine can calculate Wave 5 entry zone, invalidation stop, and target candidates.
* [ ] Given synthetic triangle pivots, the engine can identify breakout direction, invalidation stop, and measured-move target.
* [ ] Given OHLCV input, the system can produce structured candidate signals with confidence scores and invalidation reasons.
* [ ] Confidence score breakdown is included in signal diagnostics.
* [ ] Signal diagnostics include symbol/timeframe/setup/direction, entry/stop/targets, HTF state, source pivots, invalidation, and parameter metadata.
* [ ] Signals below the selected confidence threshold are excluded from baseline backtests but counted in diagnostics.
* [ ] Given `data/ohlcv/{symbol}_{timeframe}.parquet`, the loader can read BTC, ETH, and SOL 1h OHLCV into a normalized schema with `timestamp`, `open`, `high`, `low`, `close`, `volume`.
* [ ] A CLI command can run the MVP backtest for configured symbols/timeframes and emit a structured report.
* [ ] Pivot detection parameters are configurable and can be reported in backtest output.
* [ ] Backtest output can evaluate at least win rate, expectancy, max drawdown, and trade count for BTC, ETH, and SOL 1h signals.
* [ ] Backtest output includes confidence threshold sensitivity at 60, 70, and 80.
* [ ] Backtest logic documents and enforces next-open entry fills and stop-first same-bar collision handling.
* [ ] Backtest logic enforces 1% risk sizing, one open position per symbol, and at most three open positions portfolio-wide.
* [ ] Backtest logic applies configurable fee and slippage to every fill.
* [ ] Backtest logic handles 50/50 TP1/TP2 scale-out and breakeven stop movement for Wave 3 / Wave 5 setups.
* [ ] Backtest logic applies 72-bar time stops to Wave 3/Wave 5 and 48-bar time stops to Triangle Breakout.
* [ ] Higher-timeframe Elliott Wave filters produce bullish/bearish/neutral regime states and block non-aligned filtered signals.
* [ ] Tests cover the MVP wave rules and at least one false-positive rejection case.
* [ ] First milestone includes synthetic tests for all three setup calculators before real-data backtesting is required.
* [ ] `pyproject.toml` defines the Python package and test/lint tooling baseline.

## Definition of Done (Team Quality Bar)

* Tests added or updated for unit/integration paths where appropriate.
* Lint / typecheck / CI-equivalent checks pass where tooling exists.
* Docs or notes updated if behavior changes.
* Rollout/rollback considered if any live execution path is introduced.

## Out of Scope (Explicit For MVP Unless Reconfirmed)

* Full support for all Elliott Wave variants beyond the three selected setup families.
* ML/probabilistic wave labeling.
* Exhaustive recursive wave-count backtracking.
* Live exchange order placement.
* Paper-trading account/order simulation.
* Automatic handling of every diagonal, flat, zigzag, W-X-Y, W-X-Y-X-Z, and triangle variant.
* GUI charting or manual relabeling UI.
* Fully automated profitability claims without backtest evidence.

## Technical Notes

* Repo inspection on 2026-05-22 found no existing algorithm modules, package config, tests, or data adapters.
* Local data file search on 2026-05-22 found no obvious market data files in the current workspace.
* The first major design risk is scope: implementing all three situations still requires strict MVP boundaries per setup, otherwise the project becomes a broad Elliott Wave classifier before it has testable trading evidence.
* User selected all three situations on 2026-05-22.
