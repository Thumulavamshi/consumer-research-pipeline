import unittest
from pathlib import Path
from pipeline import classifier, database

class TestPipeline(unittest.TestCase):
    def test_sentiment_classification(self):
        # Test positive sentiment
        label, score = classifier.classify_sentiment("This product is amazing and fast!")
        self.assertEqual(label, "Positive")
        self.assertGreater(score, 0.05)

        # Test negative sentiment
        label, score = classifier.classify_sentiment("This service is slow and buggy, terrible experience.")
        self.assertEqual(label, "Negative")
        self.assertLess(score, -0.05)

        # Test neutral sentiment
        label, score = classifier.classify_sentiment("OpenAI is an AI company.")
        self.assertEqual(label, "Neutral")
        self.assertTrue(-0.05 < score < 0.05)

    def test_category_classification(self):
        # Coding Assistant
        self.assertEqual(classifier.classify_category("Using Cursor editor for pair programming"), "Coding Assistant")
        # Pricing
        self.assertEqual(classifier.classify_category("The new subscription price is too expensive"), "Pricing")
        # Performance
        self.assertEqual(classifier.classify_category("The latency benchmark shows it is slow"), "Performance")
        # Default
        self.assertEqual(classifier.classify_category("Some random text about something else"), "General AI")

    def test_database_idempotency(self):
        test_db = Path("test_research.db")
        if test_db.exists():
            test_db.unlink()

        try:
            # Initialize
            database.initialize(test_db)
            self.assertEqual(database.count_records(db_path=test_db), 0)

            # Insert raw records
            records = [
                {
                    "id": "1",
                    "topic": "OpenAI",
                    "source": "hackernews",
                    "author": "user1",
                    "title": "OpenAI news",
                    "text": "some text",
                    "url": "http://example.com",
                    "created_at": "2026-07-23T12:00:00Z",
                    "fetched_at": "2026-07-23T12:00:00Z",
                    "sentiment": None,
                    "sentiment_score": None,
                    "category": None,
                },
                {
                    "id": "2",
                    "topic": "Anthropic",
                    "source": "hackernews",
                    "author": "user2",
                    "title": "Anthropic release",
                    "text": "some other text",
                    "url": "http://example.com/2",
                    "created_at": "2026-07-23T12:01:00Z",
                    "fetched_at": "2026-07-23T12:01:00Z",
                    "sentiment": None,
                    "sentiment_score": None,
                    "category": None,
                }
            ]

            inserted = database.insert_records(records, db_path=test_db)
            self.assertEqual(inserted, 2)
            self.assertEqual(database.count_records(db_path=test_db), 2)

            # Insert duplicates (should be skipped)
            inserted_again = database.insert_records(records, db_path=test_db)
            self.assertEqual(inserted_again, 0)
            self.assertEqual(database.count_records(db_path=test_db), 2)

            # Classification update
            classified = classifier.classify_records(records)
            updated = database.update_classification(classified, db_path=test_db)
            self.assertEqual(updated, 2)

            # Verify updated values
            fetched = database.fetch_records(db_path=test_db)
            self.assertEqual(len(fetched), 2)
            for r in fetched:
                self.assertIsNotNone(r["sentiment"])
                self.assertIsNotNone(r["category"])

        finally:
            database.dispose_engine(test_db)
            if test_db.exists():
                test_db.unlink()

if __name__ == "__main__":
    unittest.main()
