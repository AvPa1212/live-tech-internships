import datetime as dt
import json
import unittest
from unittest.mock import patch

from scripts import update


class ExpirationTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 11, 24, tzinfo=dt.timezone.utc)

    def normalize(self, expires=None):
        with patch.object(update, "NOW", self.now):
            return update.normalize(
                source="test",
                company="Example",
                title="Software Intern",
                location="Remote",
                url="https://example.com/job",
                posted=None,
                expires=expires,
            )

    def test_expired_deadline_excludes_listing(self):
        self.assertIsNone(self.normalize("2026-11-23"))

    def test_deadline_today_and_future_remain_listed(self):
        self.assertIsNotNone(self.normalize("2026-11-24"))
        self.assertIsNotNone(self.normalize("2026-11-25"))

    def test_missing_or_unparseable_deadline_does_not_exclude_listing(self):
        self.assertIsNotNone(self.normalize())
        self.assertIsNotNone(self.normalize("not a date"))

    def test_jsonld_valid_through_filters_expired_listing(self):
        postings = [
            {
                "@type": "JobPosting",
                "title": f"Software Intern {deadline}",
                "url": f"https://example.com/{deadline}",
                "datePosted": "2026-11-01",
                "validThrough": deadline,
            }
            for deadline in ("2026-11-23", "2026-11-25")
        ]
        text = (
            '<script type="application/ld+json">'
            + json.dumps(postings)
            + "</script>"
        )

        with patch.object(update, "NOW", self.now):
            jobs = update.parse_jsonld("Example Careers", text)

        self.assertEqual([job["url"] for job in jobs], ["https://example.com/2026-11-25"])

    def test_repo_source_deadline_filters_expired_listing(self):
        payload = {
            "closed": {
                "company": "Example",
                "title": "Closed Intern",
                "url": "https://example.com/closed",
                "deadline": "2026-11-23",
            },
            "open": {
                "company": "Example",
                "title": "Open Intern",
                "url": "https://example.com/open",
                "deadline": "2026-11-25",
            },
        }

        with patch.object(update, "NOW", self.now):
            jobs = update.parse_repo("Example", "zshah", payload)

        self.assertEqual([job["url"] for job in jobs], ["https://example.com/open"])


if __name__ == "__main__":
    unittest.main()
