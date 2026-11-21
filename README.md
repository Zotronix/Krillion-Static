# Krillion — static replica

A browser-only recreation of the Krillion dive: seven prompts, 25 seconds each, six rarity
tiers, typo correction, a pixel ocean that actually descends, and a score report.

**One page, no server, no build required to play.** `krillion.html` is standalone: the styles,
the whole app and the bundled prompt packs are inlined, so opening the file from disk works.
Daily and Unlimited both live on that page and switch in place.

```
start index.html                  # or double-click it
node serve.mjs                    # optional: http://localhost:3060, enables real packs
node build.mjs                    # rebuild index.html after editing src/ or style.css
node --test tests/*.test.mjs      # rules, loader and dive tests
```

`src/*.mjs` are ES modules so the tests can import them; `build.mjs` strips the imports and
inlines everything into `index.html`. Edit the sources, run the build, reload.

## Modes

- **Daily**: one numbered dive per day. The day number comes from the America/New_York date,
  counting from day 1 on 2026-07-16 (2026-11-16 is day 124). `?day=90` overrides it.
- **Unlimited**: a fresh seven-prompt set per dive, numbered and shareable as
  `?mode=unlimited&id=7`. Offline it deals from the bundled prompt pool, seeded by the id, so
  each dive differs. Served over HTTP it reads `unlimited/unlimited_{id}.json`.

Switching modes never reloads the page. A finished daily dive reopens its report instead of
replaying. Dives are stored in `localStorage` under `krillion.history.v1`.

## Data files

The bundle always carries `data/sample-daily.json` and `unlimited/unlimited_1.json` as a
fallback. When the page is served over HTTP it prefers real files beside it:

`daily/game_{day}.json`

```json
{
  "dayNumber": 124,
  "date": "2026-11-16",
  "source": "your reference",
  "prompts": [
    {
      "id": "p1",
      "text": "Name a country with the letter B in its name.",
      "answers": [
        { "answer": "Belgium", "aliases": ["be"], "tier": "plankton" },
        { "answer": "Luxembourg", "tier": "krillion", "note": "Tiny, landlocked, hiding a b." }
      ]
    }
  ]
}
```

`unlimited/unlimited_{game}.json` is the same with `gameId` instead of `dayNumber`/`date`.
`unlimited/manifest.json` is `{ "count": 275 }`, ids 1…count.

### Loader tolerance

| Canonical | Also accepted |
| --- | --- |
| `prompts` | `questions` |
| `text` | `prompt`, `question` |
| `answers: [{ answer }]` | `text`, `value`, `name`; `aliases` / `accept` / `alternatives` |
| `tier` | `rarity`, `category`; tier-grouped `{ "plankton": ["…"], "krillion": [{…}] }` |
| `tier` | `points` / `score` exactly 10, 15, 30, 60, 85 or 100 |
| — | `note` / `trivia` shown after landing |

A pack is rejected unless it yields seven usable prompts, each with at least one answer.
Missing files fall back to the bundled pack and the intro says so.

## Scoring

| Tier | Points | Depth |
| --- | --- | --- |
| Plankton | 10 | 100 m |
| Too Clever | 15 | 150 m |
| Schooler | 30 | 300 m |
| Rare | 60 | 600 m |
| Deep Cut | 85 | 850 m |
| One in a Krillion | 100 | 1,000 m |

Seven answers cap at 700 points and 7,000 metres. Bands: 0–150 Plankton, 151–250 Schooler,
251–350 Rare, 351–449 Deep Cut, 450+ One in a Krillion.

Answers are normalised (NFKD, accents dropped, `&` → and, non-alphanumerics removed).
Exact matches and aliases score immediately; leading articles and singular/plural forms are
folded, and a near miss within 0 edits (under 4 letters), 1 edit (under 8) or 2 edits is
offered back as a correction. Swapped letters count as one edit. Multi-word answers must stay
close word by word, and genuinely ambiguous candidates are refused.

## What this build does not do

- No AI answer checker: answers outside a prompt's list are refused.
- No population comparison or percentile: those need a server.
- No accounts, ads, payments or analytics. Settings, streaks, buddies and history are local.

## Files

| Path | Role |
| --- | --- |
| `index.html` | the built single-file game |
| `page.html` | template the build fills in |
| `build.mjs` | inlines CSS, modules and packs |
| `src/rules.mjs` | tiers, bands, normalisation, matching, day maths, share text |
| `src/dataset.mjs` | pack loading, tolerance, offline deals |
| `src/engine.mjs` | the dive state machine (no DOM) |
| `src/app.mjs` | screens, timers, descent choreography, menus, results |
| `src/shell.mjs` | shared page chrome and per-mode copy |
| `src/ocean.mjs`, `src/scene-layers.mjs` | canvas scene, parallax and descent effects |
| `src/presentation.mjs` | charts and tier icons |
| `src/sound.mjs` | synthesised cues |
| `src/storage.mjs` | settings, history, streaks, buddies |
| `serve.mjs` | optional zero-dependency static server |
