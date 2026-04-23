# Trading skill smoke tests

Deterministic smoke tests for the `trading` skill's MCP server and decision
branches. No Claude API calls, no network, no external data dependencies.

## What these verify

| Script | What it exercises |
|---|---|
| `seed_db.py` | Creates a minimal `trading/env/trading_env.duckdb` with ~40 AAPL trading days (OHLCV), 6 news rows, and 2 filings (1×10-K + 1×10-Q) following the new 3-table schema. |
| `run_tools.py` | Imports `trading/mcp/trading_mcp.py` and calls each of the 5 MCP tools (`get_latest_date`, `get_prices`, `get_news`, `get_filings`, `get_indicator`) against the seeded DB. Asserts expected return shapes. |
| `run_skill_logic.py` | Walks through the trading SKILL.md decision branches (`target_date` resolution, weekend HOLD, market-holiday HOLD via missing-row check, not-yet-loaded STOP, normal decide+upsert, idempotent re-run). Writes a sample action-list JSON under `tests/smoke/results/trading/`. |

## When to run against real data instead

For running the skills against real data (OHLCV / news / filings for all 8
symbols), use `scripts/download_data.py` to pull `trading_env.duckdb` from
the HuggingFace dataset `TheFinAI/ab`:

```bash
python scripts/download_data.py
```

Then `tests/smoke/run_tools.py` works against the real DB too.
`run_skill_logic.py`'s weekend / holiday cases also work against the real DB
since the same schema is used.

## Dependencies

- Python 3.11+
- `duckdb`, `fastmcp`, `pandas`, `numpy`, `pydantic`
- `pandas-ta` is **not** required. `pandas_ta_shim.py` provides a ~50-line
  drop-in replacement covering `sma`, `rsi`, `bbands`, `macd` because PyPI's
  Python-3.11-compatible `pandas-ta` versions are all yanked. The shim is
  injected into `sys.modules` before importing `trading_mcp`.

## Run

From the repo root:

```bash
python tests/smoke/seed_db.py
python tests/smoke/run_tools.py
python tests/smoke/run_skill_logic.py
```

`TRADING_DB_PATH` is respected if you want to point at a different DuckDB
file. Default is `{repo_root}/trading/env/trading_env.duckdb`.

## Expected outcome

- `run_tools.py` ends with `ALL 5 TOOLS OK`.
- `run_skill_logic.py` prints 6 case blocks and a final action-list JSON.
  The Presidents Day (2025-02-17) case exercises the market-holiday
  branch via the missing-row check. The Saturday 2025-02-22 case exercises
  the weekday check.
- `tests/smoke/results/trading/trading_AAPL_claude-code_claude-sonnet-4-6.json`
  is written (gitignored under `results/`).

## Known limitations

- `get_indicator(..., 'macd')` needs 35+ non-NaN periods (slow 26 + signal 9);
  the 40-day synthetic seed barely crosses that threshold. Extend the seed
  window if MACD is the target of a specific test.
- The synthetic data is random-walk OHLCV without corporate events, so
  `adj_close == close` for every row.
