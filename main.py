"""Consumer Research Data Pipeline CLI.

Wires config loading, crawling, parsing, storage, classification,
evaluation, and summarization into a single `run` command, following the
stage order defined in ARCHITECTURE.md:

    Configuration -> Crawl -> Raw Cache -> Parse -> SQLite
    -> Classification -> Evaluation -> Summary
"""

import logging

import typer

from pipeline import classifier, crawler, database, evaluator, parser, summarizer, utils

app = typer.Typer()

logger = logging.getLogger("pipeline.main")


@app.callback()
def callback():
    pass


@app.command()
def run():
    """Run the full Consumer Research Data Pipeline end to end."""
    utils.setup_logging()
    logger.info("Pipeline Started")

    # Configuration
    try:
        config = utils.load_config()
    except Exception:
        logger.exception("Failed to load config.yaml; aborting pipeline")
        raise typer.Exit(code=1)

    logger.info("Loaded config with %s topics", len(config.get("topics") or []))

    # Crawl -> Raw Cache
    try:
        crawler.crawl()
    except Exception:
        logger.exception("Crawl stage failed; continuing with whatever is already cached")

    # Parse
    try:
        records = parser.parse()
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

    # Evaluation
    try:
        if evaluator.DEFAULT_LABELS_TEMPLATE_PATH.exists():
            eval_path = evaluator.evaluate(evaluator.DEFAULT_LABELS_TEMPLATE_PATH)
            logger.info("Evaluation report generated at '%s'", eval_path)
        else:
            template_path = evaluator.export_labeling_template()
            logger.info(
                "No hand-labeled file found at '%s'; wrote a fresh labeling template to '%s'. "
                "Fill in true_sentiment/true_category and re-run to evaluate.",
                evaluator.DEFAULT_LABELS_TEMPLATE_PATH,
                template_path,
            )
    except Exception:
        logger.exception("Evaluation stage failed")

    # Summary
    try:
        summary_path = summarizer.generate_summary()
        logger.info("Summary generated at '%s'", summary_path)
    except Exception:
        logger.exception("Summary stage failed")

    logger.info("Pipeline complete")


if __name__ == "__main__":
    app()
