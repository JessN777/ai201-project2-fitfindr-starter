# FitFindr — Starter Kit

This starter kit contains everything you need to begin Project 2.

## What's Included

```
ai201-project2-fitfindr-starter/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example wardrobe
├── utils/
│   └── data_loader.py         # Helper functions for loading the data
├── planning.md                # Your planning template — fill this out first
└── requirements.txt           # Python dependencies
```

## Setup

**macOS / Linux:**
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows:**
```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file (get a free key at [console.groq.com](https://console.groq.com)):
```
GROQ_API_KEY=your_key_here
```

## The Mock Listings Dataset

`data/listings.json` contains 40 mock secondhand listings across categories (tops, bottoms, outerwear, shoes, accessories) and styles (vintage, y2k, grunge, cottagecore, streetwear, and more).

Each listing has: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, and `platform`.

Load it with:
```python
from utils.data_loader import load_listings
listings = load_listings()
```

## The Wardrobe Schema

`data/wardrobe_schema.json` defines the format your agent uses to represent a user's existing wardrobe. It includes:

- `schema`: field definitions for a wardrobe item
- `example_wardrobe`: a sample wardrobe with 10 items you can use for testing
- `empty_wardrobe`: a starting template for a new user

Load an example wardrobe with:
```python
from utils.data_loader import get_example_wardrobe
wardrobe = get_example_wardrobe()
```

## Tool Inventory

Each tool's name, signature, and return value are documented below. These exactly match the function signatures in `tools.py`.

### `search_listings(description, size, max_price)`

| Parameter | Type | Description |
|-----------|------|-------------|
| `description` | `str` | Natural language description of what the user wants (style, category, colors, vibe) |
| `size` | `str \| None` | Clothing size to filter by (e.g. `"M"`, `"W30"`). `None` skips size filtering. |
| `max_price` | `float \| None` | Maximum price in USD (inclusive). `None` skips price filtering. |

**Returns:** `list[dict]` — up to 6 matching listing dicts sorted by relevance then price ascending. Returns `[]` if no matches; never raises an exception.

---

### `suggest_outfit(new_item, wardrobe)`

| Parameter | Type | Description |
|-----------|------|-------------|
| `new_item` | `dict` | A listing dict (from `search_listings`) — must have `title`, `category`, `colors`, `style_tags` |
| `wardrobe` | `dict` | Wardrobe dict with an `"items"` key (list of wardrobe item dicts). May be empty. |

**Returns:** `str` — a multi-paragraph string with 2 outfit suggestions and styling tips. Returns a fallback advice string if the LLM call fails; never raises.

---

### `create_fit_card(outfit, new_item)`

| Parameter | Type | Description |
|-----------|------|-------------|
| `outfit` | `str` | The outfit suggestion string from `suggest_outfit()` |
| `new_item` | `dict` | The listing dict for the hero item (for name, price, platform, style tags) |

**Returns:** `str` — a 2–4 sentence Instagram-caption-style string followed by hashtags. Returns a fallback caption string if `outfit` is empty or the LLM fails; never raises.

---

## Interaction Walkthrough

**User query:** `"vintage graphic tee under $30"`

**Step 1 — Tool called: `_parse_query` (internal, called by agent)**
- Input: `"vintage graphic tee under $30"`
- Why: The planning loop always starts by extracting structured parameters from the raw query before calling any tool. The LLM parser identifies the description, any size mention, and any price limit.
- Output: `{"description": "vintage graphic tee", "size": None, "max_price": 30.0}`

**Step 2 — Tool called: `search_listings`**
- Input: `description="vintage graphic tee"`, `size=None`, `max_price=30.0`
- Why: We now have structured search parameters. The agent calls `search_listings` to find matching items in the dataset, filtered to budget.
- Output: A list of 3 matching listings, top result being `lst_006` — "Graphic Tee — 2003 Tour Bootleg Style" ($24, black, grunge/vintage/streetwear tags, Depop). This is stored in `session["search_results"]` and the top item goes into `session["selected_item"]`.

**Step 3 — Tool called: `suggest_outfit`**
- Input: `new_item=lst_006` (from `session["selected_item"]`), `wardrobe=example_wardrobe` (from `session["wardrobe"]`)
- Why: The search returned results, so the agent proceeds. It passes the top item and the user's wardrobe to `suggest_outfit` to get specific, wardrobe-aware outfit suggestions. The selected item flows from step 2 via session state — the user didn't re-enter it.
- Output: A formatted string with two outfit ideas. Example — "**Off-Duty Grunge:** Graphic Tee + Baggy straight-leg jeans (dark wash) + Black combat boots + Black crossbody bag. *Grungy-cool without trying.* Tip: Leave the tee untucked and slightly cropped over the waistband." Stored in `session["outfit_suggestion"]`.

**Step 4 — Tool called: `create_fit_card`**
- Input: `outfit=session["outfit_suggestion"]` (the string from step 3), `new_item=lst_006` (from `session["selected_item"]`)
- Why: All three required tools must run in sequence to complete the multi-step workflow. The outfit string from step 3 flows into this call via session state. `create_fit_card` generates a shareable caption that captures the look's aesthetic.
- Output: `"Band tees found at 2am on depop hit different when paired right. Boxy graphic over high-rise baggies, laced up in combat boots — this is the fit for doing nothing with intention. Thrifted and undefeated. ✨ #graphictee #vintage #grunge #streetwear #thrifted #depop"`. Stored in `session["fit_card"]`.

**Final output to user:**

The Gradio UI displays three panels:
- **🛍️ Top listing found:** Formatted card with item name, price ($24.00), platform (Depop), size, condition, colors, style tags, and description.
- **👗 Outfit idea:** The two outfit suggestions from `suggest_outfit`, formatted as paragraph text with headers and styling tips.
- **✨ Your fit card:** The Instagram-caption string from `create_fit_card`, ready to copy-paste.

---

## Error Handling and Fail Points

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| `search_listings` | No listings match (returns `[]`) | Planning loop checks for empty results; if size was specified, retries without size filter. If still empty, sets `session["error"]` to a helpful message ("No listings matched. Try removing the size filter or raising your budget.") and returns early — `suggest_outfit` and `create_fit_card` are never called with empty input. |
| `search_listings` | File read exception | `try/except` in the tool catches it, logs the error, and returns `[]`. The planning loop then handles the empty list as above. |
| `suggest_outfit` | LLM API call fails (network error, rate limit, etc.) | `try/except` in the tool catches the exception and returns a fallback string: "Outfit suggestions are temporarily unavailable. Try pairing [item] with neutral basics in [colors]." The agent continues to `create_fit_card` with this fallback string — the session doesn't abort. |
| `suggest_outfit` | Wardrobe is empty | Tool detects `wardrobe["items"] == []` and switches to a different LLM prompt that gives general styling directions instead of specific outfit combos. Returns a non-empty string; the agent proceeds normally. |
| `create_fit_card` | `outfit` string is empty or whitespace | Tool guards at the top of the function and immediately returns a simple fallback caption using the item name, price, and platform — no LLM call attempted. |
| `create_fit_card` | LLM call raises an exception | `try/except` catches it, logs it, and returns a hard-coded fallback caption string. The agent always has something to display. |

---

## Spec Reflection

**One way planning.md helped during implementation:**

Writing out the state management table in planning.md before writing any code made the implementation of `run_agent()` much cleaner. Because I had already specified exactly what each key in the session dict would hold and which step set it, writing the step-by-step planning loop in `agent.py` was almost mechanical — I just translated the table into code. Without that upfront design, I would likely have passed items between tools as function arguments and realized mid-way that I needed a shared dict to hold intermediate results.

**One divergence from your spec, and why:**

The spec in planning.md described an LLM-driven Groq function-calling loop (where the LLM decides which tool to call next via tool-use API). The actual implementation uses a sequential pipeline in `run_agent()` with the LLM only invoked for query parsing. This divergence happened because the starter `agent.py` scaffold already defined `run_agent(query, wardrobe) -> dict` with a clear step-by-step TODO — a session-dict pipeline was a better fit for that interface than a conversational tool-calling loop. The "planning" aspect is preserved through conditional branching (retry without size filter, abort on no results) rather than LLM-selected tool ordering.

---

## AI Usage

This project was implemented with Claude (Cowork mode) as the primary AI tool.

### Instance 1 — Implementing `search_listings`

**Input given to Claude:** The Tool 1 spec block from `planning.md` (parameter names, types, return value description, failure mode) plus the `load_listings()` function from `utils/data_loader.py`.

**What it produced:** A complete `search_listings` implementation with keyword tokenization, stop-word filtering, scoring across all listing fields (title, description, category, style_tags, colors, brand), and price/size filtering. Results sorted by score descending then price ascending, capped at 6.

**What I changed:** The initial generated version didn't handle the "one size" edge case — it would filter out "One Size / Oversized" listings when a size like "M" was specified, even though those items fit anyone. I added the `is_one_size` check explicitly. I also tightened the stop-word list after noticing that short words like "be" and "has" were being included in keyword scoring and inflating match counts on irrelevant listings.

---

### Instance 2 — Implementing `agent.py` planning loop

**Input given to Claude:** The Planning Loop section, State Management table, and ASCII architecture diagram from `planning.md`, plus the `run_agent()` function stub from `agent.py` (which defined the session dict structure and numbered the TODO steps).

**What it produced:** A `run_agent()` implementation with LLM-powered query parsing (`_parse_query` using Groq), sequential tool calls with session dict state, and a regex fallback parser for when the API is unavailable.

**What I changed:** The generated planning loop called `search_listings` once and returned immediately on empty results. I added the adaptive retry — if search returns `[]` and a size filter was used, the agent automatically retries without the size constraint before giving up. This matches the "reactive, not fixed-sequence" description in `planning.md` and makes the agent visibly smarter when a user's size is just not in stock. I also added the `session["parsed"]["size_relaxed"]` flag so `app.py` can surface a note to the user about the relaxed filter.

---

## Where to Start

1. **Read `planning.md` and fill it out before writing any code.**
2. Verify the data loads correctly by running `python utils/data_loader.py`.
3. Build and test each tool individually before connecting them through your planning loop.
4. Run non-integration tests with `pytest tests/ -m "not integration"` (requires `pip install pytest`).
5. Run integration tests (requires `GROQ_API_KEY` in `.env`): `pytest tests/`.

Your implementation files go in this same directory. There's no required file structure for your agent code — organize it however makes sense for your design.
