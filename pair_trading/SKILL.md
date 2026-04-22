---
name: pair_trading
description: >
  Executes a daily pair trading decision task over a 3-month window
  (`2025-03-01` to `2025-05-31`) by querying an offline DuckDB through the
  `trading_mcp` MCP server. Works against an 8-symbol pool
  (AAPL, ADBE, AMZN, GOOGL, META, MSFT, NVDA, TSLA). On the first trading day,
  selects one pair from the pool using only information visible on or before
  that day (emphasis on first-day news across all 8 symbols). Then trades the
  selected pair day by day chronologically with strict no-look-ahead
  discipline, writing one final structured JSON to `results/pair_trading/`.

  Use this skill whenever the user asks you to run a pair trading task, select
  a stock pair and trade it, execute a pair trading simulation, or produce a
  pair trading results JSON — phrased as "run the pair trading experiment",
  "do pair trading on the 8 symbols", "select a pair and trade it", or
  "process the pair trading data".
---

# Pair Trading Skill

You are executing a daily-frequency **pair trading** decision task over a
3-month window (`2025-03-01` to `2025-05-31`) on a fixed 8-symbol pool. All
market data comes from the `trading_mcp` MCP server (offline DuckDB); there is
no parquet, no network access, and no forward-filled rows.

Your job has two stages:

1. **Pair selection stage**: on the **first trading day only**, choose **one
   pair of symbols** from the 8-symbol pool using only information from
   `2025-01-01` to the first trading day (inclusive).
2. **Pair trading stage**: trade that selected pair day by day for the full
   3-month window, emitting one of the allowed pair actions per trading day.

Integrity of the simulation depends entirely on you never using future
information. Read this skill carefully before starting.

---

## Inputs

The user invocation specifies (all optional):

1. **`agent_name`** — your agent identifier, e.g. `claude-code` or `codex`. Used in the output filename.
2. **`model`** — your model identifier, e.g. `claude-sonnet-4-6`. Sanitized for filename use (replace any character that is not alphanumeric, `-`, or `_` with `_`; lowercase).
3. Output folder (default `results/pair_trading/`).

Example phrasings:
- "run the pair trading task"
- "do pair trading on the 8 symbols, save to results/pair_trading/"

---

## Setup

### Symbol pool

The fixed 8-symbol pool:

```
AAPL, ADBE, AMZN, GOOGL, META, MSFT, NVDA, TSLA
```

### Ensure the output directory exists

```
results/pair_trading/
```

Create it if it doesn't exist yet.

---

## Data access — DuckDB via MCP

Four tools on the `trading_mcp` server are used by this skill:

| Tool | Purpose |
|---|---|
| `get_prices(symbol, date_start, date_end)` | Rows `{symbol, date, open, high, low, close, adj_close, volume}`. `adj_close` is the canonical trading price. Also used to enumerate trading days. |
| `get_news(symbol, date_start, date_end)` | Rows `{symbol, date, id, title, highlights}` — zero or more per date. |
| `get_filings(symbol, date_start, date_end, document_type?)` | Rows `{symbol, date, document_type, mda_content, risk_content}`. `document_type` is `"10-K"`, `"10-Q"`, or omitted for both. |
| `get_indicator(symbol, date_start, date_end, indicator, length?)` | Technical indicator from the prices table. Optional. |

### No-look-ahead discipline

On each trading day `t`, all MCP calls must use `date_end <= t`. `date_start`
can be as far back as you want. Never pre-scan dates after `t` for any
purpose — not to choose the pair, not to rank signals, not to decide the
current day's action.

The DuckDB stores rows only for actual trading days. Weekends and market
holidays have **no row**. `get_prices` returning no row for day `t` therefore
means `t` is a non-trading day (or unavailable in the DB); the pair-trading
loop simply skips that day.

---

## Stage 1 — Pair selection on the first trading day

### Determine the first trading day

Call `get_prices(symbol, "2025-03-01", "2025-03-07")` for any one symbol
(e.g. `AAPL`) and take the earliest returned `date`. That is the first
trading day `T1` in the window. All 8 symbols share the same trading-day
calendar, so any symbol produces the same `T1`.

### What information may be used for pair selection

On `T1` only, you may use:

1. Each symbol's visible price history up to and including `T1` (e.g. call `get_prices(symbol, "2025-01-01", T1)` for each of the 8 symbols).
2. Each symbol's news on `T1` (call `get_news(symbol, T1, T1)` for each).
3. Any 10-K / 10-Q filings with `date <= T1` (call `get_filings(symbol, "2024-01-01", T1)` for each). Each row contains separate `mda_content` and `risk_content` fields.

The intended emphasis: **select the pair based on all 8 symbols' news on
`T1`**, with optional support from recent-price trend (adj_close movement
over the visible history) and available filing context.

All news items from the pre-window (2025-01-01 to 2025-02-28) plus `T1` are
given the same weight, regardless of date within that period.

### What pair to select

Choose exactly **two distinct symbols** from the 8-symbol pool. The pair
should look like a good candidate for a relative-value trade over the
upcoming period. Example heuristics:

1. One symbol appears relatively stronger (positive news + price trend), another relatively weaker.
2. Both symbols are in comparable large-cap tech ecosystems with diverging news sentiment.
3. One symbol has positive news / filings catalysts, the other has negative or weaker signals.
4. One symbol faces a clear negative pressure (e.g. regulatory, guidance miss) while the other is stable or improving.

You do **not** need to compute advanced statistical pair metrics over the
full 3-month window. You **must not** use future spread behavior, future
returns, or future correlation to choose the pair.

### Pair selection output behavior

Once the pair is selected:

1. Record it in memory as an **ordered tuple**, e.g. `("META", "MSFT")`.
2. Use the same pair for every subsequent trading day.
3. Never change the pair later.

---

## Stage 2 — The trading loop

After selecting the pair on `T1`, process trading days one at a time in
chronological order. **Never read ahead.**

```
for each trading day t in [2025-03-01 .. 2025-05-31]:
    1. Call get_prices for both symbols with date_start = t - 30 days, date_end = t.
       If either symbol has no row where date == t, skip that day.
    2. Gather signals visible for both symbols on day t:
       - get_news(symbol_i, t - 7 days, t) for each symbol
       - get_filings(symbol_i, t - 1 year, t) for each symbol (only when news
         or recent moves warrant fundamentals)
       - Optionally get_indicator for a directional signal
    3. Reason over the pair relationship and decide one action.
    4. Record the decision immediately to in-memory list.
    5. Move to t+1.
```

Why does order matter? Because this task measures whether you can make
realistic trading decisions without peeking at future prices or future
filings. Even reading tomorrow's news in a pre-scan before making today's
decision is cheating. Treat each day as if you are sitting at a terminal on
that morning.

### Which days to process

Process only days where **both** selected symbols have a `get_prices` row for
that date. Skip weekends, holidays, and any day where one side of the pair
has no row.

Compute date offsets in Python:
`datetime.date.fromisoformat(t) - timedelta(days=N)`.

---

## Signals and reasoning

On each trading day, the visible information is:

- **OHLCV** — today's open / high / low / close / adj_close / volume, plus all prior rows already fetched.
- **News** — today's news items (may be empty). Each row has `title` and `highlights`. Read `title` first for topic; use `highlights` for detail.
- **Filings** — any 10-K / 10-Q rows with `date <= t`. Each row has `mda_content` (MD&A section) and `risk_content` (Risk Factors section).
- **Indicators** — optional MA / RSI / Bollinger / MACD via `get_indicator`.

### How to reason for pair trading

Each daily `trajectory` should briefly explain:

1. Which pair was selected and why it remains the active pair.
2. What signals you saw today for both symbols.
3. Which side looks stronger and which weaker, or why neither side has a clear edge.
4. The action you chose and a one-sentence rationale.

You do not need to be exhaustive — 2 to 3 sentences is enough. The point is
that the reasoning is traceable and grounded in the data actually visible on
that day.

### Allowed daily actions

For each trading day, output exactly one of:

- **`LONG_SHORT`** — long the first symbol in the pair, short the second.
- **`SHORT_LONG`** — short the first symbol, long the second.
- **`HOLD`** — do not initiate or change relative exposure today.

### Action semantics

If the pair is ordered `("META", "MSFT")`:

- **`LONG_SHORT`** means: long META, short MSFT
- **`SHORT_LONG`** means: short META, long MSFT
- **`HOLD`** means: maintain no new directional pair action for the day

Always state the long leg and short leg explicitly in the trajectory.

### Good example

```
Pair: META, MSFT. META adj_close is up 2.1% on today's product-launch news
and strong MD&A commentary, while MSFT is flat with mixed news. Relative
signal favors META. Decision: LONG_SHORT — long META, short MSFT.
```

### Bad example (uses future info)

```
META will outperform MSFT next month, so I choose this pair and go long now.
```

### Optional lightweight heuristics

You may use simple in-loop reasoning heuristics based only on visible
history, such as:

- Comparing short-window `adj_close` trends across the two symbols.
- Comparing the tone or strength of today's news titles and highlights.
- Checking whether either symbol has a visible filing excerpt with notably positive or negative implications in `mda_content` or `risk_content`.
- Comparing get_indicator outputs (e.g. today's RSI or MACD sign).

All heuristics must be computed only from data visible up to day `t`.

### Do not

- Fit models on the full future window.
- Compute future spread reversion statistics.
- Rank pairs using any information from dates after `T1`.
- Revise the initial pair choice at any later date.

---

## Output format

Write a single JSON file to:

```
results/pair_trading/{agent_name}_pair_trading_{pair}_{model}.json
```

Where `{pair}` is the ordered pair with underscore separator (e.g. `META_MSFT`).

```json
{
  "status": "completed",
  "start_date": "2025-03-03",
  "end_date": "2025-05-30",
  "agent": "claude-code",
  "model": "claude-sonnet-4-6",
  "recommendations": [
    {
      "pair": "META, MSFT",
      "date": "2025-03-03",
      "price": {
        "META": 611.32,
        "MSFT": 386.58
      },
      "recommended_action": "LONG_SHORT",
      "trajectory": "Pair selected on the first trading day from the 8-symbol pool: META, MSFT. META adj_close is up on today's product news; MSFT is roughly flat. Relative signal favors META. Decision: LONG_SHORT — long META, short MSFT."
    },
    {
      "pair": "META, MSFT",
      "date": "2025-03-04",
      "price": {
        "META": 605.17,
        "MSFT": 388.40
      },
      "recommended_action": "HOLD",
      "trajectory": "Pair remains META, MSFT. News and price action are mixed today with no clear relative edge. Decision: HOLD."
    }
  ]
}
```

**Field rules:**

| Field | Rule |
|---|---|
| `status` | `"completed"` if all trading days in the window were processed; `"partial"` if stopped early |
| `start_date` | First trading date actually processed |
| `end_date` | Last trading date actually processed |
| `agent` | Agent name (unsanitized) |
| `model` | Model identifier (sanitized for filename use) |
| `recommendations[].pair` | Pair string in fixed order, e.g. `"META, MSFT"` |
| `recommendations[].date` | Trading date string `YYYY-MM-DD` |
| `recommendations[].price` | Object mapping each symbol to its `adj_close` value for that day |
| `recommendations[].recommended_action` | Exactly one of `"LONG_SHORT"`, `"SHORT_LONG"`, `"HOLD"` (uppercase) |
| `recommendations[].trajectory` | Reasoning for that day (2-3 sentences) |

**Write the file once, at the end**, after all decisions are made. Accumulate
decisions in memory and write one final JSON.

### Important note on pair order

The pair order must remain fixed throughout the file. If you selected
`("META", "MSFT")` on day 1, keep writing `"pair": "META, MSFT"` on every
later day.

---

## What NOT to do

- Do **not** read parquet files directly. Data must come from MCP tools.
- Do **not** query MCP with `date_end > t` on trading day `t`.
- Do **not** pre-scan the full 3-month window before selecting the pair.
- Do **not** choose the pair using future returns, future spread behavior, or future news.
- Do **not** change the selected pair after the first trading day.
- Do **not** create temporary `.py` files, notebooks, debug logs, or intermediate files.
- Do **not** modify the result file once written.
- Do **not** output multiple result files for the same run.

If you need to compute something, do it in memory within the pair-selection
step or within the chronological daily loop.

---

## Implementation approach

The cleanest approach is to run short inline Python via the Bash tool that:

1. Determines the first trading day `T1` in the target window via `get_prices` for any one symbol.
2. Calls `get_prices`, `get_news`, and optionally `get_filings` for **each of the 8 symbols** scoped to `[2025-01-01, T1]`. Selects one ordered pair based on first-day-visible signals. Records the pair.
3. Loops over trading days `t` in `[T1, 2025-05-31]`. For each `t`, queries `get_prices` / `get_news` / (optionally) `get_filings` and `get_indicator` for both pair symbols, scoped to `date_end <= t`. Skips `t` if either symbol has no row for `t`.
4. Collects `(pair, date, price, recommended_action, trajectory)` records in memory.
5. Writes one final JSON at the end.

Keep all intermediate computation in memory. Do not save the script to disk.
