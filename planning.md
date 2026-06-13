# FitFindr — planning.md

FitFindr takes a natural-language thrifting request, searches a mock listings
dataset, suggests an outfit using the user's wardrobe, and writes a shareable fit
card caption. `search_listings` runs first on the parsed query; if it finds
nothing the agent stops and tells the user what to loosen. If it finds something,
the top result flows into `suggest_outfit`, then that outfit flows into
`create_fit_card`. Every tool handles its own empty/error case instead of
crashing.

---

## Tools

### Tool 1: search_listings

**What it does:** Filters the 40-item mock listings dataset by size/price and ranks
the rest by keyword overlap with the description. No LLM.

**Input parameters:**
- `description` (str): keywords for what the user wants, e.g. "vintage graphic tee".
- `size` (str | None): size to filter by, case-insensitive, `None` to skip.
- `max_price` (float | None): inclusive price ceiling, `None` to skip.

**What it returns:** `list[dict]` of matching listings, best match first. Each dict
has `id, title, description, category, style_tags, size, condition, price, colors,
brand, platform`. Returns `[]` if nothing matches.

**What happens if it fails or returns nothing:** Returns `[]` (never raises). The
agent sees the empty list and stops with an error message telling the user what to
drop.

---

### Tool 2: suggest_outfit

**What it does:** Asks the LLM to style the found item against the user's wardrobe.

**Input parameters:**
- `new_item` (dict): a listing dict from `search_listings`.
- `wardrobe` (dict): has an `items` key (list of wardrobe-item dicts). May be empty.

**What it returns:** `str` — 2–4 sentences of outfit advice. With a wardrobe it
names real pieces; with an empty wardrobe it gives general styling advice.

**What happens if it fails or returns nothing:** Empty wardrobe → general advice
prompt instead of crashing. LLM/API error → caught, returns a safe fallback string.
Always returns a non-empty string.

---

### Tool 3: create_fit_card

**What it does:** Turns the outfit + item into a short casual OOTD caption.

**Input parameters:**
- `outfit` (str): the suggestion string from `suggest_outfit`.
- `new_item` (dict): the listing dict for the item.

**What it returns:** `str` — a 2–4 sentence caption that mentions the item, price,
and platform. Uses temperature 0.9 so it differs each run.

**What happens if it fails or returns nothing:** Empty/whitespace `outfit` → returns
an error string (no LLM call). LLM/API error → caught, returns a fallback string.
Never raises.

---

### Additional Tools (if any)

None. Required three only.

---

## Planning Loop

`run_agent(query, wardrobe)` runs these steps in order, branching on the search
result:

1. `_parse_query(query)` → `{description, size, max_price}` (regex, no LLM). Store in
   `session["parsed"]`.
2. `results = search_listings(description, size, max_price)`. Store in
   `session["search_results"]`.
3. **Branch:** if `results == []` → set `session["error"]` (with which filters to
   drop) and `return` early. `suggest_outfit` and `create_fit_card` are never called,
   so `fit_card` stays `None`.
4. Else `session["selected_item"] = results[0]`.
5. `session["outfit_suggestion"] = suggest_outfit(selected_item, wardrobe)`.
6. `session["fit_card"] = create_fit_card(outfit_suggestion, selected_item)`.
7. Return `session`.

So behavior changes on the search result: a good query runs all three tools, a
dead-end query runs one tool and stops.

---

## State Management

One `session` dict per call is the single source of truth (`_new_session`). Fields:
`query, parsed, search_results, selected_item, wardrobe, outfit_suggestion,
fit_card, error`. Each tool reads what it needs from the session and writes its
result back, so nothing is re-entered. `selected_item` is literally
`search_results[0]` (same object), and that same dict is passed into both
`suggest_outfit` and `create_fit_card`. The Gradio layer reads the final session and
maps `selected_item`, `outfit_suggestion`, `fit_card` to the three panels.

---

## Error Handling

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Returns `[]`; agent sets `error` like `No listings matched "designer ballgown". Try dropping the size (XXS) or price (under $5) filter.` and stops before the LLM tools. |
| suggest_outfit | Wardrobe is empty | Switches to a general-advice prompt and returns styling tips for the item; on API error returns a neutral fallback string. |
| create_fit_card | Outfit input is missing or incomplete | Returns `Can't write a fit card without an outfit — find an item and get a styling suggestion first, then try again.` with no LLM call. |

---

## Architecture

```
User query + wardrobe
        │
        ▼
   run_agent()  ── Planning Loop ───────────────────────────────┐
        │                                                        │
   _parse_query() → session["parsed"] = {description,size,price} │
        │                                                        │
        ├─► search_listings(description, size, max_price)        │
        │        │ results == []                                 │
        │        ├──► session["error"] = "No listings..."  ──────┤ early return
        │        │     (fit_card stays None)                     │ (fit_card None)
        │        │                                               │
        │        │ results = [item, ...]                         │
        │        ▼                                               │
        │   session["selected_item"] = results[0]                │
        │        │                                               │
        ├─► suggest_outfit(selected_item, wardrobe)              │
        │        │  empty wardrobe → general advice              │
        │   session["outfit_suggestion"] = "..."                 │
        │        │                                               │
        └─► create_fit_card(outfit_suggestion, selected_item)    │
                 │  empty outfit → error string                  │
             session["fit_card"] = "..."  ◄──────────────────────┘
                 │
                 ▼
           return session  →  Gradio maps to 3 panels
```

---

## AI Tool Plan

**Tool used:** Claude (Claude Code).

**Milestone 3 — Individual tool implementations:** Give Claude each Tool block above
(inputs, return value, failure mode) one at a time. For `search_listings` tell it to
use `load_listings()` and not re-read the file, filter by all three params, and
return `[]` on no match. For the two LLM tools, tell it to call Groq
`llama-3.3-70b-versatile`, handle the empty case before calling the model, and wrap
the call in try/except. Verify: run the pytest tests in `tests/` and the three
failure triggers before trusting any of it.

**Milestone 4 — Planning loop and state management:** Give Claude the Planning Loop +
State Management sections and the diagram. Check the generated `run_agent` branches
on the empty search result, writes every result into the session dict, and does not
call the LLM tools on the no-results path. Verify by running `python agent.py` and
confirming the no-results path leaves `fit_card` as `None`.

---

## A Complete Interaction (Step by Step)

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly
wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:** `_parse_query` pulls out `max_price=30.0`, `size=None`, and
`description="vintage graphic tee ... baggy jeans and chunky sneakers"`. Then
`search_listings(description, None, 30.0)` runs and returns ranked listings; the top
one is `Graphic Tee — 2003 Tour Bootleg Style` ($24, depop). Stored as
`selected_item`.

**Step 2:** `suggest_outfit(selected_item, wardrobe)` runs on that exact item plus
the example wardrobe and returns something like: pair the tee with the baggy
straight-leg jeans and black combat boots for a grunge look. Stored as
`outfit_suggestion`.

**Step 3:** `create_fit_card(outfit_suggestion, selected_item)` returns a caption
like: "just scored this sick 2003 tour bootleg graphic tee on depop for $24 and i'm
obsessed 🤩 paired it with my baggy jeans + combat boots for a grunge vibe." Stored
as `fit_card`.

**Final output to user:** The three Gradio panels show the listing details, the
outfit idea, and the fit card caption.
