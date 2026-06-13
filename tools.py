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
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

MODEL = "llama-3.3-70b-versatile"

# Query words that carry no search meaning — dropped before keyword scoring.
_STOPWORDS = {
    "a", "an", "the", "for", "under", "in", "with", "and", "to", "of", "size",
    "im", "i'm", "looking", "look", "want", "need", "me", "my", "that", "this",
    "is", "are", "some", "something", "find", "get", "wear", "around", "less",
    "than", "about", "on", "at",
}


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


def _call_llm(prompt: str, temperature: float = 0.7) -> str:
    """Send a single prompt to the LLM and return the text reply."""
    client = _get_groq_client()
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return resp.choices[0].message.content.strip()


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

    # 1. price filter
    if max_price is not None:
        listings = [item for item in listings if item["price"] <= max_price]

    # 2. size filter (case-insensitive, token-based; "One Size" fits anyone)
    if size:
        listings = [item for item in listings if _size_matches(size, item["size"])]

    # 3. score by keyword overlap with the description
    query_words = {w for w in _tokenize(description) if w not in _STOPWORDS}
    scored = []
    for item in listings:
        score = _score_listing(query_words, item)
        if score > 0:
            scored.append((score, item))

    # 4. best match first
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored]


def _tokenize(text: str) -> list[str]:
    """Lowercase a string and split it into alphanumeric word tokens."""
    return re.findall(r"[a-z0-9]+", text.lower())


def _size_matches(requested: str, listing_size: str) -> bool:
    """True if the requested size matches the listing size, case-insensitive."""
    listing_size = listing_size.lower()
    if "one size" in listing_size:
        return True  # one-size items fit any requested size
    requested = requested.strip().lower()
    listing_tokens = re.split(r"[^a-z0-9]+", listing_size)
    return requested in listing_tokens or requested == listing_size


def _score_listing(query_words: set[str], item: dict) -> int:
    """
    Score a listing by weighted keyword overlap with the query.

    Matches in the title and style tags count for more than matches buried in the
    free-text description, so the most on-topic listing rises to the top.
    """
    weighted_fields = [
        (3, item.get("title", "")),
        (3, " ".join(item.get("style_tags", []))),
        (2, item.get("category", "")),
        (2, item.get("brand") or ""),
        (1, item.get("description", "")),
        (1, " ".join(item.get("colors", []))),
    ]
    score = 0
    for weight, text in weighted_fields:
        text = text.lower()
        score += weight * sum(1 for word in query_words if word in text)
    return score


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
    item_line = _describe_item(new_item)
    items = wardrobe.get("items", []) if isinstance(wardrobe, dict) else []

    if not items:
        prompt = (
            "A user just found this secondhand item but has NOT told you anything "
            "about their existing wardrobe:\n"
            f"{item_line}\n\n"
            "Give general styling advice in 2-4 sentences: what kinds of pieces "
            "pair well with it, what vibe it suits, and how to wear it. Be specific "
            "and practical. Do not invent items the user owns."
        )
    else:
        wardrobe_lines = "\n".join(f"- {_describe_wardrobe_item(w)}" for w in items)
        prompt = (
            "A user just found this secondhand item:\n"
            f"{item_line}\n\n"
            "Here is what they already own:\n"
            f"{wardrobe_lines}\n\n"
            "Suggest 1-2 complete outfits that pair the new item with specific, "
            "named pieces from their wardrobe above. Reference the wardrobe pieces "
            "by name. Keep it to 2-4 sentences total and make it sound like real "
            "styling advice, not a list."
        )

    try:
        return _call_llm(prompt, temperature=0.7)
    except Exception as exc:  # API/network/etc. — stay useful, don't crash
        return (
            "Couldn't reach the styling model just now "
            f"({type(exc).__name__}). A safe bet: keep the rest of the look simple "
            "and neutral so this piece stands out."
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
    # 1. guard: no outfit means nothing to caption
    if not outfit or not outfit.strip():
        return (
            "Can't write a fit card without an outfit — find an item and get a "
            "styling suggestion first, then try again."
        )

    item = new_item if isinstance(new_item, dict) else {}
    title = item.get("title", "this piece")
    price = item.get("price")
    platform = item.get("platform", "")
    price_str = f"${price:g}" if isinstance(price, (int, float)) else "a steal"

    prompt = (
        "Write a short, casual Instagram/TikTok caption for a thrifted outfit. "
        "Sound like a real person posting their OOTD, not a product description.\n\n"
        f"Item: {title}\n"
        f"Price: {price_str}\n"
        f"Platform: {platform}\n"
        f"Outfit: {outfit}\n\n"
        "Rules: 2-4 sentences. Mention the item, price, and platform naturally "
        "(once each). Capture the outfit vibe in specific terms. Lowercase, a "
        "little slangy, an emoji or two is fine. No hashtag dump."
    )

    try:
        return _call_llm(prompt, temperature=0.9)  # high temp -> varied captions
    except Exception as exc:
        return (
            "Couldn't generate a fit card right now "
            f"({type(exc).__name__}). Try again in a sec."
        )


# ── helpers ───────────────────────────────────────────────────────────────────

def _describe_item(item: dict) -> str:
    """One-line description of a listing for an LLM prompt."""
    if not isinstance(item, dict):
        return str(item)
    tags = ", ".join(item.get("style_tags", []))
    price = item.get("price")
    price_str = f"${price:g}" if isinstance(price, (int, float)) else "?"
    return (
        f"{item.get('title', 'Unknown item')} ({item.get('category', '')}, "
        f"{price_str}, {item.get('condition', '')}, on {item.get('platform', '')}). "
        f"Style: {tags}. {item.get('description', '')}"
    ).strip()


def _describe_wardrobe_item(w: dict) -> str:
    """One-line description of a wardrobe item for an LLM prompt."""
    if not isinstance(w, dict):
        return str(w)
    tags = ", ".join(w.get("style_tags", []))
    notes = w.get("notes", "")
    line = f"{w.get('name', 'item')} ({w.get('category', '')}; {tags})"
    return f"{line} — {notes}" if notes else line
