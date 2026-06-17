"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card, compare_price, get_trend_report
from utils.data_loader import load_listings
from utils.profile import load_style_profile, save_style_profile


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "retry_info": None,          # set if retry logic loosened a constraint
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "price_assessment": None,    # string returned by compare_price
        "trend_report": None,        # string returned by get_trend_report
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    Flow: load profile → parse query → search (with retry) → compare_price →
          get_trend_report → suggest_outfit (with trend + profile context) →
          create_fit_card → save profile → return session.
    """
    # Step 1: load style profile from previous sessions
    profile = load_style_profile()

    # Step 2: initialize session
    session = _new_session(query, wardrobe)

    # Step 3: parse query with regex
    # --- extract max_price ---
    price_match = re.search(
        r'(?:under|below|less than|up to|max|no more than)\s*\$?(\d+(?:\.\d+)?)',
        query,
        re.IGNORECASE,
    )
    max_price = float(price_match.group(1)) if price_match else None

    # --- extract size: "size M" form first, then bare token fallback ---
    size_match = re.search(r'\bsize\s+([A-Z0-9/]+)', query, re.IGNORECASE)
    if size_match:
        size = size_match.group(1).upper()
    else:
        standalone = re.search(
            r'\b(XXS|XS|S/M|M/L|L/XL|S|M|L|XL|XXL|XXXL)\b',
            query,
            re.IGNORECASE,
        )
        size = standalone.group(1).upper() if standalone else None

    # --- build description: strip price and size clauses, then normalize ---
    desc = query
    if price_match:
        desc = re.sub(
            r'(?:under|below|less than|up to|max|no more than)\s*\$?\d+(?:\.\d+)?',
            '',
            desc,
            flags=re.IGNORECASE,
        )
    if size_match:
        desc = re.sub(r'\bsize\s+[A-Z0-9/]+', '', desc, flags=re.IGNORECASE)
    elif size:
        desc = re.sub(
            r'\b(XXS|XS|S/M|M/L|L/XL|S|M|L|XL|XXL|XXXL)\b',
            '',
            desc,
            flags=re.IGNORECASE,
        )
    description = ' '.join(desc.lower().split())

    session["parsed"] = {
        "description": description,
        "size": size,
        "max_price": max_price,
    }

    # Step 4: search with retry logic
    results = search_listings(description, size, max_price)

    # Retry 1: drop size filter
    if not results and size is not None:
        results = search_listings(description, None, max_price)
        if results:
            session["retry_info"] = (
                f"No results found for size '{size}'. "
                f"Showing results without size filter."
            )

    # Retry 2: drop price filter as well
    if not results and max_price is not None:
        results = search_listings(description, None, None)
        if results:
            if size is not None:
                session["retry_info"] = (
                    f"No results found for size '{size}' under ${max_price:.0f}. "
                    f"Showing results with size and price filters removed."
                )
            else:
                session["retry_info"] = (
                    f"No results found under ${max_price:.0f}. "
                    f"Showing results with price filter removed."
                )

    session["search_results"] = results

    if not results:
        session["error"] = (
            f"No listings found matching '{query}'. "
            "Try different keywords, a different size, or a higher price limit."
        )
        return session

    # Step 5: select top result
    session["selected_item"] = results[0]

    # Step 6: price comparison (no LLM — pure dataset math)
    all_listings = load_listings()
    session["price_assessment"] = compare_price(session["selected_item"], all_listings)

    # Step 7: trend report (LLM + trends.json)
    session["trend_report"] = get_trend_report(session["selected_item"])

    # Step 8: build combined context string for suggest_outfit
    context_parts = []
    if session["trend_report"] and "unavailable" not in session["trend_report"]:
        context_parts.append(f"Trend context:\n{session['trend_report']}")
    if profile.get("preferred_styles"):
        context_parts.append(
            f"This user's style history: {', '.join(profile['preferred_styles'][:8])}"
        )
    outfit_context = "\n\n".join(context_parts) if context_parts else None

    # Step 9: suggest outfit (now informed by trends and style history)
    session["outfit_suggestion"] = suggest_outfit(
        session["selected_item"],
        session["wardrobe"],
        context=outfit_context,
    )

    # Step 10: generate fit card
    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"],
        session["selected_item"],
    )

    # Step 11: persist style preferences for next session
    save_style_profile(session)

    # Step 12: return completed session
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
