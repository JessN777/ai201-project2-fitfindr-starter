"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform
    """
    try:
        listings = load_listings()

        # --- Tokenise description into meaningful keywords ---
        raw_tokens = re.findall(r"[a-z0-9]+", description.lower())
        _stop = {
            "a", "an", "the", "and", "or", "for", "in", "on", "at", "with",
            "i", "me", "my", "want", "looking", "find", "get", "some", "any",
            "is", "are", "was", "be", "have", "has", "do", "does", "can",
            "under", "below", "around", "about", "like", "something", "need",
        }
        keywords = [t for t in raw_tokens if t not in _stop and len(t) > 2]

        results = []
        for listing in listings:

            # --- Price filter ---
            if max_price is not None and listing.get("price", 0) > max_price:
                continue

            # --- Size filter (flexible: "M" matches "S/M", "One Size" always passes) ---
            if size:
                listing_size = listing.get("size", "").lower()
                size_lower = size.lower()
                is_one_size = "one size" in listing_size or listing_size == "os"
                if not is_one_size and size_lower not in listing_size:
                    continue

            # --- Keyword scoring ---
            searchable = " ".join([
                listing.get("title", ""),
                listing.get("description", ""),
                listing.get("category", ""),
                " ".join(listing.get("style_tags", [])),
                " ".join(listing.get("colors", [])),
                listing.get("brand", "") or "",
            ]).lower()

            score = sum(1 for kw in keywords if kw in searchable)

            # Keep only listings with at least one keyword match
            # (if no keywords were extracted, keep all price/size-filtered results)
            if score > 0 or not keywords:
                results.append({**listing, "_score": score})

        # Sort: highest score first, then cheapest first as tiebreaker
        results.sort(key=lambda x: (-x["_score"], x.get("price", 0)))

        # Strip internal field before returning
        return [{k: v for k, v in r.items() if k != "_score"} for r in results[:6]]

    except Exception as exc:
        # Tool-level error handling: never crash the agent
        print(f"[search_listings ERROR] {exc}")
        return []


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, returns general styling advice for the item.
        Returns a fallback error string if the LLM call fails — never raises.
    """
    item_name = new_item.get("title") or new_item.get("name") or "Unknown item"
    item_category = new_item.get("category", "unknown")
    item_colors = ", ".join(new_item.get("colors", [])) or "unspecified"
    item_tags = ", ".join(new_item.get("style_tags", [])) or "unspecified"
    item_desc = new_item.get("description", "")

    wardrobe_items = wardrobe.get("items", [])

    try:
        client = _get_groq_client()

        if not wardrobe_items:
            # Empty wardrobe: give general styling directions
            prompt = f"""You are a fashion stylist. A user found this secondhand piece but has an empty wardrobe:

Item: {item_name}
Category: {item_category}
Colors: {item_colors}
Style tags: {item_tags}

Suggest 2 outfit directions they could build around this piece. For each:
- Give the outfit a short evocative name
- List 3–4 types of basics they would need (keep it general, no specific brands)
- Describe the vibe in one sentence
- Give one practical styling tip

Keep the tone casual and encouraging. Format clearly with headers for each outfit."""

        else:
            wardrobe_text = "\n".join(
                f"- {item['name']} ({item['category']}, "
                f"colors: {', '.join(item.get('colors', []))}, "
                f"tags: {', '.join(item.get('style_tags', []))})"
                + (f" — {item['notes']}" if item.get("notes") else "")
                for item in wardrobe_items
            )

            prompt = f"""You are a fashion stylist helping someone style a new secondhand find.

New item:
  Name: {item_name}
  Category: {item_category}
  Colors: {item_colors}
  Style tags: {item_tags}
  Description: {item_desc}

User's existing wardrobe:
{wardrobe_text}

Suggest 2 complete, cohesive outfits using the new item plus specific pieces from their wardrobe.
For each outfit:
- Give it a short evocative name
- List every piece in the look (new item + wardrobe pieces by name)
- Describe the vibe in one sentence
- Give one practical styling tip (tuck, layer, accessorize, etc.)

Keep the tone casual and specific. Format clearly with headers for each outfit."""

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )

        result = response.choices[0].message.content.strip()
        return result if result else "No outfit suggestions could be generated."

    except Exception as exc:
        # Tool-level error handling: return informative string, never crash
        return (
            f"Outfit suggestions are temporarily unavailable ({exc}). "
            f"Try pairing {item_name} with neutral basics in complementary colors ({item_colors})."
        )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption, followed
        by relevant hashtags. Returns a fallback caption string if outfit is
        empty or the LLM call fails — never raises an exception.
    """
    item_name = new_item.get("title") or new_item.get("name") or "this find"
    price = new_item.get("price")
    platform = new_item.get("platform", "")
    style_tags = new_item.get("style_tags", [])

    # Build hashtag string from style tags + platform
    hashtags = " ".join(f"#{t.replace(' ', '')}" for t in style_tags[:4])
    if platform:
        hashtags += f" #thrifted #{platform}"

    # --- Guard: empty outfit string ---
    if not outfit or not outfit.strip():
        return (
            f"outfit check: {item_name}"
            + (f" — ${price:.0f} on {platform}" if price and platform else "")
            + f". thrift game strong. 🤌 {hashtags}"
        )

    try:
        client = _get_groq_client()

        price_str = f"${price:.0f}" if price else "a steal"
        platform_str = f"on {platform}" if platform else "secondhand"

        prompt = f"""Write a short Instagram caption (2–4 sentences) for this OOTD.

Hero piece: {item_name} ({price_str} {platform_str})
Full outfit breakdown:
{outfit[:600]}

Caption rules:
- Sound like a real person posting an OOTD, not a product description
- Mention the item name and price/platform naturally, once each
- Capture the specific vibe of this look (avoid generic phrases like "love this outfit!")
- End with these hashtags on their own line: {hashtags}
- Maximum 4 sentences before the hashtags
- Do NOT wrap in quotes

Output only the caption."""

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,   # higher = more varied captions
        )

        caption = response.choices[0].message.content.strip().strip('"').strip("'")
        return caption if caption else f"found {item_name} {platform_str} and it's everything. {hashtags}"

    except Exception as exc:
        # Tool-level fallback: always return a usable string
        print(f"[create_fit_card ERROR] {exc}")
        return (
            f"can't stop thinking about this {item_name} find. "
            f"thrift smarter, not harder. {hashtags}"
        )
