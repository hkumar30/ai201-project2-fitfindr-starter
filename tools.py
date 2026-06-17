"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)           → list[dict]
    suggest_outfit(new_item, wardrobe, context=None)         → str
    create_fit_card(outfit, new_item)                        → str
    compare_price(item, listings)                            → str
    get_trend_report(item)                                   → str
"""

import json
import os
import statistics

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

def suggest_outfit(new_item: dict, wardrobe: dict, context: str | None = None) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handled explicitly without
                  raising (switches to a general styling prompt).
        context:  Optional string combining the trend report from get_trend_report
                  and the user's accumulated style history from load_style_profile.
                  Appended to the LLM prompt so outfit suggestions reflect current
                  trends and the user's known tastes. Pass None to skip.

    Returns:
        A non-empty string with outfit suggestions. For a populated wardrobe,
        names specific wardrobe pieces by name in each outfit. For an empty
        wardrobe, provides general styling advice (silhouettes, colors, occasions).
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
        context_block = f"\n\nAdditional context:\n{context}" if context else ""
        prompt = (
            f"A user is considering buying this secondhand item:\n{item_summary}\n\n"
            "They don't have a saved wardrobe yet. Suggest general styling ideas: "
            "what kinds of pieces pair well with this item (be specific about "
            "silhouettes, colors, and fabrics), what aesthetic it fits, and what "
            f"occasions it works for. Be concrete — avoid generic advice.{context_block}"
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

        context_block = f"\n\nAdditional context:\n{context}" if context else ""
        prompt = (
            f"A user just found this secondhand item:\n{item_summary}\n\n"
            f"Their existing wardrobe includes:\n{wardrobe_text}"
            f"{context_block}\n\n"
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

    The caption:
    - Feels casual and authentic (like a real OOTD post, not a product description)
    - Mentions the item name, price, and platform naturally (once each)
    - Captures the outfit vibe in specific terms
    - Varies meaningfully across calls with different inputs (temperature 0.9)
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


# ── Tool 4: compare_price ─────────────────────────────────────────────────────

def compare_price(item: dict, listings: list[dict]) -> str:
    """
    Estimate whether an item's price is fair based on comparable listings.

    Comparables are defined as listings in the same category with at least
    one overlapping style tag. The item itself is excluded from the set.

    Args:
        item:     The selected listing dict. Uses 'id', 'category',
                  'style_tags', 'title', and 'price'.
        listings: The full dataset (from load_listings()). Comparables are
                  drawn from this list.

    Returns:
        A multi-line string with:
          - The item price and a verdict (GREAT DEAL / FAIR PRICE / ABOVE AVERAGE)
          - Comparable set stats (count, avg, price range)
          - One sentence of reasoning
        Returns a descriptive string (no exception) if fewer than 2 comparables
        are found.
    """
    item_tags = set(item.get("style_tags", []))
    item_category = item.get("category", "")

    comparables = [
        l for l in listings
        if l["id"] != item["id"]
        and l["category"] == item_category
        and len(set(l.get("style_tags", [])) & item_tags) >= 1
    ]

    if len(comparables) < 2:
        return (
            f"Not enough comparable listings to assess pricing for {item['title']}. "
            f"Only {len(comparables)} similar {item_category} found in the dataset."
        )

    prices = [l["price"] for l in comparables]
    avg = statistics.mean(prices)
    median = statistics.median(prices)
    min_p = min(prices)
    max_p = max(prices)
    item_price = item["price"]

    if item_price <= median * 0.80:
        verdict = "GREAT DEAL"
    elif item_price <= median * 1.10:
        verdict = "FAIR PRICE"
    else:
        verdict = "ABOVE AVERAGE"

    direction = "below" if item_price < avg else "above"

    return (
        f"Price: ${item_price:.2f} — {verdict}\n"
        f"Comparable {item_category} ({len(comparables)} listings): "
        f"avg ${avg:.2f}, median ${median:.2f}, range ${min_p:.2f}–${max_p:.2f}\n"
        f"Reasoning: {item['title']} is priced {direction} the ${avg:.2f} average "
        f"for {item_category} with similar style tags."
    )


# ── Tool 5: get_trend_report ──────────────────────────────────────────────────

_TRENDS_PATH = os.path.join(os.path.dirname(__file__), "data", "trends.json")


def get_trend_report(item: dict) -> str:
    """
    Assess how well an item aligns with current fashion trends.

    Loads trend data from data/trends.json (aggregated from Depop trending
    searches, TikTok #OOTD tags, and Pinterest fashion boards), cross-references
    the item's style tags, category, and colors against trending aesthetics and
    categories, then uses the Groq LLM to produce a 2–3 sentence trend report.

    The returned string is passed into suggest_outfit() as context so outfit
    recommendations reflect the current fashion moment.

    Args:
        item: The selected listing dict. Uses 'title', 'category',
              'style_tags', and 'colors'.

    Returns:
        A 2–3 sentence trend assessment string. Returns a fallback string
        if trends.json is missing or the LLM call fails — never raises.
    """
    fallback = "Trend data unavailable — styling without trend context."

    try:
        with open(_TRENDS_PATH, "r", encoding="utf-8") as f:
            trends = json.load(f)
    except Exception:
        return fallback

    # Find which trending aesthetics and categories overlap with the item
    item_tags = set(t.lower() for t in item.get("style_tags", []))
    item_colors = set(c.lower() for c in item.get("colors", []))
    item_category = item.get("category", "")

    matching_aesthetics = [
        a for a in trends.get("trending_aesthetics", [])
        if a.lower() in item_tags or any(a.lower() in tag for tag in item_tags)
    ]
    matching_category_trends = [
        t for t in trends.get("trending_by_category", {}).get(item_category, [])
        if any(t.lower() in tag for tag in item_tags) or t.lower() in item.get("title", "").lower()
    ]
    matching_colors = [
        c for c in trends.get("trending_colors", [])
        if c.lower() in item_colors or any(c.lower() in col for col in item_colors)
    ]
    rising = [
        r for r in trends.get("rising_searches", [])
        if r.lower() in item_tags or r.lower() in item.get("title", "").lower()
    ]

    trend_summary = (
        f"Trending aesthetics it matches: {', '.join(matching_aesthetics) or 'none directly'}\n"
        f"Trending {item_category} styles it fits: {', '.join(matching_category_trends) or 'none directly'}\n"
        f"Trending colors it contains: {', '.join(matching_colors) or 'none directly'}\n"
        f"Rising search terms it hits: {', '.join(rising) or 'none directly'}"
    )

    prompt = (
        f"You are a fashion trend analyst. Given the trend data below and an item description, "
        f"write a 2–3 sentence trend report explaining whether this item is currently on-trend, "
        f"which specific aesthetics it aligns with, and one concrete styling tip that plays into those trends.\n\n"
        f"Item: {item['title']} (category: {item_category}, "
        f"style tags: {', '.join(item.get('style_tags', []))}, "
        f"colors: {', '.join(item.get('colors', []))})\n\n"
        f"Trend alignment:\n{trend_summary}\n\n"
        "Be specific and concrete — reference the actual trend names. Keep it to 2–3 sentences."
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return fallback
