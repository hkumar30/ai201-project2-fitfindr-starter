# FitFindr

FitFindr is a multi-tool AI agent that helps users find secondhand clothing and figure out how to wear it. You describe what you're looking for in natural language, and the agent searches a dataset of mock thrift listings, uses an LLM to suggest outfit combinations from your existing wardrobe, and generates a shareable OOTD caption — all in a single interaction.

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

### `suggest_outfit(new_item, wardrobe)`

**Purpose:** Given a thrifted item the user is considering buying and their existing wardrobe, uses an LLM to suggest 1–2 complete outfit combinations.

**Inputs:**
- `new_item` (dict) — A listing dict returned by `search_listings`. The prompt uses `title`, `description`, `style_tags`, `colors`, `price`, and `platform`.
- `wardrobe` (dict) — A wardrobe dict with an `"items"` key containing a list of wardrobe item dicts, each with `name`, `category`, `colors`, `style_tags`, and optional `notes`. Accepts an empty wardrobe (`{"items": []}`) — handled explicitly without raising.

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

## Planning Loop

The planning loop is a sequential pipeline with one conditional early exit. Here is the exact decision logic:

**Step 1 — Parse the query.** Regex extracts three things from the raw user input:
- `max_price`: matched by `r'(?:under|below|less than|up to|max|no more than)\s*\$?(\d+(?:\.\d+)?)'`
- `size`: matched by `r'\bsize\s+([A-Z0-9/]+)'` first; falls back to a bare token pattern `r'\b(XXS|XS|S/M|M/L|L/XL|S|M|L|XL|XXL|XXXL)\b'` if "size X" form isn't found
- `description`: the original query with the matched price and size clauses stripped out, then lowercased and whitespace-normalized

**Step 2 — Call `search_listings`.** The parsed description, size, and max_price are passed in. This step always runs.

> **Condition:** If `search_listings` returns an empty list, the agent sets `session["error"]` to a specific message and returns the session immediately. `suggest_outfit` and `create_fit_card` are never called with empty input. This is the only branch in the loop.

**Step 3 — Select the top result.** `session["selected_item"] = session["search_results"][0]`. The top result is the highest-scoring item from step 2; ties preserve original dataset order.

**Step 4 — Call `suggest_outfit`.** Passes `session["selected_item"]` and `session["wardrobe"]` directly — no re-entry by the user.

**Step 5 — Call `create_fit_card`.** Passes `session["outfit_suggestion"]` and `session["selected_item"]` directly.

**Step 6 — Return the session.** `session["error"]` is `None` on success.

The agent doesn't call all three tools unconditionally. If step 2 produces nothing, the loop terminates before any LLM calls are made.

---

## State Management

All state lives in a single `session` dict initialized once per interaction by `_new_session()`. No global variables are used. Here is what each key holds and when it's written versus read:

| Key | Written by | Read by |
|-----|-----------|---------|
| `session["query"]` | `_new_session()` at start | Error messages |
| `session["parsed"]` | Regex parsing in `run_agent` | `search_listings` call |
| `session["search_results"]` | `search_listings` return value | Selecting `selected_item` |
| `session["selected_item"]` | `results[0]` after search | `suggest_outfit`, `create_fit_card` |
| `session["wardrobe"]` | `_new_session()` (passed in by caller) | `suggest_outfit` |
| `session["outfit_suggestion"]` | `suggest_outfit` return value | `create_fit_card` |
| `session["fit_card"]` | `create_fit_card` return value | Returned to `app.py` for display |
| `session["error"]` | Set on empty search results | Checked by `app.py` before rendering |

The user never re-enters intermediate values. The item found in step 2 is the exact same dict object that flows into steps 4 and 5. Confirming this is straightforward: `print(session["selected_item"])` at the end of a run shows the same record that appeared at the top of `session["search_results"]`.

---

## Error Handling

### `search_listings` — No results match the query

**What the agent does:** Sets `session["error"]` to `f"No listings found matching '{query}'. Try different keywords, a different size, or a higher price limit."` and returns the session immediately. `suggest_outfit` and `create_fit_card` are skipped entirely.

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
