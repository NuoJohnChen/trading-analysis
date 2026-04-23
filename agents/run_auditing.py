"""Driver for the auditing skill.

Emits one prompt per (symbol, date, document_type) tuple by querying the
trading_env DuckDB's filings table directly. Optionally filters by symbol
or document_type.

This driver touches the DB in read-only mode solely to enumerate filing
rows. It does not call any LLM API.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

SUPPORTED_SYMBOLS = {"AAPL", "ADBE", "AMZN", "GOOGL", "META", "MSFT", "NVDA", "TSLA"}

PROMPT_TEMPLATE = """\
Audit the {document_type} filing for {symbol} dated {date}. (audit_id: {audit_id})

Cross-check the MD&A section against the Risk Factors section per the
auditing SKILL.md procedure. Write one JSON to results/auditing/.

agent_name = {agent}
model = {model}
"""


def _list_filings(db_path: Path, symbol: str | None, document_type: str | None):
    try:
        import duckdb
    except ImportError:
        raise SystemExit("duckdb is required. Install with: pip install duckdb")

    sql = "SELECT symbol, CAST(date AS VARCHAR), document_type FROM filings WHERE 1=1"
    params: list = []
    if symbol:
        sql += " AND symbol = ?"
        params.append(symbol)
    if document_type:
        sql += " AND document_type = ?"
        params.append(document_type)
    sql += " ORDER BY symbol, date, document_type"

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    default_db = repo_root / "trading" / "env" / "trading_env.duckdb"

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default=str(default_db),
                   help="Path to trading_env.duckdb")
    p.add_argument("--symbol", default=None, help="Filter by symbol (one of 8)")
    p.add_argument("--document-type", default=None,
                   choices=["10-K", "10-Q"], help="Filter by filing type")
    p.add_argument("--agent", default="claude-code")
    p.add_argument("--model", default="claude-sonnet-4-6")
    p.add_argument("--audit-id-prefix", default="audit",
                   help="Prefix for generated audit_ids (e.g. audit_001, audit_002)")
    args = p.parse_args()

    sym = args.symbol.upper() if args.symbol else None
    if sym and sym not in SUPPORTED_SYMBOLS:
        raise SystemExit(
            f"Unsupported --symbol {args.symbol!r}. Must be one of: {sorted(SUPPORTED_SYMBOLS)}"
        )

    db_path = Path(os.environ.get("TRADING_DB_PATH", args.db))
    if not db_path.exists():
        raise SystemExit(
            f"DuckDB not found at {db_path}. Run scripts/download_data.py first."
        )

    rows = _list_filings(db_path, sym, args.document_type)
    if not rows:
        print(
            f"[{Path(__file__).name}] no filings matched in {db_path}",
            file=sys.stderr,
        )
        return 1

    for idx, (fsym, fdate, ftype) in enumerate(rows, start=1):
        audit_id = f"{args.audit_id_prefix}_{idx:03d}"
        print("=" * 72)
        print(PROMPT_TEMPLATE.format(
            symbol=fsym,
            date=fdate,
            document_type=ftype,
            audit_id=audit_id,
            agent=args.agent,
            model=args.model,
        ).rstrip())
    print("=" * 72, file=sys.stderr)
    print(
        f"[{Path(__file__).name}] emitted {len(rows)} auditing prompts from {db_path.name}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
