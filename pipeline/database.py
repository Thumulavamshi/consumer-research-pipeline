"""Database module.

Responsible for SQLite schema management and idempotent (INSERT OR IGNORE)
storage of normalized records in the mentions table.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import Column, Float, MetaData, String, Table, create_engine, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine

from . import utils

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("research.db")

metadata = MetaData()

mentions_table = Table(
    "mentions",
    metadata,
    Column("id", String, primary_key=True),
    Column("topic", String, nullable=False),
    Column("source", String),
    Column("author", String),
    Column("title", String),
    Column("text", String),
    Column("url", String),
    Column("created_at", String),
    Column("fetched_at", String),
    Column("sentiment", String),
    Column("sentiment_score", Float),
    Column("category", String),
)


_engines: Dict[Path, Engine] = {}


def _get_engine(db_path: Path = DEFAULT_DB_PATH) -> Engine:
    resolved_path = Path(db_path).resolve()
    if resolved_path not in _engines:
        _engines[resolved_path] = create_engine(f"sqlite:///{resolved_path}")
    return _engines[resolved_path]


def dispose_engine(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Dispose of the connection pool for a specific database path and remove it from cache."""
    resolved_path = Path(db_path).resolve()
    if resolved_path in _engines:
        _engines[resolved_path].dispose()
        del _engines[resolved_path]
        logger.info("Disposed engine for '%s'", resolved_path)


def initialize(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Create the mentions table if it does not already exist."""
    engine = _get_engine(db_path)
    metadata.create_all(engine)
    logger.info("Database initialized at '%s'", db_path)


def insert_records(records: List[Dict[str, Any]], db_path: Path = DEFAULT_DB_PATH) -> int:
    """Insert normalized records, ignoring duplicates by primary key `id`.

    Returns the number of rows actually inserted (duplicates skipped).
    """
    if not records:
        return 0

    engine = _get_engine(db_path)
    inserted = 0

    with engine.begin() as conn:
        for record in records:
            stmt = sqlite_insert(mentions_table).values(**record).prefix_with("OR IGNORE")
            result = conn.execute(stmt)
            if result.rowcount:
                inserted += 1
                logger.info("Inserted record '%s'", record.get("id"))
            else:
                logger.info("Duplicate skipped: '%s'", record.get("id"))

    logger.info("Inserted %s new records (of %s submitted)", inserted, len(records))
    return inserted


def update_classification(records: List[Dict[str, Any]], db_path: Path = DEFAULT_DB_PATH) -> int:
    """Update sentiment, sentiment_score, and category for existing records by id.

    Returns the number of rows updated.
    """
    if not records:
        return 0

    engine = _get_engine(db_path)
    updated = 0

    with engine.begin() as conn:
        for record in records:
            stmt = (
                mentions_table.update()
                .where(mentions_table.c.id == record["id"])
                .values(
                    sentiment=record.get("sentiment"),
                    sentiment_score=record.get("sentiment_score"),
                    category=record.get("category"),
                )
            )
            result = conn.execute(stmt)
            updated += result.rowcount

    logger.info("Updated classification for %s records", updated)
    return updated


def fetch_records(
    topic: Optional[str] = None,
    limit: Optional[int] = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> List[Dict[str, Any]]:
    """Fetch mention records, optionally filtered by topic and capped by limit."""
    engine = _get_engine(db_path)

    stmt = select(mentions_table)
    if topic is not None:
        stmt = stmt.where(mentions_table.c.topic == topic)
    if limit is not None:
        stmt = stmt.limit(limit)

    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()

    return [dict(row) for row in rows]


def count_records(topic: Optional[str] = None, db_path: Path = DEFAULT_DB_PATH) -> int:
    """Return the total number of mention records, optionally filtered by topic."""
    engine = _get_engine(db_path)

    stmt = select(func.count()).select_from(mentions_table)
    if topic is not None:
        stmt = stmt.where(mentions_table.c.topic == topic)

    with engine.connect() as conn:
        return conn.execute(stmt).scalar_one()


if __name__ == "__main__":
    utils.setup_logging()
    initialize()
    logger.info("Total records: %s", count_records())
