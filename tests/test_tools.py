"""
tests/test_tools.py

Isolation tests for each FitFindr tool.

Run with:
    pytest tests/

LLM-dependent tests (suggest_outfit, create_fit_card happy paths) make real
Groq API calls and require GROQ_API_KEY in .env. The failure-mode tests for
those tools do NOT call the LLM and are always safe to run.
"""

import pytest
from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def graphic_tee():
    """A minimal listing dict representing a graphic tee — used across tool tests."""
    return {
        "id": "lst_006",
        "title": "Graphic Tee — 2003 Tour Bootleg Style",
        "description": "Vintage-style bootleg tee with faded graphic. Slightly boxy fit.",
        "category": "tops",
        "style_tags": ["graphic tee", "vintage", "grunge", "streetwear"],
        "size": "L",
        "condition": "good",
        "price": 24.00,
        "colors": ["black"],
        "brand": None,
        "platform": "depop",
    }


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []   # empty list, no exception


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter():
    """Items returned must contain the size token (case-insensitive)."""
    results = search_listings("tee", size="M", max_price=None)
    assert len(results) > 0
    assert all("m" in item["size"].lower() for item in results)


def test_search_no_size_filter_returns_more():
    """Removing the size filter should return at least as many results."""
    with_size = search_listings("vintage", size="M", max_price=None)
    without_size = search_listings("vintage", size=None, max_price=None)
    assert len(without_size) >= len(with_size)


def test_search_top_result_is_relevant():
    """The first result for 'vintage graphic tee' should actually be a graphic tee."""
    results = search_listings("vintage graphic tee", size=None, max_price=None)
    assert len(results) > 0
    first = results[0]
    searchable = " ".join([
        first["title"], first["description"],
        " ".join(first["style_tags"])
    ]).lower()
    assert any(token in searchable for token in ["graphic", "tee", "vintage"])


def test_search_returns_full_listing_fields():
    """Every returned dict should have all required listing fields."""
    required_fields = {"id", "title", "description", "category", "style_tags",
                       "size", "condition", "price", "colors", "brand", "platform"}
    results = search_listings("vintage", size=None, max_price=None)
    for item in results:
        assert required_fields.issubset(item.keys())


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def test_suggest_outfit_with_wardrobe(graphic_tee):
    """With a populated wardrobe, returns a non-empty outfit suggestion."""
    result = suggest_outfit(graphic_tee, get_example_wardrobe())
    assert isinstance(result, str)
    assert len(result.strip()) > 0


def test_suggest_outfit_empty_wardrobe(graphic_tee):
    """
    Failure mode: empty wardrobe.
    Should return general styling advice, not crash or return empty string.
    """
    result = suggest_outfit(graphic_tee, get_empty_wardrobe())
    assert isinstance(result, str)
    assert len(result.strip()) > 0


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def test_create_fit_card_empty_outfit(graphic_tee):
    """
    Failure mode: empty outfit string.
    Should return the specific error string without calling the LLM.
    """
    result = create_fit_card("", graphic_tee)
    assert result == "Unable to generate fit card: no outfit suggestion was provided."


def test_create_fit_card_whitespace_outfit(graphic_tee):
    """Whitespace-only outfit should also trigger the error guard."""
    result = create_fit_card("   \n  ", graphic_tee)
    assert result == "Unable to generate fit card: no outfit suggestion was provided."


def test_create_fit_card_returns_caption(graphic_tee):
    """With valid outfit input, returns a non-empty caption string."""
    outfit = "Pair with baggy dark-wash jeans and chunky sneakers for a vintage streetwear look."
    result = create_fit_card(outfit, graphic_tee)
    assert isinstance(result, str)
    assert len(result.strip()) > 0
