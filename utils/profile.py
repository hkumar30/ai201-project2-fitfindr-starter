"""
utils/profile.py

Style profile persistence for FitFindr.

Stores a user's accumulated style preferences to disk so the agent can
reference them in future sessions without the user re-describing their
wardrobe or style each time.

Functions:
    load_style_profile()          → dict
    save_style_profile(session)   → None
"""

import json
import os

_PROFILE_PATH = os.path.join(os.path.dirname(__file__), "..", "user_profile.json")
_MAX_HISTORY = 5
_MAX_STYLES = 15


def load_style_profile() -> dict:
    """
    Load the user's style profile from disk.

    Returns a dict with keys:
        preferred_styles  (list[str])  — style tags accumulated from past interactions
        preferred_size    (str | None) — most recently used size filter
        search_history    (list[str])  — last 5 search descriptions

    If the file doesn't exist or contains malformed JSON, returns an empty
    profile — never raises.
    """
    empty = {"preferred_styles": [], "preferred_size": None, "search_history": []}
    try:
        if not os.path.exists(_PROFILE_PATH):
            return empty
        with open(_PROFILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Ensure all expected keys are present
        return {
            "preferred_styles": data.get("preferred_styles", []),
            "preferred_size": data.get("preferred_size"),
            "search_history": data.get("search_history", []),
        }
    except Exception:
        return empty


def save_style_profile(session: dict) -> None:
    """
    Extract style preferences from a completed session and persist them.

    Merges the selected item's style tags into the profile (up to
    _MAX_STYLES unique tags, oldest dropped first). Updates preferred_size
    if the session parsed one. Prepends the description to search_history
    (capped at _MAX_HISTORY).

    Does nothing if the session has no selected_item (e.g., error path).
    Catches all write errors silently — a failed save never aborts a session.
    """
    if not session.get("selected_item"):
        return

    try:
        profile = load_style_profile()

        # Merge style tags from the selected item
        new_tags = session["selected_item"].get("style_tags", [])
        merged = list(dict.fromkeys(new_tags + profile["preferred_styles"]))
        profile["preferred_styles"] = merged[:_MAX_STYLES]

        # Update preferred size if the session used one
        parsed_size = session.get("parsed", {}).get("size")
        if parsed_size:
            profile["preferred_size"] = parsed_size

        # Prepend description to search history
        desc = session.get("parsed", {}).get("description", "").strip()
        if desc:
            history = [desc] + [h for h in profile["search_history"] if h != desc]
            profile["search_history"] = history[:_MAX_HISTORY]

        with open(_PROFILE_PATH, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2)

    except Exception:
        pass  # Silent failure — profile save is best-effort
