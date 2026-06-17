# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset for items that match a natural-language description, an optional clothing size, and a maximum price. Returns up to 6 ranked results sorted by keyword relevance, then price ascending.

**Input parameters:**
- `description` (str): Natural language description of what the user is looking for — style, category, color, vibe, brand, etc. (e.g. "vintage graphic tee", "rust corduroy pants")
- `size` (str): Clothing size to filter by (e.g. "S", "M", "W30"). Empty string means no size filter.
- `max_price` (float): Maximum price in USD. Use `float('inf')` or a very large number when no budget is given.

**What it returns:**
A list of listing dictionaries (up to 6), each containing: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`. Returns an empty list if no listings match. Returns a dict with an `"error"` key if an exception occurs.

**What happens if it fails or returns nothing:**
- Empty list → agent tells the user no matches were found and suggests broadening the search (e.g., removing size filter, raising price, or using different keywords).
- Error dict → agent surfaces the error message and asks the user to try again.

---

### Tool 2: suggest_outfit

**What it does:**
Uses a Groq LLM call to suggest 2–3 complete outfit combinations built around a specific new item and the user's existing wardrobe. Handles the empty wardrobe case by suggesting general outfit directions instead.

**Input parameters:**
- `new_item` (dict): A listing dict (from `search_listings`) or any wardrobe-item dict with `title`/`name`, `category`, `colors`, and `style_tags` fields.
- `wardrobe` (dict): A wardrobe dict in the standard schema format (`{"items": [...]}`) — may be empty.

**What it returns:**
A dict with an `"outfits"` key containing a list of outfit dicts. Each outfit has: `"name"` (str), `"pieces"` (list[str]), `"vibe"` (str), `"styling_tip"` (str). May also include a `"note"` key when the wardrobe is empty. Returns a dict with an `"error"` key (and an empty `"outfits"` list) if the LLM call or JSON parse fails.

**What happens if it fails or returns nothing:**
- Empty wardrobe → still runs; returns outfit directions for wardrobe-building with a note — does not refuse or return an error.
- LLM / JSON parse error → returns `{"error": "...", "outfits": []}`. Agent tells the user outfit suggestions are unavailable right now and offers to still generate a fit card from a generic description.

---

### Tool 3: create_fit_card

**What it does:**
Uses a Groq LLM call (at high temperature for variety) to generate a short, shareable Instagram-caption-style description of a complete outfit. Output differs for every unique outfit input.

**Input parameters:**
- `outfit` (dict): One outfit dict from `suggest_outfit`'s results — must have `"pieces"`, `"name"`, and `"vibe"` keys; may be partially populated.
- `new_item` (dict): The listing dict for the hero item, used to pull style tags for hashtags and framing.

**What it returns:**
A plain string: 2–4 sentences of caption copy followed by relevant hashtags. If the outfit data is missing or incomplete, returns a reasonable fallback caption string (never raises an exception).

**What happens if it fails or returns nothing:**
- Incomplete `outfit` dict → generates a simpler caption using just the `new_item` name; still returns a valid string.
- LLM exception → returns a hard-coded fallback caption that names the item — agent displays it transparently without crashing.

---

### Additional Tools (if any)

No additional tools beyond the required three.

---

## Planning Loop

**How does your agent decide which tool to call next?**

The planning loop is powered by Groq's function-calling API (LLM-driven tool selection). Here's the logic:

1. **Input:** The user's message is appended to a running `messages` list alongside a system prompt that describes FitFindr's purpose and the session's current state (what's been found and selected so far).

2. **LLM call:** The Groq LLM is invoked with the three tool schemas. It reads the conversation history and current session state summary, then either:
   - Returns a tool call (name + arguments) if more information is needed, or
   - Returns a plain text message when it has enough to respond naturally.

3. **Tool dispatch:** If the LLM requests a tool, the agent executes the corresponding function and injects the result back into `messages` as a tool result. The loop then calls the LLM again.

4. **State awareness:** The agent bridges the gap between what the LLM requests and what the pure tool functions expect. For example, when the LLM calls `suggest_outfit` with an `item_index`, the agent resolves this to `session['search_results'][item_index]` and passes the full item dict + wardrobe to the tool. This means the LLM only needs to remember an index, not re-specify the item.

5. **Termination:** The loop exits when the LLM returns a message with no tool calls. That message is the final response shown to the user.

6. **Safety limit:** The loop caps at 8 iterations to prevent runaway calls. If the cap is hit, the agent returns what it has so far.

The loop is **reactive, not fixed-sequence** — if the user immediately says "just give me a fit card," the LLM can skip directly to `create_fit_card` using data already in state. If the user changes their search mid-conversation, the LLM re-invokes `search_listings` with new parameters.

---

## State Management

**How does information from one tool get passed to the next?**

Each conversation session has a `session_state` dict with these keys:

| Key | Type | Set by | Used by |
|-----|------|--------|---------|
| `search_results` | `list[dict]` | `search_listings` | `suggest_outfit` (item lookup by index) |
| `selected_item` | `dict` | Agent (from search results) | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | `dict` | Initialized at session start | `suggest_outfit` |
| `outfit_suggestions` | `dict` | `suggest_outfit` | `create_fit_card` (outfit lookup by index) |
| `last_fit_card` | `str` | `create_fit_card` | Displayed to user, optionally re-shown |

The `session_state` dict is passed into every `run_turn()` call and mutated in place. Because it persists for the lifetime of the Gradio session, tool results from turn 1 are still available in turn 5 without the user re-entering anything.

A summary of the current state (e.g., "You've found 4 listings. Selected item: Vintage Levi's 501 Jeans.") is injected into the system prompt on every turn so the LLM always knows what's already been done.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| `search_listings` | No listings match the filters | Returns empty list `[]`; agent tells user "No matches found" and suggests relaxing the size or price constraints, or rephrasing the description |
| `search_listings` | File read error or exception | Returns `{"error": "..."}` dict; agent surfaces the message and invites the user to try again |
| `suggest_outfit` | Wardrobe is empty | Runs anyway; returns outfit directions for wardrobe-building with a note — does not refuse or return an error |
| `suggest_outfit` | LLM call fails or JSON parse error | Returns `{"error": "...", "outfits": []}`; agent tells user outfit suggestions are unavailable and offers to generate a fit card with a generic outfit description |
| `create_fit_card` | `outfit` dict is empty or missing keys | Generates a fallback caption using just the item name — never raises, always returns a string |
| `create_fit_card` | LLM call raises an exception | Returns a hard-coded fallback string naming the item; displayed to user as the fit card |

---

## Architecture

```
User Input (Gradio chat)
        │
        ▼
┌───────────────────────────────────────────────────────┐
│                   run_turn()                          │
│                                                       │
│  messages list + session_state summary                │
│        │                                              │
│        ▼                                              │
│  ┌─────────────┐                                      │
│  │  Groq LLM   │ ◄── Tool schemas (3 tools)           │
│  │ (llama-3.3) │                                      │
│  └──────┬──────┘                                      │
│         │                                             │
│    tool_call?                                         │
│    ┌────┴────────────────────────┐                    │
│    │ YES                         │ NO                 │
│    ▼                             ▼                    │
│  dispatch tool              Return text to user       │
│  ┌──────────────────────────┐                         │
│  │ search_listings()        │                         │
│  │   → updates search_results in state                │
│  │                          │                         │
│  │ suggest_outfit()         │                         │
│  │   → resolves item from state                       │
│  │   → updates outfit_suggestions in state            │
│  │                          │                         │
│  │ create_fit_card()        │                         │
│  │   → resolves outfit from state                     │
│  │   → updates last_fit_card in state                 │
│  └──────────────────────────┘                         │
│         │                                             │
│    inject tool result into messages                   │
│         │                                             │
│    loop back to Groq LLM  ◄──────────────────────────┘
│    (max 8 iterations)                                 │
└───────────────────────────────────────────────────────┘
        │
        ▼
  Response shown in Gradio

Error paths:
  search returns [] ──► LLM tells user, suggests broadening query
  search returns error ──► LLM surfaces message, asks to retry
  suggest_outfit error ──► LLM offers fit card with generic description
  create_fit_card error ──► fallback string returned, session continues
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

- **Tool used:** Claude (Cowork mode)
- **Input given:** The Tool 1/2/3 spec sections above (parameter names, types, return values, failure modes) + the `data_loader.py` utility functions showing how to load listings and wardrobes.
- **Expected output:** A `tools.py` file implementing all three functions with exact matching signatures, keyword-scoring search logic for `search_listings`, Groq LLM calls with `response_format={"type": "json_object"}` for `suggest_outfit`, and plain-text LLM call at temperature=0.9 for `create_fit_card`.
- **Verification plan:** Import `tools.py` in a Python REPL; call `search_listings("vintage graphic tee", "", 30)` and confirm it returns a non-empty list of listing dicts with the right keys. Call `search_listings("xyzzy impossible", "XS", 0.01)` and confirm it returns `[]`. Verify all three function signatures match this spec exactly using `inspect.signature()`.

**Milestone 4 — Planning loop and state management:**

- **Tool used:** Claude (Cowork mode)
- **Input given:** The Planning Loop and State Management sections above + the `tools.py` signatures + the architecture ASCII diagram above.
- **Expected output:** An `agent.py` with `run_turn(user_message, messages, session_state, groq_client)` that runs the Groq function-calling loop, dispatches to the three tools using the state-bridging pattern described, updates `session_state` after each tool call, and returns the final assistant text.
- **Verification plan:** Write a `test_agent.py` that mocks the Groq client and calls `run_turn()` three times in sequence (search → suggest → fit card), printing `session_state` after each call to confirm state flows correctly.

---

## A Complete Interaction (Step by Step)

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
The agent receives the user query. The LLM reads the message and identifies: (1) the user wants to search, (2) style="vintage graphic tee", (3) max_price=30, (4) no size specified. The LLM calls `search_listings` with `description="vintage graphic tee"`, `size=""`, `max_price=30.0`.

`search_listings` tokenizes the description, scores each listing by keyword overlap against title + description + style_tags + colors, filters to price ≤ $30, and returns the top matches — e.g., `lst_006` ("Graphic Tee — 2003 Tour Bootleg Style", $24, black, grunge/vintage/streetwear) and `lst_002` ("Y2K Baby Tee — Butterfly Print", $18, white/pink/purple, y2k/vintage). The results are stored in `session_state['search_results']`.

**Step 2:**
The agent injects the search results as a tool result and loops back to the LLM. The LLM sees results and also sees that the user asked *how to style it* — so it immediately calls `suggest_outfit` with `item_index=0`. The agent resolves this: it pulls `session_state['search_results'][0]` (`lst_006`) as `new_item` and passes the example wardrobe (baggy dark-wash jeans, white tank, black combat boots, chunky sneakers, black crossbody bag) as `wardrobe`. `suggest_outfit` calls the Groq LLM and returns 2 outfits:
- "Off-Duty Grunge": Graphic tee + baggy dark-wash jeans + black combat boots + black crossbody. Vibe: "grungy-cool without trying."
- "Streetwear Sunday": Graphic tee + baggy jeans + chunky white sneakers + black zip hoodie tied at the waist. Vibe: "effortlessly streetwear."

Results stored in `session_state['outfit_suggestions']` and `session_state['selected_item']`.

**Step 3:**
The LLM now has search results and outfit suggestions. Because the user asked for a complete styling walkthrough, the LLM calls `create_fit_card` with `outfit_index=0`. The agent resolves this to the first outfit dict and passes it with `new_item=lst_006`. `create_fit_card` prompts Groq at temperature=0.9 and returns a caption. Result stored in `session_state['last_fit_card']`.

**Final output to user:**
The LLM composes a final reply presenting the top search results with prices and platforms, both outfit suggestions with their pieces and vibes, and the fit card caption. For example:

> "Found some great options under $30! Top pick: **Graphic Tee — 2003 Tour Bootleg Style** ($24 on Depop) — boxy black tee with worn-in vintage energy. There's also a **Y2K Butterfly Baby Tee** ($18) if you want something more colorful.
>
> Here's how I'd wear the graphic tee with what you have:
> - **Off-Duty Grunge:** Tee + baggy dark-wash jeans + black combat boots + black crossbody. *Grungy-cool without trying.*
> - **Streetwear Sunday:** Tee + baggy jeans + chunky white sneakers + black zip hoodie at the waist. *Effortlessly streetwear.*
>
> **✨ Fit Card:**
> Band tees found at 2am on depop hit different when styled right. Boxy graphic over high-rise baggies, laced up in combats — this is the fit for doing nothing with intention. Thrifted and undefeated. #graphictee #vintage #grunge #streetwear #thrifted #depop"
