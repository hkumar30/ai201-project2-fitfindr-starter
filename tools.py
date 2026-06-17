"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os

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

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()

    # Step 1: filter by max_price (inclusive)
    if max_price is not None:
        listings = [item for item in listings if item["price"] <= max_price]

    # Step 2: filter by size (case-insensitive substring)
    if size is not None:
        listings = [
            item for item in listings
            if size.lower() in item["size"].lower()
        ]

    # Step 3: score by keyword overlap with description
    tokens = description.lower().split()

    def score_listing(item: dict) -> int:
        searchable_words = set(
            " ".join([
                item["title"],
                item["description"],
                item["category"],
                " ".join(item["style_tags"]),
                " ".join(item["colors"]),
            ]).lower().split()
        )
        return sum(1 for token in tokens if token in searchable_words)

    scored = [(item, score_listing(item)) for item in listings]

    # Step 4: drop zero-score listings
    scored = [(item, s) for item, s in scored if s > 0]

    # Step 5: sort by score descending (stable sort preserves dataset order on ties)
    scored.sort(key=lambda x: x[1], reverse=True)

    return [item for item, _ in scored]


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
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    client = _get_groq_client()

    item_summary = (
        f"Item: {new_item['title']}\n"
        f"Description: {new_item['description']}\n"
        f"Style tags: {', '.join(new_item['style_tags'])}\n"
        f"Colors: {', '.join(new_item['colors'])}\n"
        f"Price: ${new_item['price']}\n"
        f"Platform: {new_item['platform']}"
    )

    if not wardrobe.get("items"):
        # Empty wardrobe path: general styling advice
        prompt = (
            f"A user is considering buying this secondhand item:\n{item_summary}\n\n"
            "They don't have a saved wardrobe yet. Suggest general styling ideas: "
            "what kinds of pieces pair well with this item (be specific about "
            "silhouettes, colors, and fabrics), what aesthetic it fits, and what "
            "occasions it works for. Be concrete — avoid generic advice."
        )
    else:
        # Non-empty wardrobe path: reference specific pieces by name
        wardrobe_lines = []
        for w_item in wardrobe["items"]:
            line = f"- {w_item['name']} ({w_item['category']}, {', '.join(w_item['colors'])}, tags: {', '.join(w_item['style_tags'])})"
            if w_item.get("notes"):
                line += f" — {w_item['notes']}"
            wardrobe_lines.append(line)
        wardrobe_text = "\n".join(wardrobe_lines)

        prompt = (
            f"A user just found this secondhand item:\n{item_summary}\n\n"
            f"Their existing wardrobe includes:\n{wardrobe_text}\n\n"
            "Suggest 1–2 complete outfit combinations using the new item with specific "
            "named pieces from their wardrobe. Reference each wardrobe piece by its name. "
            "Be specific about the vibe, how to style it, and what the overall look communicates."
        )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return (
            f"Unable to generate outfit suggestion. "
            f"The {new_item['title']} would pair well with jeans and a neutral top."
        )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    if not outfit or not outfit.strip():
        return "Unable to generate fit card: no outfit suggestion was provided."

    client = _get_groq_client()

    prompt = (
        f"Write a 2–4 sentence Instagram or TikTok caption for this thrift find and outfit.\n\n"
        f"Thrifted item: {new_item['title']} — ${new_item['price']} from {new_item['platform']}\n"
        f"Outfit: {outfit}\n\n"
        "Requirements:\n"
        "- Sound casual and authentic, like a real OOTD post — not a product description\n"
        "- Mention the item name, price, and platform naturally, exactly once each\n"
        "- Be specific about the outfit vibe in concrete terms\n"
        "- Keep it 2–4 sentences total"
    )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return (
            f"Fit card unavailable. "
            f"Found: {new_item['title']} — ${new_item['price']} on {new_item['platform']}."
        )
