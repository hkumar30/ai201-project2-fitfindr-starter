# FitFindr

FitFindr is a multi-tool AI agent that helps users find secondhand clothing and figure out how to wear it. You describe what you're looking for in natural language, and the agent searches a dataset of mock thrift listings, uses an LLM to suggest outfit combinations from your existing wardrobe, and generates a shareable OOTD caption — all in a single interaction.

![GUI of FitFindr](https://github.com/hkumar30/ai201-project2-fitfindr-starter/blob/e2f39c2ba8f8cf8668bdfe7404aee323d522686f/images/fitfindr_gui_example.png)

<center><p> Figure 1. GUI of FitFindr - Your Smart Personal Wardrobe</p></center>

Demo: https://www.youtube.com/watch?v=jx7j3betvBo

## Setup

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

Add your Groq API key to a `.env` file in the project root (free key at [console.groq.com](https://console.groq.com)):
```
GROQ_API_KEY=your_key_here
```

**Run the app:**
```bash
python app.py
```
Open the URL shown in the terminal (usually `http://localhost:7860`).

**Run the tests:**
```bash
pytest tests/ -v
```

**Run the CLI directly:**
```bash
python agent.py
```

---

## Stretch Features

All four stretch features are implemented:

- **Price comparison tool** — `compare_price()` estimates whether a listing's price is fair using dataset comparables. No LLM required — pure math.
- **Style profile memory** — `utils/profile.py` saves style tags, preferred size, and search history to `user_profile.json` after each successful session and loads them on the next run. The second interaction automatically incorporates preferences from the first.
- **Trend awareness** — `get_trend_report()` cross-references an item against `data/trends.json` (aggregated from Depop trending searches and Pinterest fashion boards) and uses the Groq LLM to produce a 2–3 sentence trend assessment that flows into `suggest_outfit` as context.
- **Retry logic with fallback** — If `search_listings` returns no results with a size filter set, the agent automatically retries without size. If still empty and a price filter was set, retries with both filters removed. A `⚠️` note in the listing panel tells the user exactly what was loosened.

---

## Tool Inventory

### `search_listings(description, size, max_price)`

**Purpose:** Searches the mock listings dataset and returns items ranked by relevance to the user's query.

**Inputs:**
- `description` (str) — Keywords describing what the user wants, e.g. `"vintage graphic tee"`. Tokenized into lowercase words for scoring.
- `size` (str | None) — Size string to filter by, e.g. `"M"` or `"S/M"`. Case-insensitive substring match — `"M"` matches listings sized `"M"`, `"S/M"`, and `"M/L"`. Pass `None` to skip size filtering.
- `max_price` (float | None) — Maximum price, inclusive. Listings priced above this are dropped before scoring. Pass `None` to skip price filtering.

**Output:** `list[dict]` — Matching listing records sorted by relevance score (highest first). Each dict contains `id`, `title`, `description`, `category`, `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list), `brand` (str or None), and `platform`. Returns `[]` on no match — never raises.

**How scoring works:** For each listing, the tool builds a set of all unique words from the title, description, category, style tags, and colors. The score is the count of query tokens that appear in that set. A listing tagged `["vintage", "graphic tee"]` scores 3 against a query of `"vintage graphic tee"` because all three tokens (`vintage`, `graphic`, `tee`) are present after splitting. Zero-score listings are dropped entirely.

---

### `suggest_outfit(new_item, wardrobe, context=None)`

**Purpose:** Given a thrifted item the user is considering buying and their existing wardrobe, uses an LLM to suggest 1–2 complete outfit combinations.

**Inputs:**
- `new_item` (dict) — A listing dict returned by `search_listings`. The prompt uses `title`, `description`, `style_tags`, `colors`, `price`, and `platform`.
- `wardrobe` (dict) — A wardrobe dict with an `"items"` key containing a list of wardrobe item dicts, each with `name`, `category`, `colors`, `style_tags`, and optional `notes`. Accepts an empty wardrobe (`{"items": []}`) — handled explicitly without raising.
- `context` (str | None) — Optional context string combining the trend report from `get_trend_report` and the user's accumulated style history from `load_style_profile`. When provided, appended to the LLM prompt so outfit suggestions reflect current trends and the user's known tastes. Pass `None` to skip (e.g., in tests). Defaults to `None`.

**Output:** `str` — A non-empty outfit suggestion. For a populated wardrobe, the response names specific wardrobe pieces by name in each outfit. For an empty wardrobe, it provides general styling advice (what silhouettes, colors, and occasions work for the item).

**Model:** `llama-3.3-70b-versatile`, temperature 0.7.

---

### `create_fit_card(outfit, new_item)`

**Purpose:** Turns the outfit suggestion into a 2–4 sentence Instagram/TikTok caption that sounds like a real OOTD post.

**Inputs:**
- `outfit` (str) — The outfit suggestion string from `suggest_outfit`. If empty or whitespace-only, the function returns an error message string without calling the LLM.
- `new_item` (dict) — The listing dict for the thrifted item. Used to provide `title`, `price`, and `platform` to the prompt.

**Output:** `str` — A casual, specific caption that mentions the item name, price, and platform exactly once each. Because temperature is set to 0.9, the output varies meaningfully across calls with different inputs. If `outfit` is empty/whitespace, returns `"Unable to generate fit card: no outfit suggestion was provided."` without making an API call.

**Model:** `llama-3.3-70b-versatile`, temperature 0.9.

---

### `compare_price(item, listings)`

**Purpose:** Estimates whether the selected listing's price is fair by comparing it against similar items in the same dataset — no LLM required.

**Inputs:**
- `item` (dict) — The selected listing dict. Uses `id`, `category`, `style_tags`, `title`, and `price`.
- `listings` (list[dict]) — The full dataset from `load_listings()`. The item itself is excluded from the comparable set.

**How comparables are found:** Listings with the same `category` and at least one overlapping `style_tag`. Requires ≥ 2 comparables for a meaningful verdict.

**Output:** `str` — Three lines: price + verdict (`GREAT DEAL` / `FAIR PRICE` / `ABOVE AVERAGE`), comparable set stats (count, avg, median, range), and one sentence of reasoning. Returns a descriptive message string if fewer than 2 comparables exist — never raises.

**Verdict thresholds:** ≤ 80% of comparable median → GREAT DEAL; 81–110% → FAIR PRICE; > 110% → ABOVE AVERAGE.

---

### `get_trend_report(item)`

**Purpose:** Assesses whether the selected item is currently on-trend based on aggregated fashion platform data, and produces context that directly influences `suggest_outfit`.

**Inputs:**
- `item` (dict) — The selected listing dict. Uses `title`, `category`, `style_tags`, and `colors`.

**Data source:** `data/trends.json` — aggregated from Depop trending searches, TikTok #OOTD tags, and Pinterest fashion boards (2024–2025). The file simulates data that would be fetched via a live scrape in production.

**Output:** `str` — A 2–3 sentence trend assessment naming specific trending aesthetics the item aligns with and one concrete styling tip. Passed into `suggest_outfit` as `context` so outfit recommendations reflect the current fashion moment. Returns `"Trend data unavailable — styling without trend context."` if the file is missing or the LLM call fails.

**Model:** `llama-3.3-70b-versatile`, temperature 0.5 (lower temperature for more consistent, factual trend analysis).

---

### Style Profile Memory (`utils/profile.py`)

**Purpose:** Persists a user's accumulated style preferences across sessions so the agent learns their tastes over time without re-entry.

**`load_style_profile()` → dict:** Reads `user_profile.json` from the project root. Returns `{"preferred_styles": [], "preferred_size": None, "search_history": []}` if the file doesn't exist — never raises.

**`save_style_profile(session)` → None:** Merges the selected item's style tags into `preferred_styles` (up to 15 unique tags, most recent first), updates `preferred_size` if the session parsed one, and prepends the search description to `search_history` (capped at 5). Silent on write errors.

**How it influences suggestions:** The loaded `preferred_styles` are formatted as `"This user's style history: y2k, vintage, graphic tee, ..."` and appended to the `suggest_outfit` context string alongside the trend report.

---

## Planning Loop

The planning loop is a sequential pipeline with one conditional early exit. Here is the exact decision logic:

**Step 1 — Load style profile.** `load_style_profile()` reads `user_profile.json`. Preferred styles and size from prior sessions are available as context for step 8.

**Step 2 — Parse the query.** Regex extracts three things from the raw user input:
- `max_price`: matched by `r'(?:under|below|less than|up to|max|no more than)\s*\$?(\d+(?:\.\d+)?)'`
- `size`: matched by `r'\bsize\s+([A-Z0-9/]+)'` first; falls back to `r'\b(XXS|XS|S/M|M/L|L/XL|S|M|L|XL|XXL|XXXL)\b'`
- `description`: the original query with matched price and size clauses stripped, lowercased, whitespace-normalized

**Step 3 — Call `search_listings` with retry.** First attempt uses all three parsed parameters.

> **Condition A:** If results are empty and `size` was set → retry without size, store `session["retry_info"]` describing what was loosened.
> **Condition B:** If still empty and `max_price` was set → retry with both filters removed, update `session["retry_info"]`.
> **Condition C:** If still empty after all retries → set `session["error"]` and return immediately. No LLM calls are made.

**Step 4 — Select the top result.** `session["selected_item"] = session["search_results"][0]`.

**Step 5 — Call `compare_price`.** Passes the selected item and the full dataset. No LLM call — pure dataset math. Stores result in `session["price_assessment"]`.

**Step 6 — Call `get_trend_report`.** Passes the selected item. Stores result in `session["trend_report"]`.

**Step 7 — Build outfit context.** Combines the trend report and loaded style profile preferences into a single context string.

**Step 8 — Call `suggest_outfit`.** Passes the selected item, wardrobe, and the combined context string. LLM output is now informed by both trends and the user's style history.

**Step 9 — Call `create_fit_card`.** Passes `session["outfit_suggestion"]` and the selected item.

**Step 10 — Save style profile.** `save_style_profile(session)` persists this session's style tags to `user_profile.json` for the next run.

**Step 11 — Return the session.** `session["error"]` is `None` on success.

The agent doesn't call all tools unconditionally — if step 3 finds nothing after all retries, the loop exits before any LLM calls are made.

---

## State Management

All state lives in a single `session` dict initialized once per interaction by `_new_session()`. No global variables are used. Here is what each key holds and when it's written versus read:

| Key | Written by | Read by |
|-----|-----------|---------|
| `session["query"]` | `_new_session()` at start | Error messages |
| `session["parsed"]` | Regex parsing in `run_agent` | `search_listings`; `save_style_profile` |
| `session["search_results"]` | `search_listings` (after any retries) | Selecting `selected_item` |
| `session["retry_info"]` | Retry logic in `run_agent` | Prepended to listing panel in UI |
| `session["selected_item"]` | `results[0]` after search | `compare_price`, `get_trend_report`, `suggest_outfit`, `create_fit_card` |
| `session["wardrobe"]` | `_new_session()` (passed in by caller) | `suggest_outfit` |
| `session["price_assessment"]` | `compare_price` return value | Displayed in price panel |
| `session["trend_report"]` | `get_trend_report` return value | Built into `outfit_context` for `suggest_outfit` |
| `session["outfit_suggestion"]` | `suggest_outfit` return value | `create_fit_card` |
| `session["fit_card"]` | `create_fit_card` return value | Returned to `app.py` for display |
| `session["error"]` | Set on empty search after all retries | Checked by `app.py` before rendering |

The user never re-enters intermediate values. Style preferences from a previous session flow in at step 1 via `load_style_profile()` and are persisted back at step 10 via `save_style_profile()` — the second run automatically incorporates what was learned from the first.

---

## Error Handling

### `search_listings` — No results match the query (with retry logic)

**What the agent does:** Before setting an error, the agent tries to recover automatically:
1. If `size` was set and results are empty → retry without size, store `session["retry_info"]`
2. If still empty and `max_price` was set → retry with both filters off, update `session["retry_info"]`
3. If still empty → set `session["error"]` and return early

On a successful retry, the listing panel shows a `⚠️` note explaining what was adjusted so the user knows the results are broader than they asked for. If all retries fail, the error message names the original query and tells the user what to adjust.

**Concrete example from testing:**
```bash
python -c "
from agent import run_agent
from utils.data_loader import get_example_wardrobe
s = run_agent('designer ballgown size XXS under \$5', get_example_wardrobe())
print(s['error'])
print('fit_card:', s['fit_card'])
"
```
Output:
```
No listings found matching 'designer ballgown size XXS under $5'. Try different keywords, a different size, or a higher price limit.
fit_card: None
```
The agent names the original query, explains why it failed (all three filters combined left nothing), and tells the user exactly what levers to adjust.

![](https://github.com/hkumar30/ai201-project2-fitfindr-starter/blob/e2f39c2ba8f8cf8668bdfe7404aee323d522686f/images/search_listings_not_found.png)

<center><p> Figure 2. No results found </p></center>

---

### `suggest_outfit` — Wardrobe is empty

**What the agent does:** Detects `wardrobe["items"] == []` and switches to a general-styling prompt instead of a wardrobe-specific one. The LLM is asked what silhouettes, colors, and occasions work well with the new item. Returns a non-empty string — the agent continues to `create_fit_card` normally.

**Concrete example from testing:**
```bash
python -c "
from tools import search_listings, suggest_outfit
from utils.data_loader import get_empty_wardrobe
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(suggest_outfit(results[0], get_empty_wardrobe()))
"
```
Output (summarized): a multi-sentence response about what kinds of bottoms and outerwear pair well with a Y2K butterfly baby tee, what aesthetic it fits, and what occasions it suits — without referencing any wardrobe pieces that don't exist.

![](https://github.com/hkumar30/ai201-project2-fitfindr-starter/blob/e2f39c2ba8f8cf8668bdfe7404aee323d522686f/images/search_listings_empty_wardrobe.png)

<center><p> Figure 3. General Styled Prompt in case of empty wardrobe </p></center>

---

### `compare_price` — Insufficient comparables

**What the agent does:** Returns a plain-English message explaining there aren't enough similar listings to make a price judgment — never raises. The agent continues to `get_trend_report` and `suggest_outfit` normally.

**Concrete example (insufficient comparables):**
```bash
python -c "
from tools import compare_price
from utils.data_loader import load_listings
listings = load_listings()
# Chelsea boots — only 1 comparable shoe shares a style tag; triggers the < 2 comparables path
item = next(l for l in listings if l['id'] == 'lst_028')
print(compare_price(item, listings))
"
```
Output:
```
Not enough comparable listings to assess pricing for Suede Chelsea Boots — Tan. Only 1 similar shoes found in the dataset.
```

**Happy path output (for reference):** When enough comparables exist, the output is three lines — verdict, stats, and reasoning. For example, the velvet blazer (`lst_036`, $52, outerwear, 6 comparables):
```
Price: $52.00 — ABOVE AVERAGE
Comparable outerwear (6 listings): avg $44.50, median $41.00, range $27.00–$75.00
Reasoning: Velvet Blazer — Emerald Green is priced above the $44.50 average for outerwear with similar style tags.
```

---

### `get_trend_report` — Trends file unavailable

**What the agent does:** If `data/trends.json` is missing or the LLM fails, returns `"Trend data unavailable — styling without trend context."` The outfit context passed to `suggest_outfit` simply omits the trend section — the tool doesn't propagate the failure.

---

### `create_fit_card` — Empty outfit string

**What the agent does:** Guards against `outfit == ""` or whitespace-only before making any API call. Returns the string `"Unable to generate fit card: no outfit suggestion was provided."` immediately.

**Concrete example from testing:**
```bash
python -c "
from tools import search_listings, create_fit_card
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(create_fit_card('', results[0]))
"
```
Output:
```
Unable to generate fit card: no outfit suggestion was provided.
```
No API call is made. This means a broken `suggest_outfit` upstream doesn't cause a cascade failure — the agent can still surface the listing and the error message.

![](https://github.com/hkumar30/ai201-project2-fitfindr-starter/blob/e2f39c2ba8f8cf8668bdfe7404aee323d522686f/images/create_fit_card_empty.png)

<center><p> Figure 4. No outfit suggestion provided </p></center>

---

## Spec Reflection

**One way the planning.md spec made the implementation better:**

Writing out the error handling table in `planning.md` before touching `tools.py` forced a concrete decision about what `suggest_outfit` should do when the wardrobe is empty. The options were: raise an exception, return an empty string, or switch prompts. The table format — requiring a specific agent response for each failure mode — made it obvious that "switch prompts" was the right answer, because returning an empty string would just push the failure downstream to `create_fit_card`. That design decision came from the spec, not from coding.

**One divergence from the spec and why:**

The planning.md query parser describes a standalone size token fallback (`\b(XXS|XS|S/M|...)\b`) for queries that don't use the `"size X"` form. In practice, every test query used "size X" format and the fallback was never triggered. More significantly, the standalone pattern has a false-positive risk: a query like "90s look" contains no size, but a query like "looking for an M-style fit" could accidentally match "M". The fallback was kept in the implementation for completeness, but it wasn't validated against a broader range of real queries — the spec assumed it would work correctly without testing it explicitly.

---

## AI Usage

### Instance 1 — Implementing the three tools in `tools.py`

**What I directed the AI to do:** For each tool, I provided the corresponding spec block from `planning.md` — the exact input parameters with types, the return value description, and the failure mode — along with the relevant docstring from `utils/data_loader.py`. I asked Claude to implement one function at a time.

**What it produced:** Complete implementations of `search_listings`, `suggest_outfit`, and `create_fit_card` matching the spec signatures, including the two-path structure in `suggest_outfit` (empty vs. non-empty wardrobe) and the empty-outfit guard in `create_fit_card`.

**What I reviewed and revised:** For `search_listings`, I verified that the scoring logic built a word set from all five fields (title, description, category, style_tags, colors) and that multi-word style tags like `"graphic tee"` were correctly split so individual tokens (`"graphic"`, `"tee"`) could each score. I confirmed the size filter used substring matching so `"M"` correctly matched `"S/M"` and `"M/L"`, as specified. I ran three targeted test cases before accepting the code: `"vintage graphic tee"` under $30 (expected 3+ results with graphic tees at the top), `"track jacket"` size `"M"` (expected lst_004), and `"designer ballgown"` size `"XXS"` under $5 (expected `[]`). All three behaved as the spec predicted.

---

### Instance 2 — Implementing the planning loop in `agent.py`

**What I directed the AI to do:** I provided the Planning Loop section, the State Management table, and the Architecture diagram from `planning.md`, plus the `_new_session()` function and docstring from `agent.py`. I asked Claude to implement `run_agent()` following those inputs exactly.

**What it produced:** The full `run_agent()` implementation with regex query parsing, the `search_listings` early-exit condition, and state flowing through the session dict at each step.

**What I reviewed and revised:** Before running the code, I checked three things against the spec: (1) the early-exit condition used `if not results` rather than `if results is None`, since `search_listings` returns `[]` on failure, not `None`; (2) the regex for standalone size tokens listed `S/M` and `M/L` before `S` and `M` in the alternation, so the longer patterns matched first; (3) `session["selected_item"]` was set to `results[0]` after — not before — the empty check, so it could never be set to an item from an empty list. I then ran `python agent.py` and verified both the happy path (real title, outfit, and fit card printed) and the no-results path (error message only, `fit_card` remained `None`).
