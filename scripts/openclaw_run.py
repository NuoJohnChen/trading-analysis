#!/usr/bin/env python3
"""Minimal openclaw runner: load YAML spec, dispatch via Claude Code CLI.

Demonstrates that the openclaw YAML harness is a real spec consumed by a
runtime, not just a paper artifact. This runner loads
`openclaw/skills/skill.trading.yaml`, formats its prompt_template, then
shells out to `claude --print` with `trading/SKILL.md` as the system
prompt. The MCP server defined in the skill YAML is auto-spawned by
`claude` from the repo's `.mcp.json`.

Usage:
    python3 scripts/openclaw_run.py --symbol AAPL --target-date 2025-05-28

Why shell out to `claude`: the Anthropic API call inherits Claude Code's
OAuth / keychain auth, which is the simplest credential model for a
local demo. A "real" openclaw engine would use the Anthropic SDK
directly with its own credential management; that path is a small
substitution away.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

import yaml

shlex_quote = shlex.quote

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "openclaw" / "openclaw.config.example.yaml"
DEFAULT_SKILL = REPO_ROOT / "openclaw" / "skills" / "skill.trading.yaml"

# Brand-y banner so the GIF reads as "openclaw is running"
BANNER_TOP = "═" * 70
BANNER = f"""{BANNER_TOP}
  ▶  openclaw runtime — minimal POC dispatcher
{BANNER_TOP}"""


def _step(msg: str) -> None:
    print(f"  · {msg}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Minimal openclaw runner that dispatches a skill via Claude Code."
    )
    parser.add_argument("--symbol", required=True, help="Symbol, e.g. AAPL")
    parser.add_argument("--target-date", required=True, help="Target date YYYY-MM-DD")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--skill", default=str(DEFAULT_SKILL),
                        help="Path to the skill YAML to dispatch")
    parser.add_argument("--max-budget-usd", default="0.50",
                        help="Hard cap passed to claude CLI")
    parser.add_argument("--agent-name", default="openclaw-poc")
    args = parser.parse_args()

    print(BANNER)
    print()

    # Phase 1: load YAML spec
    _step(f"loading config: {Path(args.config).relative_to(REPO_ROOT)}")
    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    _step(f"loading skill spec: {Path(args.skill).relative_to(REPO_ROOT)}")
    with open(args.skill) as f:
        skill = yaml.safe_load(f)

    skill_id = skill["skill"]["id"]
    procedure_source = skill["skill"].get("procedure_source", "")
    procedure_path = (Path(args.skill).parent / procedure_source).resolve()
    model = skill["model_selection"]["preferred_model"]

    _step(f"skill id           = {skill_id}")
    _step(f"model              = {model}")
    _step(f"procedure_source   = {procedure_path.relative_to(REPO_ROOT)}")
    _step(f"mcp_servers        = {[s['id'] for s in skill.get('mcp_servers', [])]}")
    _step(f"tools declared     = {len(skill.get('tools', []))} "
          f"(preferred={sum(1 for t in skill.get('tools', []) if t.get('preferred'))}, "
          f"deprecated={sum(1 for t in skill.get('tools', []) if t.get('deprecated'))})")
    print()

    # Phase 2: format the user prompt from inputs
    user_prompt = (
        f"Run the {skill_id} skill for symbol {args.symbol} on "
        f"{args.target_date}. Follow the procedure in the system prompt. "
        f"Use agent_name={args.agent_name} and model={model} for the "
        f"output filename."
    )
    _step("dispatching via claude CLI ...")
    _step(f"  user prompt: {user_prompt!r}")
    print()
    print(BANNER_TOP)
    print()

    # Phase 3: shell out to `claude --print` with SKILL.md as system prompt.
    # claude auto-loads .mcp.json so the MCP server is wired up for free.
    # Pipe stream-json through our pretty-printer for a readable transcript.
    formatter = REPO_ROOT / "scripts" / "_stream_format.py"
    cmd = (
        f'claude --print --output-format stream-json --verbose '
        f'--max-budget-usd {args.max_budget_usd} --model {model} '
        f'--append-system-prompt-file {procedure_path} '
        f'{shlex_quote(user_prompt)} '
        f'< /dev/null '
        f'| python3 {formatter}'
    )
    t0 = time.monotonic()
    proc = subprocess.run(cmd, shell=True, cwd=str(REPO_ROOT))
    dt = time.monotonic() - t0
    print()
    print(BANNER_TOP)
    print(f"  claude exited rc={proc.returncode} in {dt:.1f}s")

    if proc.returncode != 0:
        print("  dispatch failed; check claude output above")
        return proc.returncode

    # Phase 4: locate the JSON the skill should have written
    safe_model = model.replace("/", "_").replace(".", "-").lower()
    out_path = REPO_ROOT / "results" / "trading" / (
        f"trading_{args.symbol}_{args.agent_name}_{safe_model}.json"
    )
    if out_path.exists():
        try:
            doc = json.loads(out_path.read_text())
            print()
            _step(f"output: {out_path.relative_to(REPO_ROOT)}")
            for rec in doc.get("recommendations", [])[-3:]:
                print(f"        ↳ {rec['date']}  ${rec['price']:.2f}  "
                      f"{rec['recommended_action']}")
        except Exception as e:
            print(f"  (could not parse {out_path}: {e})")
    else:
        # Try the legacy trading_AAPL_openclaw-poc_<model>.json as well
        candidates = list((REPO_ROOT / "results" / "trading").glob(
            f"trading_{args.symbol}_*.json"))
        if candidates:
            _step(f"closest output found: {candidates[-1].relative_to(REPO_ROOT)}")
        else:
            _step("no output JSON found under results/trading/")

    print(BANNER_TOP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
