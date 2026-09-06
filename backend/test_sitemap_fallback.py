from unittest import TestCase
from unittest.mock import Mock, patch

from scraping.sitemap import crawl_internal_html_links


class SitemapFallbackTests(TestCase):
    def test_internal_crawl_discovers_same_site_pages_only(self):
        pages = {
            "https://example.com": '<a href="/guides/one">One</a><a href="https://other.example/post">Other</a>',
            "https://example.com/guides/one": '<a href="/guides/two">Two</a>',
            "https://example.com/guides/two": "Done",
        }

        def response(url, **kwargs):
            result = Mock()
            result.status_code = 200
            result.url = url
            result.text = pages[url]
            result.headers = {"content-type": "text/html; charset=utf-8"}
            return result

        with patch("scraping.sitemap.requests.get", side_effect=response):
            urls = crawl_internal_html_links("https://example.com", max_urls=10)

        self.assertEqual(urls, list(pages))

