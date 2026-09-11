from unittest import TestCase
import gzip
from unittest.mock import Mock, patch

from scraping.sitemap import (
    MAX_SITEMAP_XML_BYTES,
    _bounded_sitemap_locations,
    crawl_internal_html_links,
    decompress_if_gzip,
)


class SitemapFallbackTests(TestCase):
    def test_gzip_sitemap_expansion_is_memory_bounded(self):
        compressed = gzip.compress(b"x" * (MAX_SITEMAP_XML_BYTES + 1))
        self.assertEqual(decompress_if_gzip(compressed), b"")

    def test_streaming_sitemap_parser_stops_at_requested_url_count(self):
        xml = b"<urlset>" + b"".join(
            f"<url><loc>https://example.com/{index}</loc></url>".encode()
            for index in range(1000)
        ) + b"</urlset>"

        kind, urls = _bounded_sitemap_locations(xml, 12)

        self.assertEqual(kind, "urlset")
        self.assertEqual(len(urls), 12)
        self.assertEqual(urls[-1], "https://example.com/11")

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
