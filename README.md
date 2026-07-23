# Consumer Research Data Pipeline

A small, production-style ETL pipeline that crawls public discussion data for
configurable AI-industry topics, stores it durably, classifies it, and turns
it into an analyst-readable report — with one command.

```bash
python main.py run
```

---

## Project Overview

Product and research teams that track how an AI company or product is being
received publicly usually start the same way: someone manually searches
Hacker News, skims a few dozen threads, and writes up impressions by hand.
That doesn't scale, isn't repeatable, and leaves no audit trail of what data
the conclusions were based on.

This pipeline automates that first pass. It pulls public discussion threads
for a configurable set of topics, stores the raw data so results are
reproducible, classifies each mention by sentiment and category using
deterministic methods (no LLM calls, no external API costs, fully
repeatable), and produces a Markdown summary an analyst can read in under a
minute.

The five default topics — **OpenAI, Anthropic, Google Gemini, Perplexity,
Cursor** — were chosen because they span the current AI landscape in a way
that's useful for cross-topic comparison: two frontier model labs
(OpenAI, Anthropic), a challenger with a different product bet (Google
Gemini), an AI-native search product (Perplexity), and a developer tool
built on top of these models (Cursor). None of this is hardcoded — topics
live entirely in `config.yaml`, so the same pipeline works for any other set
of companies or products.

This is deliberately an **ETL pipeline, not an ML research project**. Every
classification decision is a rule a human can read and predict; nothing here
is a trained model or a prompt to a hosted LLM.

---

## Architecture

```
Configuration
     |
     v
   Crawler  ---------> polls Hacker News Algolia Search API per topic, paginated
     |
     v
 Raw Cache  ---------> every API response saved as JSON before any transformation
     |
     v
   Parser   ---------> reads the cache, normalizes hits into a consistent record shape
     |
     v
   SQLite   ---------> INSERT OR IGNORE into `mentions`, keyed by stable id
     |
     v
Classification ------> VADER sentiment + keyword-rule category, written back by id
     |
     v
 Evaluation  --------> compares predictions to a small hand-labeled sample
     |
     v
  Summary    --------> data/summary/summary.md, an analyst-facing report
```

**Why this order matters:** raw data is written to disk *before* any
parsing happens, and parsed records are written to SQLite *before*
classification runs. Each stage's output is durable before the next stage
starts. That's what makes the whole thing safe to re-run: if classification
crashes halfway through, the raw cache and the unclassified rows are still
there, and re-running the pipeline just picks up where it left off instead
of re-fetching or re-inserting anything.

### Stage by stage

1. **Configuration** — `config.yaml` is the single source of truth for
   topics and crawl parameters. Nothing pipeline-specific is hardcoded in
   code.
2. **Crawler** — for each topic, pages through the Hacker News Algolia
   Search API, retrying transient failures with exponential backoff and
   pausing briefly between real requests.
3. **Raw Cache** — every page response is written to
   `data/raw/<topic>/page_<n>.json` verbatim, before any parsing. If a page
   is already cached, the crawler skips it entirely — no network call, no
   wasted quota.
4. **Parser** — reads whatever is in the raw cache (not just what was
   crawled in this run) and normalizes each hit into a flat record matching
   the database schema.
5. **SQLite** — normalized records are inserted with `INSERT OR IGNORE`,
   keyed on the Hacker News `objectID`. Re-running never creates duplicates.
6. **Classification** — sentiment (VADER) and category (keyword rules) are
   computed in memory and written back onto the stored rows by id.
7. **Evaluation** — if a hand-labeled sample exists, compares it against
   stored predictions and reports accuracy, a confusion matrix, and failure
   examples. If not, generates a sample for you to label.
8. **Summary** — reads the final state of the database and writes
   `data/summary/summary.md`.

---

## Project Structure

```
consumer-research-pipeline/
├── pipeline/
│   ├── crawler.py       # fetch + cache raw API responses (no parsing)
│   ├── parser.py        # cache -> normalized records
│   ├── database.py      # SQLite schema, insert/update/fetch/count helpers
│   ├── classifier.py    # sentiment (VADER) + category (keyword rules)
│   ├── evaluator.py     # hand-label sampling + accuracy/confusion matrix
│   ├── summarizer.py    # normalized DB state -> summary.md
│   └── utils.py         # shared config loading + logging setup
├── data/
│   ├── raw/              # cached raw JSON, one folder per topic (gitignored)
│   └── summary/          # generated summary.md, evaluation.md, labels CSV (gitignored)
├── logs/                 # pipeline.log, appended across runs (gitignored)
├── tests/                # reserved for future automated tests (currently empty)
├── config.yaml            # topics + crawl parameters — the only place to edit behavior
├── main.py                 # Typer CLI; `python main.py run` executes the full pipeline
├── requirements.txt
├── ARCHITECTURE.md         # the design spec this implementation follows
└── README.md
```

`research.db` (the SQLite database) is created at the repo root on first run
and is gitignored, like everything else the pipeline generates.

---

## Technology Stack

| Technology | Why this and not something else |
|---|---|
| **Python 3.11+** | Matches the assessment's target runtime; no reason to reach for anything else for a script-scale ETL job. |
| **SQLite** | Zero-setup, file-based, transactional, and more than sufficient for a few hundred to a few thousand rows. No server to run or credentials to manage. |
| **Hacker News Algolia API** | Public, free, documented, no auth required, and explicitly built for third-party search — a genuinely ToS-friendly source, unlike scraping a site that doesn't want to be scraped. |
| **VADER (vaderSentiment)** | A lexicon-based sentiment scorer tuned for short, informal, social-style text — a much better fit for HN titles/comments than a model trained on formal prose, and it's deterministic and free to run. |
| **Keyword rules (category)** | Explicit requirement: categories must be deterministic and auditable, not LLM-inferred. A human can read the rule and predict the output. |
| **Typer** | Thin, typed CLI layer over `argparse`/click patterns; gives `python main.py run` for free with almost no boilerplate. |
| **httpx** | Modern, typed HTTP client with a clean timeout/client model; used purely for the crawler's HTTP calls. |
| **SQLAlchemy (Core, not ORM)** | Parameterized SQL without hand-writing string interpolation, and native support for SQLite's `INSERT OR IGNORE` via `sqlite_insert(...).prefix_with("OR IGNORE")`. Core (not the ORM) because a single flat table doesn't need object-relational mapping — that would be over-engineering for this schema. |
| **tenacity** | Declarative retry/backoff instead of hand-rolled `for attempt in range(...)` loops around HTTP calls. |
| **rich** | Used for readable, leveled console logging output (`RichHandler`) during a pipeline run — the log file still gets plain-text lines for grepping/archival. |
| **pandas** | Used narrowly in `evaluator.py` for `crosstab`-based confusion matrices — the one place tabular aggregation genuinely earns its keep. |
| **PyYAML** | Parses `config.yaml`. |

---

## Data Pipeline

**ETL flow:** Extract (crawler pages through the API), Transform (parser
normalizes raw JSON into the `mentions` schema, classifier derives
sentiment/category), Load (SQLite, in two writes — an initial insert, then a
classification update by id).

**Caching:** every raw API response is saved to
`data/raw/<topic>/page_<n>.json` before it's touched. The crawler checks for
that file first and skips the HTTP request entirely if it's already there.
This means re-running the pipeline after a partial or complete first run
only fetches pages that were never successfully cached — nothing is
re-downloaded. (Caveat: the cache key is the page number only, not the page
size — see [Tradeoffs](#tradeoffs).)

**Idempotency:** re-running `python main.py run` end-to-end is always safe.
Cached pages aren't re-fetched, `INSERT OR IGNORE` means an already-stored
record is never duplicated, and classification is a pure function of
`title`/`text` — reclassifying an existing row just writes back the same
value. Verified directly: two consecutive full runs against the same cache
produced `Inserted 371 new records` then `Inserted 0 new records`, with the
total row count unchanged.

**Incremental execution:** each stage reads from the previous stage's
durable output (cache, then DB), not from in-memory state carried over from
an earlier stage in the same process. That means you can run the crawler
today, add it to tomorrow's cache with a wider `max_pages`, and the parser
will pick up everything that's accumulated in `data/raw/` — not just what
was fetched in the most recent run.

**Duplicate handling:** a hit can appear more than once across topic
queries (e.g. an article mentioning both "OpenAI" and "Anthropic" surfaces
under both topic searches). `INSERT OR IGNORE` on the primary key silently
drops the second occurrence, and `summary.md` reports how many were dropped
this way.

---

## Database Schema

SQLite database `research.db`, single table `mentions`:

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT, **PRIMARY KEY** | Hacker News `objectID` — see below for why. |
| `topic` | TEXT, NOT NULL | Which configured topic this record was found under. |
| `source` | TEXT | Always `"hackernews"` today; kept as a column so a second source could be added without a schema change. |
| `author` | TEXT | HN username of the poster. |
| `title` | TEXT | Story title. |
| `text` | TEXT | Story/comment body, when present (often empty for link posts). |
| `url` | TEXT | Link the story points to. |
| `created_at` | TEXT | ISO timestamp from Hacker News — when the item was originally posted. |
| `fetched_at` | TEXT | ISO timestamp of when *this pipeline* normalized the record. |
| `sentiment` | TEXT | `Positive` / `Neutral` / `Negative`, filled in by the classification stage. `NULL` until then. |
| `sentiment_score` | REAL | VADER compound score, `-1.0` to `1.0`. |
| `category` | TEXT | One of the 8 fixed categories (see [Classification](#classification)). |

**Why `objectID` as the primary key:** it's a stable identifier issued by
Hacker News itself, not something the pipeline derives. Two different runs
of the crawler — today, tomorrow, or after `max_pages` changes — see the
same `objectID` for the same story. That's exactly the property a
dedup key needs: idempotency has to be based on something the *source*
guarantees is stable, not something computed locally (a hash of the title
would break the moment a title got edited on HN).

**Why `INSERT OR IGNORE`:** it turns "insert if new, do nothing if it
already exists" into a single atomic statement instead of a
select-then-conditionally-insert race. Combined with the stable primary
key, it's what makes the whole pipeline safe to re-run without a separate
"have I seen this before?" check anywhere in application code.

---

## Classification

**Sentiment** — VADER's `polarity_scores()` compound score on
`title + " " + text`. Standard VADER thresholds: `>= 0.05` → Positive,
`<= -0.05` → Negative, otherwise Neutral. Both the label and the raw
compound score are stored, so downstream consumers can re-bucket with a
different threshold without re-running sentiment analysis.

**Category** — an ordered list of keyword rules, checked in a fixed
precedence (Coding Assistant → Privacy → Pricing → Performance → Enterprise
→ Open Source → Research), with **General AI** as the fallback when nothing
matches. The order matters where text could plausibly match more than one
category — e.g. "Copilot pricing announced" matches both `Coding Assistant`
and `Pricing` keywords, and precedence resolves it deterministically toward
the more specific category.

**Why deterministic rules instead of an LLM:** three concrete reasons,
beyond "the spec says so." First, **auditability** — a hiring engineer (or
an analyst) can open `classifier.py` and know exactly why any record got
its label, instead of trusting an opaque model. Second, **reproducibility**
— the same input always produces the same output, forever, with no model
version drift. Third, **cost and dependency footprint** — zero API calls,
zero API keys, zero latency, and the entire pipeline stays runnable offline
once the cache is warm.

---

## Evaluation

Classification quality is checked against a small human-labeled sample,
not a held-out test set — this is a rule-based system, not a trained model,
so the goal is closer to "does this look right to a person" than a
train/test split.

1. `evaluator.export_labeling_template()` samples ~25 records, spread
   evenly across topics (fixed random seed, so the sample is reproducible),
   and writes `data/summary/labels_template.csv` with each record's id,
   title, and the pipeline's current predictions, plus two empty columns:
   `true_sentiment` and `true_category`.
2. A human fills in those two columns by hand for as many rows as they
   want to judge (blank rows are skipped, not treated as failures).
3. `evaluator.evaluate()` reads the filled CSV, looks up each row's
   predicted values from the database by id, and computes:
   - **Accuracy** — correct / total labeled.
   - **Confusion matrix** — a `true x predicted` cross-tab (via
     `pandas.crosstab`), separately for sentiment and category.
   - **Failure examples** — every mismatch, with the record's title, so a
     reviewer can see *what kind* of text is fooling the classifier.

Run automatically by `python main.py run`: if a labels file already exists,
it's evaluated; if not, a fresh template is generated so the next run (after
you've labeled it) produces a real report.

**Limitations, stated plainly:** 25 labeled records is a small sample —
accuracy on it is indicative, not statistically rigorous. The sample is
stratified by topic but not by predicted class, so a class that's rare in
the data (e.g. `Privacy`, 2 records in a typical run) may get zero coverage
in any given 25-record sample. This is a deliberate scope tradeoff for a
time-boxed assessment, not an oversight — a production version would
stratify by predicted class too, or grow the sample size.

---

## Summary Output

`python main.py run` (or `summarizer.generate_summary()` directly) writes
`data/summary/summary.md`, containing:

- **Run timestamp** — when this summary was generated (UTC).
- **Total records** — current row count in `mentions`.
- **Duplicate count** — records seen in the current cache that were already
  in the database (i.e., what `INSERT OR IGNORE` silently dropped).
- **Sentiment breakdown** — count per Positive/Neutral/Negative.
- **Category counts** — count per one of the 8 categories.
- **Top discussions per topic** — the 5 most recent (by `created_at`)
  stored discussions per topic, linked, with their sentiment label.
- **Interesting observations** — a handful of rule-based, computed-not-
  generated observations: the most-discussed topic, the most common
  category, whether overall sentiment skews positive or negative, and which
  topic has the highest share of negative sentiment.

Everything in this file is computed directly from aggregate counts — no
text generation, no LLM, nothing that isn't traceable to a specific number
in the database.

---

## Tradeoffs

Honest engineering discussion, written the way I'd want a reviewer to see
it rather than glossed over:

- **"Top discussions" is a proxy, not a popularity ranking.** The `mentions`
  schema (as specified in `ARCHITECTURE.md`) doesn't include a points/score
  or comment-count column, even though the Algolia API returns one. Rather
  than silently adding a column outside the specified schema, "top" is
  implemented as "most recent" and labeled that way in the output. A real
  popularity ranking would need a schema change, which felt like a bigger
  decision than this assessment's time budget warranted without checking
  in first.
- **Cache keys don't encode crawl parameters.** `data/raw/<topic>/page_<n>.json`
  is keyed on page number only, per the architecture spec. If you change
  `hits_per_page` after already having cached pages, the crawler will
  happily serve the old, differently-sized cached page instead of
  re-fetching — I hit this directly during development (see git history)
  and worked around it by clearing `data/raw/` after a config change.
  There's no built-in cache invalidation for this; it's a manual step today.
- **Duplicate count is a derived estimate, not a tracked counter.** It's
  computed as `(records currently in cache) - (records currently in DB)`
  at summary time, rather than accumulated as insert/duplicate events
  happen. This is correct in the common case but conflates "duplicates from
  this run" with "records still sitting in the cache from a run whose
  insert never happened" — an edge case, not the normal path.
- **Inserts and classification updates are row-by-row, not batched.** Both
  `insert_records()` and `update_classification()` execute one SQL
  statement per record inside a single transaction, rather than one bulk
  `executemany`. This was a deliberate choice: the architecture explicitly
  asks for per-record log lines (`Inserted record`, `Duplicate skipped`),
  which a bulk statement can't produce. At this dataset's scale (hundreds
  of rows) the performance difference is not observable; it would matter
  at tens of thousands of rows.
- **Evaluation requires a human in the loop.** There's no way around this
  for a rule-based classifier with no held-out ground truth — the pipeline
  auto-generates the labeling template so the loop is as short as possible,
  but a fresh clone's first run will show a 0-sample evaluation report
  until someone actually labels the CSV.

---

## Setup

### Requirements

- Python 3.11+
- Internet access (only needed for uncached crawl requests — the pipeline
  runs fully offline once `data/raw/` is populated)

### Installation

```bash
python -m venv .venv
```

```bash
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
```

### Configuration

Edit `config.yaml` to change topics or crawl behavior — nothing needs to be
touched in code:

```yaml
topics:
  - OpenAI
  - Anthropic
  - Google Gemini
  - Perplexity
  - Cursor

crawler:
  hits_per_page: 25   # Algolia results per page
  max_pages: 3         # cap per topic (keeps a full run inside ~50–150 items/topic)
  delay_seconds: 1.0    # pause between real (non-cached) requests

raw_cache_dir: data/raw
```

---

## Usage

### Run the full pipeline

```bash
python main.py run
```

This executes every stage — config load, crawl, parse, store, classify,
evaluate, summarize — and logs progress to both the console and
`logs/pipeline.log`.

### Re-run it

```bash
python main.py run
```

Same command. Already-cached pages aren't re-fetched, already-stored
records aren't re-inserted, and classification is recomputed but produces
identical values for unchanged text — so a second run is fast and leaves
the database in the same state, just with a fresh `summary.md`.

### How the cache behaves

- First run: `Crawling page 0 for topic 'OpenAI'` — an HTTP request is made
  and the response is written to `data/raw/OpenAI/page_0.json`.
- Every run after: `Cache hit for topic 'OpenAI' page 0` — no HTTP request,
  the file is read straight off disk.
- To force a re-crawl (e.g. after changing `hits_per_page` or wanting fresh
  data), delete the relevant folder under `data/raw/` — or all of it — and
  re-run.

### Where outputs land

| Output | Path |
|---|---|
| Raw cached API responses | `data/raw/<topic>/page_<n>.json` |
| SQLite database | `research.db` (repo root) |
| Analyst summary | `data/summary/summary.md` |
| Evaluation report | `data/summary/evaluation.md` |
| Hand-labeling template | `data/summary/labels_template.csv` |
| Run log | `logs/pipeline.log` (appended across runs) |

### Evaluating classification quality

```bash
python main.py run              # generates data/summary/labels_template.csv if missing
```

Open that CSV, fill in `true_sentiment` and/or `true_category` for as many
rows as you'd like to judge, then:

```bash
python main.py run              # now scores against your labels
```

### Running an individual stage

Every stage can also be run on its own (useful for debugging or
inspecting intermediate state) via `python -m`, since the modules use
package-relative imports:

```bash
python -m pipeline.crawler
python -m pipeline.parser
python -m pipeline.database
python -m pipeline.classifier
python -m pipeline.evaluator
python -m pipeline.summarizer
```

---

## Sample Outputs

### `data/summary/summary.md` (excerpt)

```markdown
# Consumer Research Pipeline Summary

- Run timestamp: 2026-07-23T11:15:54.736283+00:00
- Total records: 371
- Duplicate count (skipped on insert): 4

## Sentiment Breakdown

- Neutral: 197
- Negative: 89
- Positive: 85

## Category Counts

- General AI: 268
- Coding Assistant: 77
- Research: 9
- Open Source: 7
- Pricing: 5
- Enterprise: 2
- Privacy: 2
- Performance: 1

## Interesting Observations

- 'Anthropic' is the most discussed topic with 75 mentions.
- The most common category overall is 'General AI' (268 records).
- Overall sentiment skews negative (24.0% negative vs 22.9% positive).
- 'Google Gemini' has the highest share of negative sentiment (32.0%).
```

### `logs/pipeline.log` (excerpt)

```
2026-07-23 16:44:57,802 INFO pipeline.main: Loaded config with 5 topics
2026-07-23 16:44:59,735 INFO pipeline.database: Inserted 371 new records (of 375 submitted)
2026-07-23 16:44:59,735 INFO pipeline.main: Inserted 371 new records (375 parsed, 371 total in DB)
2026-07-23 16:45:00,002 INFO pipeline.database: Updated classification for 375 records
2026-07-23 16:45:00,086 INFO pipeline.summarizer: Summary generated at 'data\summary\summary.md'
2026-07-23 16:45:00,086 INFO pipeline.main: Pipeline complete
```

### Database (excerpt, via `database.fetch_records(limit=1)`)

```python
{
    'id': '46124267',
    'topic': 'Anthropic',
    'source': 'hackernews',
    'author': 'ryanvogel',
    'title': 'Anthropic acquires Bun',
    'text': '',
    'url': 'https://bun.com/blog/bun-joins-anthropic',
    'created_at': '2025-12-02T18:05:44Z',
    'fetched_at': '2026-07-23T11:14:58.785687+00:00',
    'sentiment': 'Neutral',
    'sentiment_score': 0.0,
    'category': 'General AI',
}
```

### `data/summary/evaluation.md` (example, after hand-labeling 25 records)

```markdown
## Sentiment

- Sample size: 25
- Correct: 24
- Accuracy: 96.00%

### Confusion Matrix

predicted  Negative  Neutral  Positive
true
Negative          4        1         0
Neutral           0       15         0
Positive          0        0         5

### Failure Examples

- id=48364055 | true=Negative | predicted=Neutral | "Can the stockmarket swallow Anthropic, SpaceX and OpenAI?"
```

---

## Design Decisions

- **Crawler and parser are fully separate stages, not one combined step.**
  The crawler's only job is "fetch and cache"; the parser's only job is
  "read cache and normalize." This mirrors `ARCHITECTURE.md`'s own stage
  boundary and means the parser can be re-run against an accumulated cache
  without touching the network at all — useful for iterating on
  normalization logic without re-crawling.
- **Classification writes back to already-inserted rows, rather than
  classifying before the first insert.** `ARCHITECTURE.md`'s pipeline
  diagram places SQLite *before* Classification. Making that literally true
  required one small addition to `database.py` —
  `update_classification()` — instead of quietly reordering the stages to
  "classify, then insert" (which would have been easier but wouldn't match
  the spec). Raw normalized data lands in SQLite first, unmodified;
  classification enriches it afterward. This also means classification can
  be re-run and improved later without re-crawling or re-parsing anything.
- **SQLAlchemy Core, not the ORM.** One flat table with no relationships
  doesn't need object mapping — Core gives parameterized SQL and
  `INSERT OR IGNORE` support without a layer of abstraction the schema
  doesn't need.
- **`utils.py` holds only what's genuinely shared.** Config loading and
  logging setup were duplicated near-verbatim across `crawler.py` and
  `parser.py` early on; both now import a single implementation from
  `utils.py`. Nothing was added there that only one module uses.
- **Stable IDs over locally-derived ones.** See
  [Database Schema](#database-schema) — `objectID` from Hacker News, not a
  hash computed by this pipeline, is what makes `INSERT OR IGNORE`
  actually idempotent across runs, machines, and time.

---

## Future Improvements

Kept realistic — things that would matter at the next size of problem, not
speculative features:

- **Batch DB writes** (`executemany`) once record volume grows past what a
  per-row loop comfortably handles, with a coarser "N inserted / M skipped"
  log line replacing the current per-record one.
- **Cache invalidation keyed on crawl parameters**, not just page number,
  so changing `hits_per_page`/`max_pages` doesn't require manually clearing
  `data/raw/`.
- **A real popularity signal** (HN points/comment count) added to the
  schema, so "top discussions" ranks by engagement instead of recency.
- **Stratify the evaluation sample by predicted class**, not just by topic,
  so rare categories reliably get coverage in the 25-record sample.
- **A minimal automated test suite** under `tests/` (currently an empty,
  reserved directory) — unit tests for the keyword-rule categorizer and the
  idempotency of `insert_records`/`update_classification` would be the
  highest-value first tests.

Explicitly **not** planned, per `ARCHITECTURE.md`'s own scope boundary:
FastAPI, Docker, a database beyond SQLite, LLM-based classification, or
additional data sources beyond Hacker News.

---

## Time Spent

Implemented incrementally, module by module, over several sessions:
scaffold and crawler (~1.5h), parser and database (~1h), classifier (~45m),
summarizer and evaluator (~1.5h), full pipeline wiring in `main.py` (~45m),
and this end-to-end review/refactor/documentation pass (~2h). Roughly
**7–8 hours** total, which is consistent with a focused
internship-assessment time budget rather than a production hardening pass —
see [Tradeoffs](#tradeoffs) for what that budget did and didn't cover.
