"""Exercise the trading SKILL.md decision branches against the seeded MCP.

New non-trading-day rule (matches upstream SKILL.md):
  - Weekday check (Saturday/Sunday -> HOLD).
  - Missing-row check:
      * target_date <= get_latest_date(symbol) -> market holiday -> HOLD.
      * target_date >  get_latest_date(symbol) -> not yet loaded -> STOP.

No forward-fill check, because the new DuckDB does not forward-fill.

No Claude API call. This reproduces the deterministic branches and verifies
they match the SKILL.md spec. A real run has Claude pick the BUY/SELL/HOLD
action at step 'decide' instead of the momentum-free heuristic used here.
"""

import datetime as dt
import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
SHIM = HERE / "pandas_ta_shim.py"
TRADING_MCP = REPO_ROOT / "trading" / "mcp" / "trading_mcp.py"
DB_PATH = REPO_ROOT / "trading" / "env" / "trading_env.duckdb"
OUT_DIR = HERE / "results" / "trading"

spec = importlib.util.spec_from_file_location("pandas_ta", SHIM)
shim_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shim_mod)
sys.modules["pandas_ta"] = shim_mod
os.environ["TRADING_DB_PATH"] = str(DB_PATH)
sys.path.insert(0, str(TRADING_MCP.parent))
import trading_mcp as tmcp  # noqa: E402

SYMBOL = "AAPL"
AGENT = "claude-code"
MODEL = "claude-sonnet-4-6"


def decide(symbol: str, target_date: str | None) -> dict:
    result = {"symbol": symbol, "target_date_input": target_date}

    if not target_date:
        target_date = tmcp.get_latest_date(symbol)
        result["target_date_resolved_from_latest"] = True
    if not target_date:
        result["outcome"] = "STOP_no_data_in_db"
        return result
    result["target_date"] = target_date

    t = dt.date.fromisoformat(target_date)
    window_start = (t - dt.timedelta(days=7)).isoformat()
    rows = tmcp.get_prices(symbol, window_start, target_date)
    by_date = {r["date"]: r for r in rows}
    today_row = by_date.get(target_date)

    # Weekday check
    weekday = t.weekday()
    if weekday >= 5:
        # Saturday or Sunday - weekend HOLD
        priors = [r for r in rows if r["date"] < target_date]
        price = priors[-1]["adj_close"] if priors else None
        result.update({
            "action": "HOLD",
            "outcome": "forced_HOLD_weekend",
            "weekday": weekday,
            "price_today": price,
        })
        if price is not None:
            _upsert(symbol, target_date, price, "HOLD")
        return result

    # Missing-row branch: distinguish market holiday vs not-yet-loaded
    if not today_row:
        latest = tmcp.get_latest_date(symbol)
        if latest and target_date <= latest:
            priors = [r for r in rows if r["date"] < target_date]
            price = priors[-1]["adj_close"] if priors else None
            result.update({
                "action": "HOLD",
                "outcome": "forced_HOLD_market_holiday",
                "latest_available": latest,
                "price_today": price,
            })
            if price is not None:
                _upsert(symbol, target_date, price, "HOLD")
            return result
        result.update({
            "outcome": "STOP_target_date_not_loaded_yet",
            "latest_available": latest,
        })
        return result

    price_today = today_row["adj_close"]
    result["price_today"] = price_today

    # Simple OHLCV-based heuristic for the smoke test
    priors = [r for r in rows if r["date"] < target_date]
    if priors:
        change = price_today - priors[-1]["adj_close"]
        if change > 0.5:
            action = "BUY"
        elif change < -0.5:
            action = "SELL"
        else:
            action = "HOLD"
    else:
        action = "HOLD"

    result.update({
        "action": action,
        "outcome": "decided_from_ohlcv_heuristic",
        "context": {
            "prior_close": priors[-1]["adj_close"] if priors else None,
            "today_open": today_row["open"],
            "today_close": today_row["close"],
        },
    })
    _upsert(symbol, target_date, price_today, action)
    return result


def _upsert(symbol: str, target_date: str, price: float, action: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"trading_{symbol}_{AGENT}_{MODEL}.json"

    if out_path.exists():
        doc = json.loads(out_path.read_text())
    else:
        doc = {"status": "in_progress", "recommendations": []}

    by_date = {r["date"]: r for r in doc.get("recommendations", [])}
    by_date[target_date] = {"date": target_date, "price": price, "recommended_action": action}

    recs = sorted(by_date.values(), key=lambda r: r["date"])
    doc = {
        "status": "in_progress",
        "symbol": symbol,
        "agent": AGENT,
        "model": MODEL,
        "start_date": recs[0]["date"],
        "end_date": recs[-1]["date"],
        "recommendations": recs,
    }
    out_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False))


out_path = OUT_DIR / f"trading_{SYMBOL}_{AGENT}_{MODEL}.json"
if out_path.exists():
    out_path.unlink()

cases = [
    ("2025-02-22", "Saturday -> weekend HOLD"),
    ("2025-02-17", "Presidents Day (Monday, market holiday) -> market-holiday HOLD"),
    ("2025-02-26", "normal Wednesday -> decide+upsert"),
    ("2030-01-01", "future date with no data -> STOP"),
    (None,         "no date -> resolve from get_latest_date"),
    ("2025-02-26", "idempotent re-run on same date -> overwrite record"),
]

print(f"Output file will be: {out_path}\n")
for target_date, note in cases:
    print("=" * 72)
    print(f"CASE: target_date={target_date!r}  ({note})")
    print("=" * 72)
    r = decide(SYMBOL, target_date)
    print(json.dumps(r, indent=2, default=str))
    print()

print("=" * 72)
print("FINAL ACTION-LIST FILE")
print("=" * 72)
print(out_path.read_text())
