"""Consumer Research Data Pipeline CLI.

Wires config loading, crawling, parsing, storage, classification,
summarization, and evaluation into a single `run` command.
"""

import logging
from pathlib import Path

import typer

from pipeline import classifier, crawler, database, evaluator, parser, summarizer

app = typer.Typer()

logger = logging.getLogger("pipeline.main")

CONFIG_PATH = Path("config.yaml")
LABELS_CSV_PATH = Path("data/summary/labels_template.csv")


def _setup_logging() -> None:
    Path("logs").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler("logs/pipeline.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


@app.callback()
def callback():
    pass


@app.command()
def run():
    """Run the full Consumer Research Data Pipeline end to end."""
    _setup_logging()
    logger.info("Pipeline Started")

    # Load Config
    try:
        config = crawler.load_config(CONFIG_PATH)
    except Exception:
        logger.exception("Failed to load config.yaml; aborting pipeline")
        raise typer.Exit(code=1)

    logger.info("Loaded config with %s topics", len(config.get("topics") or []))

    # Crawl -> Cache
    try:
        crawler.crawl(CONFIG_PATH)
    except Exception:
        logger.exception("Crawl stage failed; continuing with whatever is already cached")

    # Parse
    try:
        records = parser.parse(CONFIG_PATH)
    except Exception:
        logger.exception("Parse stage failed; no records available for this run")
        records = []

    # SQLite
    try:
        database.initialize()
        inserted = database.insert_records(records)
        total = database.count_records()
        logger.info("Inserted %s new records (%s parsed, %s total in DB)", inserted, len(records), total)
    except Exception:
        logger.exception("Database stage failed; aborting pipeline")
        raise typer.Exit(code=1)

    # Classification
    try:
        classified = classifier.classify_records(records)
        updated = database.update_classification(classified)
        logger.info("Updated classification for %s records", updated)
    except Exception:
        logger.exception("Classification stage failed; stored records may be missing sentiment/category")

    # Summary
    try:
        summary_path = summarizer.generate_summary()
        logger.info("Summary generated at '%s'", summary_path)
    except Exception:
        logger.exception("Summary stage failed")

    # Evaluation
    try:
        if LABELS_CSV_PATH.exists():
            eval_path = evaluator.evaluate(LABELS_CSV_PATH)
            logger.info("Evaluation report generated at '%s'", eval_path)
        else:
            template_path = evaluator.export_labeling_template()
            logger.info(
                "No hand-labeled file found at '%s'; wrote a fresh labeling template to '%s'. "
                "Fill in true_sentiment/true_category and re-run to evaluate.",
                LABELS_CSV_PATH,
                template_path,
            )
    except Exception:
        logger.exception("Evaluation stage failed")

    logger.info("Pipeline complete")


if __name__ == "__main__":
    app()
