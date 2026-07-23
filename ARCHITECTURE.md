# Consumer Research Data Pipeline – Architecture

## Project Goal

Build a small end-to-end Consumer Research Data Pipeline that:

1. Crawls public discussions for configurable AI-related topics.
2. Stores the raw API responses for reproducibility.
3. Normalizes and stores records in SQLite.
4. Classifies each record by sentiment and category.
5. Generates an analyst-friendly summary.
6. Supports incremental, idempotent re-runs.

The project is intentionally designed as a simple production-style ETL pipeline rather than an ML research project.

---

# Technology Stack

Language:
- Python 3.11+

Libraries:
- httpx
- typer
- pyyaml
- sqlalchemy
- pandas
- vaderSentiment
- tenacity
- rich

Database:
- SQLite

Crawler Source:
- Hacker News Algolia Search API

---

# Topics

Configured inside config.yaml.

Default topics:

- OpenAI
- Anthropic
- Google Gemini
- Perplexity
- Cursor

Topics must never be hardcoded.

---

# Folder Structure

consumer-research-pipeline/

    pipeline/
        crawler.py
        parser.py
        database.py
        classifier.py
        summarizer.py
        evaluator.py
        utils.py

    data/
        raw/
        summary/

    logs/

    tests/

    config.yaml
    main.py
    requirements.txt
    README.md

---

# Pipeline Flow

config.yaml

↓

Crawler

↓

Raw JSON Cache

↓

Parser / Normalizer

↓

SQLite

↓

Sentiment Classification

↓

Category Classification

↓

Evaluation

↓

Summary.md

---

# Raw Cache

Every API response is stored before transformation.

Structure:

data/raw/

    OpenAI/

        page_0.json

        page_1.json

    Anthropic/

        page_0.json

The crawler should skip downloading if the cache already exists.

---

# Database

SQLite

Database name:

research.db

Main table:

mentions

Columns

- id (PRIMARY KEY)
- topic
- source
- author
- title
- text
- url
- created_at
- fetched_at
- sentiment
- sentiment_score
- category

Use:

INSERT OR IGNORE

to guarantee idempotency.

---

# Classification

Sentiment

Use VADER.

Output:

- Positive
- Neutral
- Negative

Store both

- sentiment
- sentiment_score

---

Category

Use deterministic keyword rules.

Categories

- Coding Assistant
- General AI
- Research
- Pricing
- Performance
- Privacy
- Enterprise
- Open Source

Do NOT use LLMs.

---

# Evaluation

Hand-label approximately 25 records.

Generate:

- Accuracy
- Confusion Matrix
- Failure Examples

---

# Summary

Generate summary.md containing:

- Run timestamp
- Total crawled
- Total stored
- Duplicate count
- Sentiment distribution
- Category distribution
- Top discussions per topic
- Interesting observations

---

# Logging

Use Python logging.

Every module should log useful progress.

Examples:

- Crawling page...
- Cache hit
- Inserted records
- Duplicate skipped
- Summary generated

---

# Error Handling

Retry transient HTTP failures using exponential backoff.

Do not terminate the pipeline because one topic fails.

Continue processing remaining topics.

---

# One Command

The complete pipeline must execute using

python main.py run

---

# Engineering Principles

- Modular
- Config-driven
- Idempotent
- Incremental
- Re-runnable
- Deterministic
- Easy to understand
- Minimal dependencies

---

# Out of Scope

Do NOT add

- FastAPI
- Docker
- React
- LangChain
- Vector databases
- Cloud deployment
- Authentication
- Multiple data sources

Unless explicitly requested.