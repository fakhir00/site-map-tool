import unittest
from unittest.mock import patch

from app.goldhunter.scraper import fetch_url_content


class _Response:
    url = "https://www.example.com/"
    text = """
    <html><head><title>Diagram Tools</title><meta name="description" content="Build diagrams"></head>
    <body><nav><a href="/circuit-tool#demo">Circuit Tool</a></nav>
    <main><h1>Diagram Maker</h1><a href="https://example.com/exporter">PNG Exporter</a>
    <a href="https://outside.example/tool">Unrelated External Tool</a><p>Drag and drop components.</p></main></body></html>
    """

    def raise_for_status(self):
        return None


class _Client:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, *_args, **_kwargs):
        return _Response()


class GoldHunterScraperTests(unittest.IsolatedAsyncioTestCase):
    async def test_scraper_preserves_same_site_linked_tool_evidence(self):
        with patch("app.goldhunter.scraper.httpx.AsyncClient", return_value=_Client()):
            content = await fetch_url_content("https://example.com")

        self.assertIn("Circuit Tool: https://www.example.com/circuit-tool", content)
        self.assertIn("PNG Exporter: https://example.com/exporter", content)
        self.assertNotIn("Unrelated External Tool: https://outside.example/tool", content)
        self.assertIn("Drag and drop components", content)


if __name__ == "__main__":
    unittest.main()
