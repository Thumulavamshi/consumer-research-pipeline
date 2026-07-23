"""Summarizer module.

Responsible for generating the analyst-friendly summary.md report
from the data stored in SQLite.
"""

import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from . import database, parser

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_PATH = Path("data/summary/summary.md")
TOP_DISCUSSIONS_PER_TOPIC = 5


def _count_duplicates(db_path: Path) -> int:
    """Estimate duplicates skipped by comparing cached raw records to stored records."""
    parsed_count = len(parser.parse())
    stored_count = database.count_records(db_path=db_path)
    return max(parsed_count - stored_count, 0)


def _sentiment_breakdown(records: List[Dict[str, Any]]) -> Counter:
    return Counter(r.get("sentiment") or "Unclassified" for r in records)


def _category_breakdown(records: List[Dict[str, Any]]) -> Counter:
    return Counter(r.get("category") or "Unclassified" for r in records)


def _top_discussions_by_topic(
    records: List[Dict[str, Any]], top_n: int = TOP_DISCUSSIONS_PER_TOPIC
) -> Dict[str, List[Dict[str, Any]]]:
    """Return the most recent `top_n` discussions per topic (by created_at)."""
    by_topic: Dict[str, List[Dict[str, Any]]] = {}
    for record in records:
        by_topic.setdefault(record.get("topic", "Unknown"), []).append(record)

    top_by_topic: Dict[str, List[Dict[str, Any]]] = {}
    for topic, topic_records in by_topic.items():
        sorted_records = sorted(topic_records, key=lambda r: r.get("created_at") or "", reverse=True)
        top_by_topic[topic] = sorted_records[:top_n]

    return top_by_topic


def _generate_observations(records: List[Dict[str, Any]]) -> List[str]:
    """Generate a handful of deterministic, rule-based observations from the data."""
    if not records:
        return ["No records available to analyze."]

    observations: List[str] = []

    topic_counts = Counter(r.get("topic", "Unknown") for r in records)
    most_discussed_topic, most_discussed_count = topic_counts.most_common(1)[0]
    observations.append(
        f"'{most_discussed_topic}' is the most discussed topic with {most_discussed_count} mentions."
    )

    category_counts = _category_breakdown(records)
    top_category, top_category_count = category_counts.most_common(1)[0]
    observations.append(
        f"The most common category overall is '{top_category}' ({top_category_count} records)."
    )

    sentiment_counts = _sentiment_breakdown(records)
    total = len(records)
    negative_pct = (sentiment_counts.get("Negative", 0) / total) * 100
    positive_pct = (sentiment_counts.get("Positive", 0) / total) * 100
    if negative_pct > positive_pct:
        observations.append(
            f"Overall sentiment skews negative ({negative_pct:.1f}% negative vs {positive_pct:.1f}% positive)."
        )
    elif positive_pct > negative_pct:
        observations.append(
            f"Overall sentiment skews positive ({positive_pct:.1f}% positive vs {negative_pct:.1f}% negative)."
        )
    else:
        observations.append("Overall sentiment is evenly balanced between positive and negative.")

    topic_negative_ratio = {}
    for topic in topic_counts:
        topic_records = [r for r in records if r.get("topic") == topic]
        negative = sum(1 for r in topic_records if r.get("sentiment") == "Negative")
        topic_negative_ratio[topic] = negative / len(topic_records) if topic_records else 0

    most_negative_topic = max(topic_negative_ratio, key=topic_negative_ratio.get)
    observations.append(
        f"'{most_negative_topic}' has the highest share of negative sentiment "
        f"({topic_negative_ratio[most_negative_topic] * 100:.1f}%)."
    )

    return observations


def generate_summary(
    db_path: Path = database.DEFAULT_DB_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    """Generate summary.md from records currently stored in SQLite."""
    records = database.fetch_records(db_path=db_path)
    total_records = len(records)
    duplicate_count = _count_duplicates(db_path)

    sentiment_counts = _sentiment_breakdown(records)
    category_counts = _category_breakdown(records)
    top_discussions = _top_discussions_by_topic(records)
    observations = _generate_observations(records)

    lines: List[str] = [
        "# Consumer Research Pipeline Summary",
        "",
        f"- Run timestamp: {datetime.now(timezone.utc).isoformat()}",
        f"- Total records: {total_records}",
        f"- Duplicate count (skipped on insert): {duplicate_count}",
        "",
        "## Sentiment Breakdown",
        "",
    ]
    for sentiment, count in sentiment_counts.most_common():
        lines.append(f"- {sentiment}: {count}")
    lines.append("")

    lines.append("## Category Counts")
    lines.append("")
    for category, count in category_counts.most_common():
        lines.append(f"- {category}: {count}")
    lines.append("")

    lines.append("## Top Discussions per Topic (most recent)")
    lines.append("")
    for topic, topic_records in top_discussions.items():
        lines.append(f"### {topic}")
        lines.append("")
        for record in topic_records:
            title = record.get("title") or "(untitled)"
            url = record.get("url") or ""
            sentiment = record.get("sentiment") or "Unclassified"
            lines.append(f"- [{title}]({url}) — {sentiment}")
        lines.append("")

    lines.append("## Interesting Observations")
    lines.append("")
    for observation in observations:
        lines.append(f"- {observation}")
    lines.append("")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")

    logger.info("Summary generated at '%s'", output_path)
    return output_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    generate_summary()
