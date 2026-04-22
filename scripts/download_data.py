"""Download trading_env.duckdb from the TheFinAI/ab HuggingFace dataset.

The file is placed at {repo_root}/trading/env/trading_env.duckdb unless
TRADING_DB_PATH is set in the environment.

Usage:
    python scripts/download_data.py
    TRADING_DB_PATH=/custom/path.duckdb python scripts/download_data.py
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEST = REPO_ROOT / "trading" / "env" / "trading_env.duckdb"


def main() -> int:
    dest = Path(os.environ.get("TRADING_DB_PATH", str(DEFAULT_DEST)))
    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print(
            "huggingface_hub is required. Install with: pip install huggingface_hub",
            file=sys.stderr,
        )
        return 2

    print(f"Downloading TheFinAI/ab:trading_env.duckdb ...")
    cached = hf_hub_download(
        repo_id="TheFinAI/ab",
        filename="trading_env.duckdb",
        repo_type="dataset",
    )
    print(f"  cached at: {cached}")

    if Path(cached).resolve() != dest.resolve():
        shutil.copy2(cached, dest)
        print(f"  copied to: {dest}")
    else:
        print(f"  dest is the cache path itself, no copy needed")

    size = dest.stat().st_size
    print(f"  size: {size / 1024 / 1024:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
