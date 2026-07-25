"""Classifier module.

Responsible for sentiment classification (VADER) and deterministic
keyword-rule based category classification of stored records.
"""

import logging
from typing import Any, Dict, List, Tuple

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from . import utils

logger = logging.getLogger(__name__)

_analyzer = SentimentIntensityAnalyzer()

POSITIVE_THRESHOLD = 0.05
NEGATIVE_THRESHOLD = -0.05

DEFAULT_CATEGORY = "General AI"

# Checked in order; the first category whose keyword is found wins.
# DEFAULT_CATEGORY is used when nothing matches.
CATEGORY_KEYWORDS: List[Tuple[str, List[str]]] = [
    (
        "Coding Assistant",
        [
            "copilot", "code assistant", "coding assistant", "code completion",
            "autocomplete", "pair programming", "ide plugin", "code editor",
            "cursor", "code generation",
        ],
    ),
    (
        "Privacy",
        ["privacy", "gdpr", "surveillance", "data collection", "personal data", "tracking"],
    ),
    (
        "Pricing",
        ["pricing", "price", "cost", "subscription", "free tier", "discount", "expensive"],
    ),
    (
        "Performance",
        ["latency", "benchmark", "throughput", "performance", "speed", "slow", "fast", "accuracy"],
    ),
    (
        "Enterprise",
        # NOTE: Targets product/feature enterprise aspects (e.g., compliance, SSO)
        # rather than general corporate/business news (e.g., stock listings, mergers).
        ["enterprise", "b2b", "compliance", "soc 2", "sso", "on-premise", "on-premises", "corporate"],
    ),
    (
        "Open Source",
        ["open source", "open-source", "self-hosted", "mit license", "apache license", "github repo"],
    ),
    (
        "Research",
        ["paper", "research", "arxiv", "study", "dataset", "publication"],
    ),
]


def classify_sentiment(text: str) -> Tuple[str, float]:
    """Classify sentiment of text using VADER. Returns (label, compound score)."""
    scores = _analyzer.polarity_scores(text or "")
    compound = scores["compound"]

    if compound >= POSITIVE_THRESHOLD:
        label = "Positive"
    elif compound <= NEGATIVE_THRESHOLD:
        label = "Negative"
    else:
        label = "Neutral"

    return label, compound


def classify_category(text: str) -> str:
    """Classify text into a category using deterministic keyword rules."""
    lowered = (text or "").lower()

    for category, keywords in CATEGORY_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return category

    return DEFAULT_CATEGORY


def classify_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of record annotated with sentiment, sentiment_score, category."""
    combined_text = " ".join(filter(None, [record.get("title"), record.get("text")]))

    sentiment, sentiment_score = classify_sentiment(combined_text)
    category = classify_category(combined_text)

    classified = dict(record)
    classified["sentiment"] = sentiment
    classified["sentiment_score"] = sentiment_score
    classified["category"] = category

    return classified


def classify_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Classify sentiment and category for a list of records."""
    classified = [classify_record(record) for record in records]
    logger.info("Classified %s records", len(classified))
    return classified


if __name__ == "__main__":
    utils.setup_logging()
    sample = {
        "title": "New pricing for Copilot enterprise plan announced",
        "text": "The new subscription is too expensive for small teams.",
    }
    logger.info("Sample classification: %s", classify_record(sample))
