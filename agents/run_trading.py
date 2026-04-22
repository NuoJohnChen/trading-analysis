"""Driver for the trading skill.

Emits one prompt to stdout per trading day in [start, end] for a single
symbol. The user pipes or pastes these prompts into a Claude Code (or
openclaw) session whose `.mcp.json` already includes `trading_mcp`.

The driver is read-only; it does not call any LLM API or write any file.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

SUPPORTED_SYMBOLS = {"AAPL", "ADBE", "AMZN", "GOOGL", "META", "MSFT", "NVDA", "TSLA"}

PROMPT_TEMPLATE = """\
trade {symbol} on {target_date}
agent_name = {agent}
model = {model}
"""


def _validate_symbol(s: str) -> str:
    s = s.upper()
    if s not in SUPPORTED_SYMBOLS:
        raise SystemExit(
            f"Unsupported symbol {s!r}. Must be one of: {sorted(SUPPORTED_SYMBOLS)}"
        )
    return s


def _daterange(start: str, end: str):
    d0 = date.fromisoformat(start)
    d1 = date.fromisoformat(end)
    if d1 < d0:
        raise SystemExit("--end must be >= --start")
    cur = d0
    while cur <= d1:
        yield cur.isoformat()
        cur += timedelta(days=1)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbol", required=True, help="Target symbol (one of 8)")
    p.add_argument("--start", required=True, help="Start date YYYY-MM-DD (inclusive)")
    p.add_argument("--end", required=True, help="End date YYYY-MM-DD (inclusive)")
    p.add_argument("--agent", default="claude-code", help="agent_name (default claude-code)")
    p.add_argument("--model", default="claude-sonnet-4-6", help="model identifier")
    p.add_argument("--weekdays-only", action="store_true",
                   help="Skip Saturdays and Sundays (they would be forced HOLD anyway)")
    args = p.parse_args()

    symbol = _validate_symbol(args.symbol)
    printed = 0
    for d in _daterange(args.start, args.end):
        if args.weekdays_only and date.fromisoformat(d).weekday() >= 5:
            continue
        print("=" * 72)
        print(PROMPT_TEMPLATE.format(symbol=symbol, target_date=d, agent=args.agent, model=args.model).rstrip())
        printed += 1
    print("=" * 72, file=sys.stderr)
    print(f"[{Path(__file__).name}] emitted {printed} trading-day prompts for {symbol}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
