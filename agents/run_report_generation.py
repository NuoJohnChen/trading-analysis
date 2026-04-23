"""Driver for the report_generation skill.

Emits one prompt to stdout per Monday in [start, end] for a single symbol.
The skill itself writes one .md file per Monday; this driver just sequences
the per-Monday invocations so the user can feed them into a session.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

SUPPORTED_SYMBOLS = {"AAPL", "ADBE", "AMZN", "GOOGL", "META", "MSFT", "NVDA", "TSLA"}

PROMPT_TEMPLATE = """\
Write the weekly equity research report for {symbol} dated {monday}
(covering the prior calendar week {week_start} to {week_end}).

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


def _mondays(start: str, end: str):
    d0 = date.fromisoformat(start)
    d1 = date.fromisoformat(end)
    if d1 < d0:
        raise SystemExit("--end must be >= --start")
    cur = d0 + timedelta(days=(7 - d0.weekday()) % 7)
    while cur <= d1:
        yield cur
        cur += timedelta(days=7)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbol", required=True)
    p.add_argument("--start", default="2025-03-01")
    p.add_argument("--end", default="2025-05-31")
    p.add_argument("--agent", default="claude-code")
    p.add_argument("--model", default="claude-sonnet-4-6")
    args = p.parse_args()

    symbol = _validate_symbol(args.symbol)
    printed = 0
    for m in _mondays(args.start, args.end):
        week_start = m - timedelta(days=7)
        week_end = m - timedelta(days=1)
        print("=" * 72)
        print(PROMPT_TEMPLATE.format(
            symbol=symbol,
            monday=m.isoformat(),
            week_start=week_start.isoformat(),
            week_end=week_end.isoformat(),
            agent=args.agent,
            model=args.model,
        ).rstrip())
        printed += 1
    print("=" * 72, file=sys.stderr)
    print(f"[{Path(__file__).name}] emitted {printed} weekly-report prompts for {symbol}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
