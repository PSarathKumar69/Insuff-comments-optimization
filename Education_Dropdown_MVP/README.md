# Education insufficiency-comment dropdown MVP

## How to run this in VS Code

1. Open this folder (`Education_Dropdown_MVP`) in VS Code — either
   `File > Open Folder...`, or open the whole `Insufficiency Comments`
   folder and navigate here in the Explorer sidebar.
2. You need PHP installed on your machine (Bridge's own stack already has
   it; if you're testing on a personal machine and don't have it, install
   via `https://windows.php.net/download` or `winget install php.php` on
   Windows, or `brew install php` on Mac).
3. Open a terminal in VS Code (`` Ctrl+` ``), make sure you're in *this*
   folder, then run:
   ```
   php -S localhost:8000 -t public router.php
   ```
4. Open `http://localhost:8000` in your browser. You'll see the full
   dropdown builder: category → reason → detail fields → live generated
   comment, plus the search/triage card at the bottom.
5. Stop the server with `Ctrl+C` in the terminal when done.

No build step, no npm install — it's plain PHP + HTML/CSS/JS, so the
`php -S` command above is the entire setup.

## Re-generating the data (only needed if the source workbook changes)

The three `build_*.py` scripts regenerate everything under `data/` from
`../Output Excel Sheets/Actual_To_Atomic_Mapping.xlsx`. Run them **in this
order**, from this folder:

```
python3 build_data.py
python3 build_templates.py
python3 build_search_index.py
```

(Needs `pip install openpyxl` if not already installed.) These are now
fully self-contained — they read directly from the source workbook, no
dependency on any prior session's temp files.

## What's here

- `data/` — JSON config: `dropdown_tree.json` (the Insuff Category → Reason
  → Sub-reason → Template decision tree), `templates.json` (37 optimized
  templates with reason clauses baked in; IDs run T1-T74 with gaps, since
  retired IDs were merged into surviving templates and are never reused), `tag_values.json` (real,
  frequency-ranked dropdown values per tag), `search_index.json` (all 8,284
  classified actual comments, for the support-triage search feature).
- `php/CommentEngine.php` — stitches the final comment from a dropdown
  selection. `php/SearchEngine.php` — reverse-lookup search for the triage
  card.
- `public/index.html` + `public/app.js` — the actual UI (dropdowns + live
  preview + search card).
- `public/*.php` — thin endpoints wrapping the two engine classes.
- `ACCEPTANCE_TEST.md` — 5 before/after comment comparisons against the
  4 acceptance criteria (context, reason, no ambiguity, no grammar errors,
  no leaked placeholders).

## Known limitations (prototype, not production)

- Search is a linear token-overlap scan over 8,284 rows — fine at this
  scale (<50ms), but should move to a real search index (e.g. SQLite FTS5)
  if this goes into production.
- Employment and Address department templates exist in the source data but
  aren't wired into this Education-only build (flagged as
  `template_exists_not_in_education_mvp` in search results, not silently
  dropped).
- Family/Check header is a simulated picker here; in Bridge it auto-fills
  from the case navigation context that's already established before an
  agent reaches the insuff-raising screen.

## Files not in this repository

Two files the app reads are deliberately excluded from version control
(see `.gitignore` at the repo root) and must be supplied locally:

**1. `data/search_index.json`** — powers the support-triage search card
(`php/SearchEngine.php`, `api/search.php`). It holds 8,284 real historical
insufficiency comments plus ~12 synthetic rows, and that comment text carries
third-party PII: institution contact email addresses, and occasional candidate
names and dates of birth. It is not published. Without it, the dropdown
generator (Category → Reason → detail fields → generated comment) works
normally, but the search card and both search regression suites
(`test_search_engine_logic.py`, and Part C of it in particular) will fail to
load. Copy the file into `data/` from the internal working folder to restore
full functionality.

**2. `.env`** at the repo root — holds two Gemini API keys:

```
GEMINI_API_KEY=<key used by the offline batch classification pipeline>
TRIAGE_GEMINI_API_KEY=<key used by php/GeminiTriageClient.php at runtime>
```

Both are optional for local use. Without `TRIAGE_GEMINI_API_KEY` (or without
PHP's `ext-curl`, which `GeminiTriageClient::isConfigured()` also requires),
`SearchEngine` never escalates ambiguous queries — it returns
**"Not supported"** for them rather than a low-confidence guess. That is
intended behaviour, not a failure.

The phase-1 pipeline's inputs and outputs (`Source Excel sheets/`,
`Output Excel Sheets/`, `stage*_checkpoint.jsonl`) are excluded for the same
PII reason. The pipeline scripts themselves (`stage1_classify.py`,
`stage2_escalate.py`, `gemini_common.py`, `build_output.py`) are included, so
the phase is reproducible given the source workbook.

## Deploying to Vercel

The repo ships a `vercel.json` and is laid out for Vercel's community PHP runtime.

**Vercel project settings** — set **Root Directory** to `Education_Dropdown_MVP`.
That is where `vercel.json` lives, and every path inside it is relative to it.
Framework Preset: **Other**. No build command, no install step.

Layout and why:

| Path | Role on Vercel |
| --- | --- |
| `public/` | static site root (`outputDirectory`) — `index.html`, `app.js` |
| `api/*.php` | serverless functions, mounted at `/api/*.php` |
| `php/`, `data/` | bundled into each function via `includeFiles` |
| `router.php` | **local dev only**, ignored by Vercel |

The three endpoints live in `api/`, not `public/`, on purpose: anything under the
static root is handed out verbatim, so `public/data.php` would have served its own
PHP source as a text file. `public/app.js` therefore calls `/api/data.php`,
`/api/generate.php` and `/api/search.php` — root-absolute, so the same URLs work
in both environments. Locally, PHP's built-in server has a single document root
and cannot see `../api`, which is the only thing `router.php` exists to bridge:

```
php -S localhost:8000 -t public router.php
```

### Optional environment variable

`TRIAGE_GEMINI_API_KEY` — set it in Vercel's project settings to enable semantic
escalation for ambiguous search queries. `GeminiTriageClient` reads `getenv()`
before falling back to a local `.env`, so no code change is needed. Left unset,
ambiguous queries return **"Not supported"** rather than a low-confidence guess.
That is intended behaviour (see the two-state confidence design in
`php/SearchEngine.php::evaluate()`).

### What does NOT work on a deployment built from this repo alone

`data/search_index.json` is gitignored (third-party PII — see **Files not in this
repository** above), so Vercel never receives it. The support-triage **search card
will report "Search unavailable"**; the dropdown comment generator is entirely
unaffected. `SearchEngine` treats a missing index as empty rather than crashing,
so this is a switched-off feature, not a 500. To enable search on a deployment,
either commit the index to a **private** repo or supply it another way — but note
it contains real candidate/institution data, so think about who can reach the
deployment URL first.

### Before you share the URL

A Vercel deployment is reachable by anyone who has the link unless you enable
Deployment Protection in project settings. This app exposes internal AuthBridge
comment templates and dropdown wording via `/api/data.php`. That is not PII, but
it is internal content — worth a deliberate decision rather than a default.
