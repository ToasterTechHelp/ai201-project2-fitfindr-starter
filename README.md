# FitFindr

A multi-tool AI agent for thrifting. You describe what you want; it searches mock
secondhand listings, suggests an outfit from your wardrobe, and writes a shareable
fit card caption.

## Setup

```bash
pip install -r requirements.txt
```

Add your Groq key to a `.env` in the repo root:

```
GROQ_API_KEY=your_key_here
```

Run the app:

```bash
python app.py
```

Run the tools from the CLI / tests:

```bash
python agent.py
pytest tests/
```

## Tools

| Tool | Inputs | Output | Purpose |
|------|--------|--------|---------|
| `search_listings` | `description` (str), `size` (str \| None), `max_price` (float \| None) | `list[dict]` of listings, best match first; `[]` if none | Filter the dataset by size/price, rank the rest by keyword overlap. No LLM. |
| `suggest_outfit` | `new_item` (dict), `wardrobe` (dict) | `str` outfit advice (2–4 sentences) | Style the found item against the wardrobe (or give general advice if the wardrobe is empty). Uses Groq `llama-3.3-70b-versatile`. |
| `create_fit_card` | `outfit` (str), `new_item` (dict) | `str` caption | Turn the outfit into a casual OOTD caption mentioning the item, price, and platform. Temperature 0.9 so it varies. |

## How the planning loop works

`run_agent(query, wardrobe)` doesn't run a fixed sequence — it branches on the
search result:

1. `_parse_query` regex-extracts `max_price`, `size`, and a cleaned `description`.
2. `search_listings` runs with those params.
3. **If it returns `[]`**, the agent sets `session["error"]` and returns early.
   `suggest_outfit` and `create_fit_card` are never called, so `fit_card` stays
   `None`.
4. **If it returns matches**, `selected_item = results[0]`, then `suggest_outfit`,
   then `create_fit_card`.

So a real query runs all three tools and a dead-end query runs one tool and stops.

## State management

One `session` dict per call holds everything: `query, parsed, search_results,
selected_item, wardrobe, outfit_suggestion, fit_card, error`. Each tool reads from
it and writes its result back, so nothing gets re-entered. `selected_item` is the
same object as `search_results[0]`, and that exact dict is passed into both
`suggest_outfit` and `create_fit_card`. Verified at runtime:
`selected_item is search_results[0]` → `True`.

## Error handling (one real example each)

- **search_listings — no results:** returns `[]`, agent stops with a message.
  Query `"designer ballgown size XXS under $5"` →
  `No listings matched "designer ballgown". Try dropping the size (XXS) or price (under $5) filter.`
  (`fit_card` and `outfit_suggestion` stay `None`.)
- **suggest_outfit — empty wardrobe:** switches to a general-advice prompt instead
  of crashing. Empty wardrobe + the graphic tee returned:
  *"This graphic tee is perfect for creating a casual, laid-back look. You can pair
  it with distressed denim jeans or joggers ... finish the look with sneakers or
  boots."* API errors are caught and return a neutral fallback string.
- **create_fit_card — empty outfit:** guards before any LLM call.
  `create_fit_card("", item)` →
  `Can't write a fit card without an outfit — find an item and get a styling suggestion first, then try again.`

All three are covered by `tests/test_tools.py` (7 tests, all passing).

## Spec reflection

- **Helped:** the "every tool handles its own failure mode" requirement forced me to
  guard the empty-outfit case in `create_fit_card` *before* hitting the LLM, so that
  path is free and can't crash.
- **Diverged:** the spec left query parsing open (regex / splitting / LLM). I used
  regex so it's deterministic and free, and I left the full description (including
  wardrobe mentions) feeding the keyword scorer instead of extracting only the item
  name — simpler and the scoring handles the extra words. I also added a UTF-8
  stdout fix to `agent.py`'s CLI block, which wasn't in the spec, because emoji in
  fit cards crashed the default Windows console.

## AI usage

1. **Implementing `search_listings`** — I gave Claude the Tool 1 spec (inputs,
   return, failure mode) and told it to use `load_listings()`, filter by all three
   params, and return `[]` on no match. The first version scored every text field
   equally, which ranked "Y2K Baby Tee" above the actual graphic tee for a "graphic
   tee" query. I overrode it to weight title/style-tag matches higher than
   description matches, which fixed the ranking.
2. **Implementing the planning loop in `run_agent`** — I gave Claude the Planning
   Loop + State Management sections and the diagram. It produced the branch
   correctly, but I added the early-return loosening hint (which filters to drop)
   and the Windows UTF-8 stdout guard in the `__main__` block after `python agent.py`
   crashed printing an emoji fit card.
