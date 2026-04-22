"""Smoke-test the trading_mcp tools directly (new 3-table schema).

Installs pandas_ta_shim as sys.modules['pandas_ta'] first, then imports
trading_mcp and calls each of the 5 tools against the seeded DB.

Run `python tests/smoke/seed_db.py` first.
"""

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

spec = importlib.util.spec_from_file_location("pandas_ta", SHIM)
shim_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shim_mod)
sys.modules["pandas_ta"] = shim_mod

os.environ["TRADING_DB_PATH"] = str(DB_PATH)
print(f"[setup] TRADING_DB_PATH={os.environ['TRADING_DB_PATH']}")

sys.path.insert(0, str(TRADING_MCP.parent))
import trading_mcp as tmcp  # noqa: E402

print(f"[setup] trading_mcp imported. FastMCP instance: {tmcp.mcp!r}\n")


def dump(label, result, limit_rows=None):
    if isinstance(result, list) and limit_rows and len(result) > limit_rows:
        preview = result[:limit_rows]
        suffix = f" ... (+{len(result)-limit_rows} more, total {len(result)})"
    else:
        preview = result
        suffix = f" (n={len(result)})" if isinstance(result, list) else ""
    print(f"--- {label}{suffix} ---")
    print(json.dumps(preview, indent=2, default=str))
    print()


print("=" * 72)
print("TEST 1: get_latest_date(AAPL)")
print("=" * 72)
latest = tmcp.get_latest_date("AAPL")
dump("get_latest_date", latest)
assert latest == "2025-02-28", f"expected 2025-02-28, got {latest!r}"

print("=" * 72)
print("TEST 2: get_prices(AAPL, 2025-02-20, 2025-02-28) -- OHLCV shape")
print("=" * 72)
rows = tmcp.get_prices("AAPL", "2025-02-20", "2025-02-28")
dump("get_prices", rows, limit_rows=3)
# Verify expected fields
assert rows, "expected rows"
expected_keys = {"symbol", "date", "open", "high", "low", "close", "adj_close", "volume"}
assert set(rows[0].keys()) == expected_keys, f"unexpected keys: {set(rows[0].keys())}"

print("=" * 72)
print("TEST 3: get_news(AAPL, 2025-01-01, 2025-02-28) -- title/url/highlights shape")
print("=" * 72)
news = tmcp.get_news("AAPL", "2025-01-01", "2025-02-28")
dump("get_news", news, limit_rows=2)
assert len(news) == 6, f"expected 6 news rows, got {len(news)}"
assert set(news[0].keys()) == {"symbol", "date", "id", "title", "highlights"}
# verify weekend news (2025-02-22 is a Saturday) is included — DATE cast in MCP handles this
assert any(n["date"] == "2025-02-22" for n in news), "Saturday news should be returned"

print("=" * 72)
print("TEST 4: get_filings(AAPL, 2024-01-01, 2025-02-28) -- mda/risk/document_type shape")
print("=" * 72)
filings = tmcp.get_filings("AAPL", "2024-01-01", "2025-02-28")
dump("get_filings", filings)
assert len(filings) == 2
assert set(filings[0].keys()) == {"symbol", "date", "document_type", "mda_content", "risk_content"}
types = sorted(f["document_type"] for f in filings)
assert types == ["10-K", "10-Q"]

print("=" * 72)
print("TEST 4b: get_filings(AAPL, 2024-01-01, 2025-02-28, document_type='10-K')")
print("=" * 72)
only_10k = tmcp.get_filings("AAPL", "2024-01-01", "2025-02-28", document_type="10-K")
dump("get_filings (10-K only)", only_10k)
assert len(only_10k) == 1 and only_10k[0]["document_type"] == "10-K"

print("=" * 72)
print("TEST 5a: get_indicator(AAPL, 2025-02-17, 2025-02-28, 'ma', length=5)")
print("=" * 72)
ma = tmcp.get_indicator("AAPL", "2025-02-17", "2025-02-28", indicator="ma", length=5)
dump("get_indicator[ma, length=5]", ma, limit_rows=3)
assert ma, "MA should have rows"
assert set(ma[0].keys()) == {"date", "ma"}

print("=" * 72)
print("TEST 5b: get_indicator(AAPL, 2025-02-17, 2025-02-28, 'rsi', length=7)")
print("=" * 72)
rsi = tmcp.get_indicator("AAPL", "2025-02-17", "2025-02-28", indicator="rsi", length=7)
dump("get_indicator[rsi, length=7]", rsi, limit_rows=3)

print("=" * 72)
print("TEST 5c: get_indicator(AAPL, 2025-02-17, 2025-02-28, 'bbands', length=10)")
print("=" * 72)
bb = tmcp.get_indicator("AAPL", "2025-02-17", "2025-02-28", indicator="bbands", length=10)
dump("get_indicator[bbands, length=10]", bb, limit_rows=3)

print("=" * 72)
print("TEST 6: no-look-ahead sanity -- request date_end > latest date")
print("=" * 72)
future_rows = tmcp.get_prices("AAPL", "2025-02-27", "2025-03-15")
dump("get_prices (end past latest)", future_rows)
dates = [r["date"] for r in future_rows]
assert all(d <= "2025-02-28" for d in dates), "Server should only return rows it has"

print("\nALL 5 TOOLS OK")
