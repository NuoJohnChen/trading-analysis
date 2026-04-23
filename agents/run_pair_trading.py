"""Driver for the pair_trading skill.

Emits ONE prompt to stdout covering the full 3-month window for the 8-symbol
pool. The pair_trading skill selects its own pair on day 1 and loops
chronologically to day N, so this driver does not loop per-day. It just
standardizes the invocation.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROMPT_TEMPLATE = """\
Run the pair trading task over the standard 3-month window
(2025-03-01 to 2025-05-31) on the 8-symbol pool
(AAPL, ADBE, AMZN, GOOGL, META, MSFT, NVDA, TSLA).

Select one pair on the first trading day using only information visible
up to that day, then trade that pair chronologically to the end of the
window. Write one final JSON to results/pair_trading/ when done.

agent_name = {agent}
model = {model}
"""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--agent", default="claude-code")
    p.add_argument("--model", default="claude-sonnet-4-6")
    args = p.parse_args()

    print("=" * 72)
    print(PROMPT_TEMPLATE.format(agent=args.agent, model=args.model).rstrip())
    print("=" * 72)
    print(f"[{Path(__file__).name}] emitted 1 pair-trading prompt", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
