---
name: report_generation
description: >
  Generates a structured weekly equity research report for a single symbol
  every Monday over a 3-month window (`2025-03-01` to `2025-05-31`) by
  querying an offline DuckDB through the `trading_mcp` MCP server. Works
  against an 8-symbol pool (AAPL, ADBE, AMZN, GOOGL, META, MSFT, NVDA, TSLA).
  Each report covers the prior week's price action, news, and filings,
  computes key metrics, and issues a graduated BUY/SELL/HOLD rating
  (Strong BUY → BUY → HOLD → SELL → Strong SELL) with supporting analysis.
  All weekly reports for a run are stored as individual .md files inside a
  single run-specific folder:
  `results/report_generation/{agent_name}_report_generation_{SYMBOL}_{model}/`.

  Use this skill whenever the user asks to generate an equity report, produce
  a weekly stock report, write a research note, or evaluate report generation
  — phrased as "write a report for AAPL", "generate weekly reports for NVDA",
  or "produce equity research for MSFT".
---

# Report Generation Skill

You are generating weekly equity research reports for a single symbol over a
3-month window (`2025-03-01` to `2025-05-31`). Every **Monday** in this
window, you write one structured report covering the **prior calendar week**
(the full 7-day period ending the previous Sunday, including weekends and
holidays).

All market data comes from the `trading_mcp` MCP server (offline DuckDB).
There is no parquet, no network access, and no forward-filled rows.

Integrity of the reports depends on never using information beyond what was
available on the Monday the report is written.

---

## Inputs

- **`SYMBOL`** — one of the 8 supported symbols: `AAPL`, `ADBE`, `AMZN`, `GOOGL`, `META`, `MSFT`, `NVDA`, `TSLA`
- **`agent_name`** — your name, e.g. `claude-code` or `codex`
- **`model`** — your model identifier, e.g. `claude-sonnet-4-6`. Sanitized for filename use (replace any character not alphanumeric, `-`, or `_` with `_`; lowercase)
- Output folder (default `results/report_generation/`)

Example phrasing:

```
Please generate weekly equity reports for AAPL. Save the output to /results/report_generation.
```

---

## Setup

### Ensure the output directory exists

```
results/report_generation/{agent_name}_report_generation_{SYMBOL}_{model}/
```

Create it if it doesn't exist yet.

---

## Data access — DuckDB via MCP

The `trading_mcp` server exposes the same 5 tools as the trading skill:

| Tool | Purpose |
|---|---|
| `get_prices(symbol, date_start, date_end)` | Rows `{symbol, date, open, high, low, close, adj_close, volume}`. `adj_close` is the canonical price for all metric computations. |
| `get_news(symbol, date_start, date_end)` | Rows `{symbol, date, id, title, highlights}`. |
| `get_filings(symbol, date_start, date_end, document_type?)` | Rows `{symbol, date, document_type, mda_content, risk_content}`. |
| `get_indicator(symbol, date_start, date_end, indicator, length?)` | Optional technical indicator. |
| `get_latest_date(symbol)` | Latest available trading date for the symbol. |

### No-look-ahead discipline

Every report for Monday `M` must be written using only data visible up to and
including `M`. Every MCP call for that report must have `date_end <= M`.
Never pre-fetch rows past `M`. Never read ahead.

---

## The report generation loop

Identify every **Monday** in the calendar range `2025-03-01` through
`2025-05-31`. For each Monday `M`, write one report using only data visible
on or before that date.

```
for each Monday M in [2025-03-01 .. 2025-05-31]:
    1. If M is not a trading day (market holiday), use the next trading day
       in that calendar week as the report date. Verify by calling
       get_prices(SYMBOL, M, M); if it returns no row, try M+1, M+2, ...
       within the same calendar week.
    2. Identify the prior calendar week: the 7-day period Mon–Sun immediately
       before M (or before the adjusted report date).
    3. Fetch data:
         get_prices(SYMBOL, prior_week_monday - 60d, report_date)
         get_news(SYMBOL, prior_week_monday, prior_week_sunday)
         get_filings(SYMBOL, '2024-01-01', report_date)
    4. Compute all 11 required metrics.
    5. Assemble the full 8-section Markdown report in memory.
    6. Write the report file immediately.
    7. Move to the next Monday.
```

A 3-month window covers ~13 Mondays and produces ~13 `.md` files.

---

## Data available for each report

On Monday `M`, you may use:

- **Prior week's OHLCV** — the trading-day rows within the prior calendar week (Mon–Sun). Use `adj_close` for price metrics.
- **Prior week's news** — all news rows whose `date` falls in the 7-day calendar period (Mon–Sun of the prior week). News has a TIMESTAMP date; the MCP server casts to DATE for the range filter, so weekend news is preserved.
- **All filings up to M** — any `get_filings` rows with `date <= M`. Each row has `mda_content` and `risk_content` separated.
- **Historical prices** — all prior `get_prices` rows up to and including the last trading day of the prior week (for moving average and trend calculations).

---

## Required metrics (compute for each report)

All prices use `adj_close`. All percentage calculations round to 2 decimal places.

| Metric | Definition |
|---|---|
| `week_open` | `adj_close` on the first trading day of the prior week |
| `week_close` | `adj_close` on the last trading day of the prior week |
| `week_high` | Highest `high` value among the trading days within the prior calendar week |
| `week_low` | Lowest `low` value among the trading days within the prior calendar week |
| `weekly_return_pct` | `(week_close - week_open) / week_open × 100` |
| `ma_4week` | Simple average of `adj_close` over the 20 trading days ending the last trading day of the prior week (or fewer if insufficient history) |
| `ma_1week` | Simple average of `adj_close` over the trading days within the prior calendar week |
| `price_vs_ma4` | `"Above"` if `week_close > ma_4week`, `"Below"` otherwise |
| `return_4week_pct` | `(week_close - adj_close_20_days_ago) / adj_close_20_days_ago × 100` (use the earliest available row if fewer than 20 trading days of history exist) |
| `weekly_volatility_pct` | `(week_high - week_low) / week_open × 100` — intra-week price range as percent of open |
| `ma_direction` | `"Up"` if `ma_1week > ma_4week`, `"Down"` if `ma_1week < ma_4week`, `"Flat"` if equal — short-MA-vs-long-MA direction as a recent-trend proxy |

---

## Report sections

Each report must contain all **8** sections, following professional equity
research update conventions:

### 1. Executive Summary
One paragraph (3–5 sentences) covering the single most important development
of the week. State the investment rating and a one-sentence thesis at the end.

### 2. Investment Rating & Thesis
State the rating using the 5-level scale:

| Rating | When to use |
|---|---|
| **Strong BUY** | Evidence is clearly and broadly positive across multiple signals |
| **BUY** | Evidence leans positive but not all signals align |
| **HOLD** | Signals are genuinely mixed; no clear directional lean |
| **SELL** | Evidence leans negative but not uniformly so |
| **Strong SELL** | Evidence is clearly and broadly negative across multiple signals |

Provide 2–3 bullet points explaining the **investment thesis**. Each bullet
should be a distinct, evidence-based argument grounded in the week's data.

Apply your own analytical judgment — weigh price action, MA direction, news
sentiment, and any filing signals holistically. **HOLD is not the safe
default**; use it only when you genuinely cannot determine a directional lean.

### 3. Weekly Price Performance & Technical Indicators

Present all 11 computed metrics in a structured table (see template below).

### 4. News & Catalysts

Bullet-point summary of the **3–5 most significant news items** from the
prior week, covering the full 7-day calendar period (weekend and holiday
news is equally valid and must not be omitted). Each bullet: one to two
sentences — what happened and why it matters for the stock.

Each news row from `get_news` has `title` and `highlights`. Read `title` for
the headline; use `highlights` for content context. Group related items if
the week had many similar stories. If no news was available, state that
explicitly.

### 5. Earnings & Filings Update

Summarize any `10-K` or `10-Q` filings that became available on or before
Monday `M`. Each filing row has separate `mda_content` (MD&A) and
`risk_content` (Risk Factors) sections. Focus on content relevant to the
investment thesis: revenue trends, margin commentary, forward guidance, or
risk disclosures. Distinguish MD&A narrative vs Risk Factors explicitly
where useful. If no filings are available, state that explicitly.

### 6. Valuation Snapshot

Simplified valuation commentary given the data available:

- Note the stock's recent price trend relative to its 4-week MA as a momentum-based fair-value signal.
- If financial data appears in MD&A excerpts (e.g., revenue, margins, EPS), compute or cite relevant multiples.
- Comment on whether the stock appears stretched, fairly valued, or compressed relative to its recent trading range and any available fundamental data.

### 7. Risk Factors

List 2–4 **specific, evidence-based** risks from the week's data —
regulatory, competitive, macro, operational, or sentiment risks visible in
news or filing `risk_content`. Each risk should be one sentence. Avoid
generic boilerplate; tie each risk to actual content observed in the data.

### 8. Recommendation & Outlook

Restate the rating. Then 2–3 sentences: what specific factors to monitor in
the coming week, and what would cause a rating change (upside catalyst or
downside trigger). Base all outlook commentary strictly on information
available as of Monday `M`.

---

## Output format

Write **one Markdown file per Monday report** to:

```
results/report_generation/{agent_name}_report_generation_{SYMBOL}_{model}/{agent_name}_report_generation_{SYMBOL}_{YYYYMMDD}_{model}.md
```

Where `{YYYYMMDD}` is the report date. Example for the first report:

```
results/report_generation/claude-code_report_generation_AAPL_claude-sonnet-4-6/claude-code_report_generation_AAPL_20250303_claude-sonnet-4-6.md
```

Use the exact template below:

````markdown
# Equity Research Report: {SYMBOL}

**Agent:** {agent_name} | **Model:** {model} | **Report Date:** {report_date}
**Week Covered:** {week_start} to {week_end} | **Rating:** {RATING_EMOJI} {RATING}

---

### 1. Executive Summary
{3–5 sentence paragraph}

---

### 2. Investment Rating & Thesis
**Rating: {RATING}**

- {thesis bullet 1}
- {thesis bullet 2}
- {thesis bullet 3}

---

### 3. Weekly Price Performance & Technical Indicators

| Metric                   | Value        |
|--------------------------|--------------|
| Open                     | $227.45      |
| Close                    | $229.10      |
| Weekly Return            | +0.73%       |
| Week High                | $231.50      |
| Week Low                 | $226.80      |
| Intra-week Volatility    | 2.07%        |
| 1-Week MA                | $228.60      |
| 4-Week MA                | $228.30      |
| Price vs 4-Week MA       | Above        |
| 4-Week Cumulative Return | -1.24%       |
| MA Direction             | Up           |

---

### 4. News & Catalysts
- **{headline}:** {1–2 sentence impact summary}
- **{headline}:** {1–2 sentence impact summary}

---

### 5. Earnings & Filings Update
{Summary of MD&A / Risk Factors content from available filings, or
"No filings available as of {report_date}."}

---

### 6. Valuation Snapshot
{Paragraph: price vs MA commentary, any multiples from filings if available,
overall fair value assessment}

---

### 7. Risk Factors
- {Specific risk 1 tied to observed data}
- {Specific risk 2}
- {Specific risk 3}

---

### 8. Recommendation & Outlook
**{RATING}.** {2–3 sentences on what to monitor next week and what would
trigger a rating change.}
````

---

**Format rules:**

| Element | Rule |
|---|---|
| Rating emoji | ⬆⬆ Strong BUY, ⬆ BUY, ➡ HOLD, ⬇ SELL, ⬇⬇ Strong SELL — on the header line |
| Metrics table | All 11 metrics required; use `$` prefix for prices, `%` suffix for returns |
| Prices | Round to 2 decimal places |
| Percentages | Include sign (`+0.73%`, `-1.24%`); round to 2 decimal places |
| News bullets | Bold the headline or topic as the bullet label |
| Section headers | Use exact `###` level shown; do not rename or reorder sections |
| Horizontal rules | `---` between each section within a report |
| Empty data | State explicitly (`No news this week.`, `No filings available.`) |

**Write each file immediately** after generating that Monday's report. Do not
accumulate all reports in memory and write at the end.

---

## What NOT to do

- Do **not** read parquet files directly. Data must come from MCP tools.
- Do **not** query MCP with `date_end > M` for the Monday `M` report.
- Do **not** invent price levels, news, or filing content not present in the DB.
- Do **not** skip any calendar Monday in the window without a reason (holiday = use next trading day).
- Do **not** write partial reports — all 8 sections must be present for every weekly report.
- Do **not** rename or reorder the section headers.
- Do **not** leave the metrics table incomplete — compute all 11 metrics from available history even if the window is shorter than 20 days.
- Do **not** create temporary `.py` files, notebooks, debug logs, or intermediate files.
- Do **not** combine all weekly reports into a single output file — each Monday must produce its own `.md` file.
- Do **not** write report files directly to `results/report_generation/` — all files must go inside the run-specific subfolder `{agent_name}_report_generation_{SYMBOL}_{model}/`.
- Do **not** output raw JSON — the output must be `.md` Markdown files.

---

## Implementation approach

The cleanest approach: run short inline Python via the Bash tool that, for
each Monday `M` in the window, calls the MCP tools scoped to `date_end <= M`,
computes all 11 metrics, assembles the full Markdown report in memory, and
writes it immediately to its own dated `.md` file before moving to the next
Monday. A 3-month window produces ~13 files. Do not save the script to disk.
