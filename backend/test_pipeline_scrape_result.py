from types import SimpleNamespace
import unittest

from scraping.crawler import ScrapedPage
from workers.pipeline import _apply_scrape_result


def _url_record(url="https://example.com/blog/example-post"):
    return SimpleNamespace(
        url=url,
        status="pending",
        error_reason=None,
        scraped_text="",
        h1=None,
        word_count=None,
        readability_score=None,
        publish_date=None,
        scraped_at=None,
    )


class PipelineScrapeResultTest(unittest.TestCase):
    def test_scraped_page_keeps_text_content_alias_in_sync(self):
        page = ScrapedPage(url="https://example.com", text="initial copy")

        self.assertEqual(page.text_content, "initial copy")

        page.text_content = "updated copy"

        self.assertEqual(page.text, "updated copy")

    def test_apply_scrape_result_marks_successful_pages_scraped(self):
        record = _url_record()
        result = ScrapedPage(
            url=record.url,
            h1="Example Post",
            text="Useful page copy for analysis.",
            word_count=5,
            readability_score=61.5,
        )

        self.assertIs(_apply_scrape_result(record, result), True)
        self.assertEqual(record.status, "scraped")
        self.assertIsNone(record.error_reason)
        self.assertEqual(record.scraped_text, "Useful page copy for analysis.")
        self.assertEqual(record.h1, "Example Post")
        self.assertEqual(record.word_count, 5)
        self.assertEqual(record.readability_score, 61.5)
        self.assertIsNotNone(record.scraped_at)

    def test_apply_scrape_result_marks_error_pages_failed(self):
        record = _url_record("https://example.com/blog/broken-post")
        result = ScrapedPage(url=record.url, error="Request timeout", status_code=0)

        self.assertIs(_apply_scrape_result(record, result), False)
        self.assertEqual(record.status, "failed")
        self.assertEqual(record.error_reason, "Request timeout")
        self.assertEqual(record.scraped_text, "")
        self.assertEqual(record.h1, "Broken")
        self.assertIsNotNone(record.scraped_at)

    def test_apply_scrape_result_marks_empty_pages_failed(self):
        record = _url_record()
        result = ScrapedPage(url=record.url, h1="Empty Page", text="")

        self.assertIs(_apply_scrape_result(record, result), False)
        self.assertEqual(record.status, "failed")
        self.assertEqual(record.error_reason, "No readable text extracted")


    def test_compute_readability_bounded(self):
        from scraping.crawler import compute_readability
        self.assertEqual(compute_readability(""), 0.0)
        self.assertEqual(compute_readability("short"), 0.0)
        # Verify it handles large text without issue
        huge_text = "The quick brown fox jumps over the lazy dog. " * 500
        score = compute_readability(huge_text)
        self.assertIsInstance(score, float)

    def test_extract_publish_date_ignores_excessive_strings(self):
        from bs4 import BeautifulSoup
        from scraping.crawler import extract_publish_date
        html = '<meta property="article:published_time" content="' + ('x' * 200) + '">'
        soup = BeautifulSoup(html, "html.parser")
        self.assertIsNone(extract_publish_date(soup))


if __name__ == "__main__":
    unittest.main()
