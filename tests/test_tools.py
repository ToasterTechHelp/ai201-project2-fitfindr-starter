"""
tests/test_tools.py

One test per failure mode (plus a few happy-path checks). Run with:
    pytest tests/

The LLM-backed tests are skipped automatically if GROQ_API_KEY isn't set, so
the search tests always run offline.
"""

import os
import sys

import pytest

# make the project root importable when running `pytest tests/`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

load_dotenv()

needs_key = pytest.mark.skipif(
    not os.environ.get("GROQ_API_KEY"),
    reason="GROQ_API_KEY not set",
)


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []  # empty list, no exception


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter():
    results = search_listings("track jacket", size="M", max_price=None)
    # "M" should match listings sized "M", "S/M", "M/L", etc. — never an exception
    assert isinstance(results, list)
    assert all("m" in item["size"].lower() for item in results)


# ── create_fit_card guard (no API call needed) ────────────────────────────────

def test_fit_card_empty_outfit_returns_message():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    msg = create_fit_card("", item)
    assert isinstance(msg, str)
    assert msg.strip() != ""
    assert "outfit" in msg.lower()  # tells the user what went wrong


# ── LLM-backed tools (skipped without a key) ──────────────────────────────────

@needs_key
def test_suggest_outfit_empty_wardrobe():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    out = suggest_outfit(item, get_empty_wardrobe())
    assert isinstance(out, str)
    assert out.strip() != ""  # general advice, not empty


@needs_key
def test_suggest_outfit_with_wardrobe():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    out = suggest_outfit(item, get_example_wardrobe())
    assert isinstance(out, str)
    assert out.strip() != ""
