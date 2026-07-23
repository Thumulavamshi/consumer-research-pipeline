"""Crawler module.

Responsible for crawling public discussions (Hacker News Algolia Search API)
for configurable topics and caching raw API responses under data/raw/.

This stage owns fetching and caching only. Normalizing the cached JSON into
storage-ready records is the parser's responsibility (see parser.py).
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from . import utils

logger = logging.getLogger(__name__)

ALGOLIA_SEARCH_URL = "https://hn.algolia.com/api/v1/search"
REQUEST_TIMEOUT_SECONDS = 10

DEFAULT_HITS_PER_PAGE = 25
DEFAULT_MAX_PAGES = 3
DEFAULT_DELAY_SECONDS = 1.0


def _raw_page_path(topic: str, page: int, raw_dir: Path) -> Path:
    return raw_dir / topic / f"page_{page}.json"


def _is_retryable_error(exc: BaseException) -> bool:
    """Retry on network-level failures and on rate-limit/server errors (429, 5xx)."""
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return False


@retry(
    reraise=True,
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    retry=retry_if_exception(_is_retryable_error),
)
def _fetch_page(client: httpx.Client, topic: str, page: int, hits_per_page: int) -> Dict[str, Any]:
    logger.info("Crawling page %s for topic '%s'", page, topic)
    response = client.get(
        ALGOLIA_SEARCH_URL,
        params={
            "query": topic,
            "tags": "story",
            "page": page,
            "hitsPerPage": hits_per_page,
        },
    )
    response.raise_for_status()
    return response.json()


def _load_or_fetch_page(
    client: httpx.Client,
    topic: str,
    page: int,
    hits_per_page: int,
    raw_dir: Path,
    delay_seconds: float,
) -> Dict[str, Any]:
    """Return the cached page if present, otherwise fetch, cache, and rate-limit."""
    cache_path = _raw_page_path(topic, page, raw_dir)

    if cache_path.exists():
        logger.info("Cache hit for topic '%s' page %s", topic, page)
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)

    payload = _fetch_page(client, topic, page, hits_per_page)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    if delay_seconds > 0:
        time.sleep(delay_seconds)

    return payload


def crawl_topic(
    client: httpx.Client,
    topic: str,
    hits_per_page: int,
    max_pages: int,
    delay_seconds: float,
    raw_dir: Path,
) -> int:
    """Crawl and cache all pages for a topic. Returns the number of hits cached."""
    hit_count = 0

    for page in range(max_pages):
        payload = _load_or_fetch_page(client, topic, page, hits_per_page, raw_dir, delay_seconds)

        hits = payload.get("hits", [])
        hit_count += len(hits)

        if not hits:
            break

        total_pages = payload.get("nbPages", page + 1)
        if page + 1 >= total_pages:
            break

    logger.info("Cached %s hits for topic '%s'", hit_count, topic)
    return hit_count


def crawl(config_path: Path = utils.DEFAULT_CONFIG_PATH) -> int:
    """Crawl and cache every configured topic. Returns the total number of hits cached."""
    config = utils.load_config(config_path)

    topics = config.get("topics") or []
    crawler_config = config.get("crawler") or {}

    hits_per_page = crawler_config.get("hits_per_page", DEFAULT_HITS_PER_PAGE)
    max_pages = crawler_config.get("max_pages", DEFAULT_MAX_PAGES)
    delay_seconds = crawler_config.get("delay_seconds", DEFAULT_DELAY_SECONDS)
    raw_dir = Path(config.get("raw_cache_dir", utils.DEFAULT_RAW_DIR))

    total_hits = 0

    headers = {"User-Agent": "ConsumerResearchPipeline/1.0 (contact: info@example.com)"}
    with httpx.Client(headers=headers, timeout=REQUEST_TIMEOUT_SECONDS) as client:
        for topic in topics:
            try:
                total_hits += crawl_topic(client, topic, hits_per_page, max_pages, delay_seconds, raw_dir)
            except Exception:
                logger.exception("Failed to crawl topic '%s', skipping", topic)
                continue

    return total_hits


if __name__ == "__main__":
    utils.setup_logging()
    total = crawl()
    logger.info("Crawl complete: %s total hits cached", total)
