"""Evaluator module.

Responsible for evaluating classification quality against a small
hand-labeled sample: accuracy, confusion matrix, and failure examples.
"""

import csv
import logging
import random
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from . import database, utils

logger = logging.getLogger(__name__)

DEFAULT_LABELS_TEMPLATE_PATH = Path("data/summary/labels_template.csv")
DEFAULT_EVAL_OUTPUT_PATH = Path("data/summary/evaluation.md")
DEFAULT_SAMPLE_SIZE = 25
SAMPLE_SEED = 42


def export_labeling_template(
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    output_path: Path = DEFAULT_LABELS_TEMPLATE_PATH,
    db_path: Path = database.DEFAULT_DB_PATH,
) -> Path:
    """Sample records (spread evenly across topics) and write a CSV for hand-labeling.

    The analyst fills in `true_sentiment` and `true_category` for each row.
    """
    all_records = database.fetch_records(db_path=db_path)
    if not all_records:
        raise ValueError("No records found in the database to sample from")

    by_topic: Dict[str, List[Dict[str, Any]]] = {}
    for record in all_records:
        by_topic.setdefault(record.get("topic", "Unknown"), []).append(record)

    rng = random.Random(SAMPLE_SEED)
    for bucket in by_topic.values():
        rng.shuffle(bucket)

    topics = list(by_topic.keys())
    sample: List[Dict[str, Any]] = []
    index = 0
    while len(sample) < min(sample_size, len(all_records)):
        topic = topics[index % len(topics)]
        bucket = by_topic[topic]
        if bucket:
            sample.append(bucket.pop())
        index += 1

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "title",
                "url",
                "predicted_sentiment",
                "predicted_category",
                "true_sentiment",
                "true_category",
            ],
        )
        writer.writeheader()
        for record in sample:
            writer.writerow(
                {
                    "id": record.get("id"),
                    "title": record.get("title"),
                    "url": record.get("url"),
                    "predicted_sentiment": record.get("sentiment"),
                    "predicted_category": record.get("category"),
                    "true_sentiment": "",
                    "true_category": "",
                }
            )

    logger.info("Labeling template with %s records written to '%s'", len(sample), output_path)
    return output_path


def _load_labels(csv_path: Path) -> pd.DataFrame:
    return pd.read_csv(csv_path, dtype=str).fillna("")


def evaluate_label(
    csv_path: Path,
    label: str,
    db_path: Path = database.DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """Evaluate predicted vs. hand-labeled `sentiment` or `category`.

    Expects the CSV to have an `id` column and a `true_<label>` column.
    Predicted values are looked up from the database by id.
    """
    if label not in ("sentiment", "category"):
        raise ValueError("label must be 'sentiment' or 'category'")

    true_column = f"true_{label}"
    labels_df = _load_labels(csv_path)

    if "id" not in labels_df.columns or true_column not in labels_df.columns:
        raise ValueError(f"CSV must contain 'id' and '{true_column}' columns")

    records_by_id = {record["id"]: record for record in database.fetch_records(db_path=db_path)}

    y_true: List[str] = []
    y_pred: List[str] = []
    failures: List[Dict[str, Any]] = []

    for _, row in labels_df.iterrows():
        record_id = row["id"]
        true_value = row[true_column].strip()

        if not true_value:
            continue

        record = records_by_id.get(record_id)
        if record is None:
            logger.warning("No stored record found for id '%s', skipping", record_id)
            continue

        predicted_value = record.get(label) or ""

        y_true.append(true_value)
        y_pred.append(predicted_value)

        if true_value != predicted_value:
            failures.append(
                {
                    "id": record_id,
                    "title": record.get("title"),
                    "true": true_value,
                    "predicted": predicted_value,
                }
            )

    total = len(y_true)
    correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    accuracy = correct / total if total else 0.0

    confusion_matrix = pd.crosstab(
        pd.Series(y_true, name="true"),
        pd.Series(y_pred, name="predicted"),
    )

    logger.info("Evaluated %s labeled records for '%s': accuracy=%.3f", total, label, accuracy)

    return {
        "label": label,
        "total": total,
        "correct": correct,
        "accuracy": accuracy,
        "confusion_matrix": confusion_matrix,
        "failures": failures,
    }


def _format_report(results: List[Dict[str, Any]]) -> str:
    lines: List[str] = ["# Classification Evaluation", ""]

    for result in results:
        lines.append(f"## {result['label'].capitalize()}")
        lines.append("")
        lines.append(f"- Sample size: {result['total']}")
        lines.append(f"- Correct: {result['correct']}")
        lines.append(f"- Accuracy: {result['accuracy']:.2%}")
        lines.append("")
        lines.append("### Confusion Matrix")
        lines.append("")
        lines.append("```")
        lines.append(result["confusion_matrix"].to_string())
        lines.append("```")
        lines.append("")
        lines.append("### Failure Examples")
        lines.append("")
        if result["failures"]:
            for failure in result["failures"][:10]:
                lines.append(
                    f"- id={failure['id']} | true={failure['true']} | "
                    f"predicted={failure['predicted']} | \"{failure['title']}\""
                )
        else:
            lines.append("- No misclassifications found.")
        lines.append("")

    return "\n".join(lines)


def evaluate(
    csv_path: Path,
    labels: Optional[List[str]] = None,
    db_path: Path = database.DEFAULT_DB_PATH,
    output_path: Path = DEFAULT_EVAL_OUTPUT_PATH,
) -> Path:
    """Evaluate one or more label types found in the hand-labeled CSV and write a report."""
    labels_df = _load_labels(csv_path)

    if labels is None:
        labels = [label for label in ("sentiment", "category") if f"true_{label}" in labels_df.columns]

    if not labels:
        raise ValueError("CSV has neither 'true_sentiment' nor 'true_category' columns")

    results = [evaluate_label(csv_path, label, db_path=db_path) for label in labels]
    report = _format_report(results)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")

    logger.info("Evaluation report written to '%s'", output_path)
    return output_path


if __name__ == "__main__":
    import sys

    utils.setup_logging()

    if len(sys.argv) > 1:
        evaluate(Path(sys.argv[1]))
    else:
        export_labeling_template()
