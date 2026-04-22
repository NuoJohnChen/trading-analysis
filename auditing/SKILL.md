---
name: auditing
description: >
  Audits one SEC filing (10-K or 10-Q) by cross-checking its MD&A section
  against its Risk Factors section. For a given (symbol, date,
  document_type, audit_id) tuple, fetches the filing via the `trading_mcp`
  server's `get_filings` tool, extracts notable forward-looking or comparative
  claims from `mda_content`, checks whether each is reflected or contradicted
  in `risk_content`, and writes one structured JSON audit result to
  `results/auditing/`.

  Use this skill whenever the user asks to audit a filing, cross-check an
  MD&A against its risk disclosures, flag risk coverage gaps, or assess
  disclosure consistency in a 10-K or 10-Q — phrased as "audit Apple's
  2024-09-28 10-K", "check MD&A consistency for NVDA Q1", "flag risk
  disclosure gaps in META 10-Q", or "run the auditing task on AAPL 10-K".
---

# Auditing Skill

You are auditing one SEC filing (10-K or 10-Q) by cross-checking its MD&A
section against its Risk Factors section. Your job is to:

1. **Extract notable claims** from the MD&A — forward-looking statements, comparative performance claims, and material operational narratives.
2. **Check risk coverage** — for each claim, determine whether the Risk Factors section addresses the underlying risk, contradicts the claim, or leaves it unaddressed.
3. **Surface concerns** — flag coverage gaps, tone inconsistencies, or specific contradictions.
4. **Write one JSON line of output.**

Data access is via the `trading_mcp` MCP server. There is no parquet, no XBRL
XML, no external API.

---

## Inputs

The user invocation specifies:

| Parameter | Example | Notes |
|---|---|---|
| `agent_name` | `claude-code`, `codex` | your agent name, used in the output filename |
| `symbol` | `AAPL`, `NVDA` | one of the 8 supported symbols |
| `date` | `2024-09-28` | `YYYY-MM-DD`, must match a filing row in the DB |
| `document_type` | `10-K`, `10-Q` | case matters, uppercase with hyphen |
| `audit_id` | `mr_1`, `audit_001` | free-form identifier from the user's request, used verbatim in the filename |
| `model` | `claude-sonnet-4-6` | your model identifier; sanitize for filename use (replace any character that is not alphanumeric, `-`, or `_` with `_`; lowercase) |

Example user request:

```
Please audit Apple's 10-K released 2024-09-28. (id: mr_1)
Save the output to results/auditing/.
```

---

## Data access — DuckDB via MCP

One tool is used for this skill:

| Tool | Purpose |
|---|---|
| `get_filings(symbol, date_start, date_end, document_type?)` | Returns rows `{symbol, date, document_type, mda_content, risk_content}`. Call with `date_start == date_end == {date}` to fetch one specific filing. |

### Fetching the target filing

```python
rows = get_filings(
    symbol=SYMBOL,
    date_start=DATE,
    date_end=DATE,
    document_type=DOCUMENT_TYPE,
)
if not rows:
    raise RuntimeError(f"No filing found for {SYMBOL} {DATE} {DOCUMENT_TYPE}")
filing = rows[0]
mda  = filing["mda_content"]   # MD&A narrative, 5k to 25k chars typically
risk = filing["risk_content"]  # Risk Factors, 30k to 100k chars typically
```

Both fields contain the raw section text as filed (HTML-entity-encoded).
Treat them as plain text for audit purposes — do not attempt to re-parse
HTML.

---

## Ensure the output directory exists

```
results/auditing/
```

Create it if it doesn't exist yet.

---

## The audit workflow

Work through this checklist in order.

### Step 1 — Extract notable MD&A claims

Read `mda_content` and identify **5–10** notable claims. A claim is notable
if it is:

- a **comparative performance statement** (growth rates, revenue comparisons vs prior year, margin expansion / compression)
- a **forward-looking or guidance-adjacent statement** (expected demand, planned investments, strategic direction)
- a **material operational narrative** (new product launches, geographic expansion, customer concentration changes, litigation status)

Numeric statements (e.g., "revenue grew 9% to $X billion") are preferred
over qualitative ones for audit tractability.

Record each claim as a short quote or paraphrase plus a one-line topic tag.

### Step 2 — Check risk coverage

For each MD&A claim, scan `risk_content` for the corresponding risk category:

- **`covered`** — the Risk Factors section discusses the risk that would materialize if the MD&A claim failed to hold (e.g., claim: "We expect continued China revenue growth"; risk coverage: a risk paragraph explicitly naming China, trade policy, or export controls).
- **`partial`** — related risks are discussed but not at the level of specificity the MD&A claim implies (e.g., claim: "We invested $X billion in AI"; risk coverage: general technology-investment risk but no AI-specific disclosure).
- **`absent`** — no matching risk category found. This is the highest-signal finding.
- **`contradictory`** — a risk paragraph actively disputes or softens the MD&A claim (e.g., MD&A says "strong pricing power"; risk says "margin compression from competition").

Ground each classification by citing **one short anchor phrase** from `risk_content`.

### Step 3 — Assess tone consistency

Compare the two sections holistically:

- **`consistent`** — MD&A's forward narrative is appropriately bounded by Risk Factors disclosures.
- **`mildly_divergent`** — MD&A is notably more optimistic than Risk Factors or vice versa, but within typical SEC filing variance.
- **`strongly_divergent`** — a reasonable reader would conclude MD&A and Risk Factors describe materially different company outlooks.

### Step 4 — Surface concerns

List the top 2–4 specific findings. A finding is worth listing if:

- It is an **`absent`** coverage gap with material implications.
- It is a **`contradictory`** pair (MD&A vs Risk Factors).
- It is a **numeric claim** in MD&A that lacks any sensitivity or contingency framing in Risk Factors.

Each finding is one sentence, specific to the claim and the anchor text.

### Step 5 — Overall assessment

A 2–3 sentence paragraph summarizing the most important finding, the
strongest area of consistency, and an overall disclosure-quality verdict.

---

## Output format

Write a single `.json` file to:

```
results/auditing/{agent_name}_auditing_{symbol}_{document_type}_{date}_{audit_id}_{model}.json
```

Sanitize `document_type` by replacing `-` with `_` for filename safety:
`10-K` → `10_K`, `10-Q` → `10_Q`.

Example: `results/auditing/claude-code_auditing_AAPL_10_K_2024-09-28_mr_1_claude-sonnet-4-6.json`

The file is a single JSON object (pretty-printed is OK). Schema:

```json
{
  "symbol": "AAPL",
  "date": "2024-09-28",
  "document_type": "10-K",
  "audit_id": "mr_1",
  "mda_claims": [
    {
      "claim": "Services revenue grew 13% year-over-year, reaching a record.",
      "topic": "services_revenue_growth"
    }
  ],
  "risk_coverage_check": [
    {
      "topic": "services_revenue_growth",
      "coverage": "partial",
      "risk_anchor": "The Company faces significant competition in services markets and pricing pressure from alternative offerings.",
      "note": "Services competition is discussed but no specific risk to the 13% growth rate is flagged."
    }
  ],
  "tone_consistency": "mildly_divergent",
  "concerns": [
    "MD&A cites record services revenue growth without a matched risk disclosure of growth-rate deceleration.",
    "MD&A's AI investment narrative has no corresponding AI-specific risk category in Risk Factors."
  ],
  "overall_assessment": "The filing's MD&A presents growth narratives in four major segments with partial or absent risk coverage for two of them. Risk Factors is exhaustive in macro and regulatory categories but under-discloses product-level risks that would materialize if MD&A growth assumptions fail. Overall disclosure quality is adequate but tilts optimistic."
}
```

**Field rules:**

| Field | Rule |
|---|---|
| `symbol`, `date`, `document_type`, `audit_id` | Echoed from inputs verbatim |
| `mda_claims` | 5–10 entries, each with `claim` and `topic` |
| `risk_coverage_check` | One entry per MD&A claim, keyed by `topic`; each has `coverage` in `{covered, partial, absent, contradictory}`, a `risk_anchor` quote (or empty string if coverage == `absent`), and a one-sentence `note` |
| `tone_consistency` | Exactly one of `consistent`, `mildly_divergent`, `strongly_divergent` |
| `concerns` | 2–4 sentence-level findings, each specific to a claim or anchor phrase |
| `overall_assessment` | 2–3 sentence paragraph |

Do not add keys beyond the schema above.

---

## What NOT to do

- Do **not** read parquet files, XBRL XML, or US-GAAP taxonomy files. Data comes from `get_filings` only.
- Do **not** call external APIs or parse the original SEC website.
- Do **not** invent quotes — every `risk_anchor` must appear in `risk_content` (substring match is enough).
- Do **not** produce audits for multiple filings in one invocation. One `(symbol, date, document_type, audit_id)` per call.
- Do **not** write intermediate scripts, debug logs, or partial files.

---

## Implementation approach

The cleanest approach: run short inline Python via the Bash tool that

1. Calls `get_filings(symbol, date, date, document_type)` and confirms exactly one row.
2. Reads `mda_content` and `risk_content` into variables.
3. Extracts 5–10 MD&A claims (you, the agent, reason over the text and pick them).
4. For each claim, scans `risk_content` for a corresponding category and records the coverage classification with a short anchor phrase.
5. Computes tone-consistency and concerns holistically.
6. Writes the output JSON to the sanitized filename.

Keep all intermediate state in memory. Do not save the script to disk.
