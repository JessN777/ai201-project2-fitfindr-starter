"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Planning loop design:
  1. Parse the query (LLM extracts description, size, max_price)
  2. search_listings() → if empty, retry without size filter → if still empty, abort
  3. select top result → store in session
  4. suggest_outfit() with selected item + wardrobe
  5. create_fit_card() with outfit string + selected item
  6. Return completed session

State flows through the session dict. Each step reads from and writes to
session, so no tool needs to re-receive data already captured upstream.

Usage:
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import json
import os
import re

from dotenv import load_dotenv
from groq import Groq

from tools import search_listings, suggest_outfit, create_fit_card

load_dotenv()


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── query parsing ─────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Extract structured search parameters from a natural language query.

    Uses the Groq LLM as the primary parser (handles varied phrasing well),
    with a regex fallback in case the API call fails.

    Returns a dict with keys: description (str), size (str|None), max_price (float|None).
    """
    # --- Primary: LLM-powered parsing ---
    try:
        api_key = os.environ.get("GROQ_API_KEY")
        if api_key:
            client = Groq(api_key=api_key)
            prompt = f"""Extract search parameters from this clothing query. Return JSON only.

Query: "{query}"

Return exactly this JSON structure:
{{
  "description": "keywords describing style, type, color, vibe — no size or price",
  "size": "size string if mentioned (e.g. S, M, L, XS, W30, size 8) or null",
  "max_price": number if a budget or price limit is mentioned, or null
}}

Examples:
  "vintage graphic tee under $30 size M" → {{"description": "vintage graphic tee", "size": "M", "max_price": 30}}
  "flowy midi skirt" → {{"description": "flowy midi skirt", "size": null, "max_price": null}}
  "90s track jacket around $45" → {{"description": "90s track jacket", "size": null, "max_price": 45}}"""

            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            parsed = json.loads(response.choices[0].message.content)
            return {
                "description": parsed.get("description", query),
                "size": parsed.get("size") or None,
                "max_price": parsed.get("max_price") or None,
            }
    except Exception:
        pass  # Fall through to regex fallback

    # --- Fallback: regex parsing ---
    price_match = re.search(r"\$?(\d+(?:\.\d+)?)\s*(?:dollars?|usd)?", query, re.I)
    size_match = re.search(
        r"\b(xs|s|m|l|xl|xxl|one size|W\d{2}|size\s*\d+)\b", query, re.I
    )
    # Strip price/size fragments to form the description
    description = re.sub(r"\$?\d+(?:\.\d+)?", "", query)
    description = re.sub(r"\b(xs|s|m|l|xl|xxl|one size|W\d{2}|size\s*\d+)\b", "", description, flags=re.I)
    description = re.sub(r"\b(under|below|around|less than|up to|max)\b", "", description, flags=re.I)
    description = " ".join(description.split())

    return {
        "description": description or query,
        "size": size_match.group(1) if size_match else None,
        "max_price": float(price_match.group(1)) if price_match else None,
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Planning loop logic:
      - Each step reads upstream state from session and writes its result back.
      - The loop is adaptive: if search returns nothing with a size filter,
        it retries without the size constraint before giving up.
      - If any step produces empty/error output, the loop sets session["error"]
        and returns early rather than passing bad data downstream.

    Args:
        query:    Natural language user request
        wardrobe: User's wardrobe dict (from get_example_wardrobe() or get_empty_wardrobe())

    Returns:
        The completed session dict. Check session["error"] first — if it is not
        None, the interaction ended early and outfit_suggestion / fit_card are None.
    """
    # ── Step 1: Initialise session ────────────────────────────────────────────
    session = _new_session(query, wardrobe)

    # ── Step 2: Parse query → extract description, size, max_price ───────────
    parsed = _parse_query(query)
    session["parsed"] = parsed
    description = parsed["description"]
    size = parsed["size"]
    max_price = parsed["max_price"]

    # ── Step 3: Search listings ───────────────────────────────────────────────
    results = search_listings(description, size, max_price)
    session["search_results"] = results

    # Planning decision: if no results with size filter, retry without size
    if not results and size:
        results = search_listings(description, None, max_price)
        session["search_results"] = results
        if results:
            # Note the relaxation so the UI can surface it
            session["parsed"]["size_relaxed"] = True

    # Planning decision: if still no results, abort with a helpful message
    if not results:
        parts = ["No listings matched your search."]
        if size:
            parts.append(f"Try removing the size filter (searched for '{size}').")
        if max_price:
            parts.append(f"Or raise your budget above ${max_price:.0f}.")
        parts.append("You can also try different keywords.")
        session["error"] = " ".join(parts)
        return session

    # ── Step 4: Select item — take the top-ranked result ─────────────────────
    selected_item = results[0]
    session["selected_item"] = selected_item   # state carried forward

    # ── Step 5: Suggest outfit using selected item + wardrobe ─────────────────
    outfit_suggestion = suggest_outfit(selected_item, wardrobe)
    session["outfit_suggestion"] = outfit_suggestion  # state carried forward

    # Planning decision: if suggest_outfit returned empty (shouldn't happen, but guard anyway)
    if not outfit_suggestion or not outfit_suggestion.strip():
        session["outfit_suggestion"] = (
            f"Style {selected_item['title']} with complementary basics in "
            f"{', '.join(selected_item.get('colors', ['neutral']))} tones."
        )

    # ── Step 6: Create fit card using outfit string + selected item ───────────
    fit_card = create_fit_card(session["outfit_suggestion"], selected_item)
    session["fit_card"] = fit_card

    # ── Step 7: Return completed session ─────────────────────────────────────
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
