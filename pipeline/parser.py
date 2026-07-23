"""Parser / Normalizer module.

Reads cached raw JSON responses from data/raw/ and normalizes them into
standardized record dictionaries ready for storage in SQLite.
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

from . import utils

logger = logging.getLogger(__name__)

_PAGE_NUMBER_RE = re.compile(r"page_(\d+)\.json$")


def _page_number(path: Path) -> int:
    match = _PAGE_NUMBER_RE.search(path.name)
    return int(match.group(1)) if match else 0


def iter_cached_pages(raw_dir: Path = utils.DEFAULT_RAW_DIR) -> Iterator[Tuple[str, Dict[str, Any]]]:
    """Yield (topic, page_payload) for every cached JSON page under raw_dir."""
    if not raw_dir.exists():
        return

    for topic_dir in sorted(p for p in raw_dir.iterdir() if p.is_dir()):
        topic = topic_dir.name
        page_files = sorted(topic_dir.glob("page_*.json"), key=_page_number)
        for page_file in page_files:
            logger.info("Reading cached page '%s' for topic '%s'", page_file.name, topic)
            with open(page_file, "r", encoding="utf-8") as f:
                yield topic, json.load(f)


def normalize_hit(topic: str, hit: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a single raw Algolia hit into a standardized mentions record.

    `sentiment`, `sentiment_score`, and `category` are left unset here; the
    classification stage fills them in after the record is stored.
    """
    return {
        "id": hit.get("objectID"),
        "topic": topic,
        "source": "hackernews",
        "author": hit.get("author"),
        "title": hit.get("title") or hit.get("story_title"),
        "text": hit.get("story_text") or hit.get("comment_text") or "",
        "url": hit.get("url") or hit.get("story_url"),
        "created_at": hit.get("created_at"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "sentiment": None,
        "sentiment_score": None,
        "category": None,
    }


def parse_cached_records(raw_dir: Path = utils.DEFAULT_RAW_DIR) -> List[Dict[str, Any]]:
    """Read every cached raw page under raw_dir and return standardized records."""
    records: List[Dict[str, Any]] = []

    for topic, payload in iter_cached_pages(raw_dir):
        for hit in payload.get("hits", []):
            record = normalize_hit(topic, hit)
            if not record["id"]:
                logger.warning("Skipping hit with no objectID for topic '%s'", topic)
                continue
            records.append(record)

    logger.info("Normalized %s records from cache", len(records))
    return records


def parse(config_path: Path = utils.DEFAULT_CONFIG_PATH) -> List[Dict[str, Any]]:
    """Load raw_cache_dir from config and parse all cached records."""
    config = utils.load_config(config_path)
    raw_dir = Path(config.get("raw_cache_dir", utils.DEFAULT_RAW_DIR))
    return parse_cached_records(raw_dir)


if __name__ == "__main__":
    utils.setup_logging()
    results = parse()
    logger.info("Parse complete: %s total records", len(results))
