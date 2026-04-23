"""Seed a small trading_env.duckdb for smoke tests (new 3-table schema).

Creates:
- ~40 trading days of AAPL OHLCV prices (Mon-Fri only, 2025-01-02 .. 2025-02-28)
- 6 news rows across that window
- 2 filings (one 10-K, one 10-Q)

The DuckDB path defaults to {repo_root}/trading/env/trading_env.duckdb unless
TRADING_DB_PATH is set.

Note: for running the skills against REAL production data, use
scripts/download_data.py to pull from HuggingFace TheFinAI/ab instead.
This seed is meant only for offline CI / smoke runs.
"""

import os
import random
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO_ROOT / "trading" / "env" / "trading_env.duckdb"
DB_PATH = Path(os.environ.get("TRADING_DB_PATH", str(DEFAULT_DB)))
SCHEMA_SQL = (REPO_ROOT / "trading" / "mcp" / "schema.sql").read_text()

DB_PATH.parent.mkdir(parents=True, exist_ok=True)
if DB_PATH.exists():
    DB_PATH.unlink()

con = duckdb.connect(str(DB_PATH))
con.execute(SCHEMA_SQL)

random.seed(42)
start = date(2025, 1, 2)
end = date(2025, 2, 28)

# US market holidays in the seeded range — match real-DB behavior of storing
# rows only for actual trading days (no forward-fill).
MARKET_HOLIDAYS = {
    date(2025, 1, 20),   # MLK Day
    date(2025, 2, 17),   # Presidents Day
}

rows = []
close = 240.00
pid = 0
d = start
while d <= end:
    if d.weekday() < 5 and d not in MARKET_HOLIDAYS:
        pid += 1
        open_ = round(close + random.uniform(-1.5, 1.5), 4)
        close = round(open_ + random.uniform(-3.0, 3.2), 4)
        high = round(max(open_, close) + random.uniform(0.0, 1.5), 4)
        low = round(min(open_, close) - random.uniform(0.0, 1.5), 4)
        adj_close = close  # no splits/dividends in synthetic data
        volume = random.randint(30_000_000, 90_000_000)
        rows.append((pid, "AAPL", d, open_, high, low, close, adj_close, volume))
    d += timedelta(days=1)

con.executemany(
    "INSERT INTO prices (id, symbol, date, open, high, low, close, adj_close, volume) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
    rows,
)

news_rows = [
    (1, "AAPL", datetime(2025, 1, 6, 14, 30),  "Apple announces new iPhone features at CES",          "https://example.com/aapl/1", "Apple announces new iPhone features at CES. Wall Street reacts positively..."),
    (2, "AAPL", datetime(2025, 1, 15, 9, 0),   "Analysts raise AAPL price target on services growth", "https://example.com/aapl/2", "Analysts raise AAPL price target on services growth..."),
    (3, "AAPL", datetime(2025, 1, 15, 16, 45), "Apple Vision Pro demand reported softer than expected","https://example.com/aapl/3", "Apple Vision Pro demand reported softer than expected..."),
    (4, "AAPL", datetime(2025, 2, 3, 8, 0),    "Apple beats Q1 EPS estimates",                         "https://example.com/aapl/4", "Apple reports strong fiscal Q1 earnings, beats EPS estimates."),
    (5, "AAPL", datetime(2025, 2, 10, 13, 15), "Apple expands App Store developer tools",              "https://example.com/aapl/5", "Apple expands App Store developer tools this week."),
    (6, "AAPL", datetime(2025, 2, 22, 18, 0),  "Analyst note: AI investments to pay off in FY25",      "https://example.com/aapl/6", "Weekend analyst note on Apple's AI investment trajectory."),
]
con.executemany(
    "INSERT INTO news (id, symbol, date, title, url, highlights) VALUES (?, ?, ?, ?, ?, ?)",
    news_rows,
)

filing_rows = [
    (1, "AAPL", date(2025, 2, 3), "MD&A: revenue grew 9% YoY to $124.3B. Services hit record $26.3B.", "Risk Factors: macro conditions, supply chain concentration, and foreign exchange could materially affect results.", "10-Q"),
    (2, "AAPL", date(2024, 11, 1), "MD&A: FY24 revenue $391B. iPhone units strong. Services margin expansion.", "Risk Factors: competition in AI, regulatory scrutiny in EU and US, component supply exposure.", "10-K"),
]
con.executemany(
    "INSERT INTO filings (id, symbol, date, mda_content, risk_content, document_type) VALUES (?, ?, ?, ?, ?, ?)",
    filing_rows,
)

con.commit()
con.close()

print(f"Seeded DB at: {DB_PATH}")
print(f"Prices rows : {len(rows)}  (AAPL {start} to {end}, weekdays only)")
print(f"News rows   : {len(news_rows)}")
print(f"Filings rows: {len(filing_rows)}  ({sum(1 for f in filing_rows if f[5]=='10-K')} 10-K, {sum(1 for f in filing_rows if f[5]=='10-Q')} 10-Q)")
