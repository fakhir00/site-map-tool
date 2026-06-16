import unittest
import uuid

from workers import pipeline


class PipelineHelperTests(unittest.TestCase):
    def test_extract_google_result_urls_preserves_organic_order(self):
        html = """
        <html>
          <body>
            <div id="search">
              <div class="g"><a href="/url?q=https%3A%2F%2Ffirst.example%2Ftool&sa=U">First</a></div>
              <div class="g"><a href="https://www.google.com/search?q=skip">Skip</a></div>
              <div class="g"><a href="/url?q=https%3A%2F%2Fsecond.example%2Fguide&sa=U">Second</a></div>
              <div class="g"><a href="https://www.youtube.com/watch?v=skip">Blocked</a></div>
              <div class="g"><a href="https://third.example/resources">Third</a></div>
            </div>
          </body>
        </html>
        """

        self.assertEqual(
            pipeline._extract_google_result_urls(html, max_results=3),
            [
                "https://first.example/tool",
                "https://second.example/guide",
                "https://third.example/resources",
            ],
        )

    def test_ai_refinement_preserves_competitor_url_evidence(self):
        source_url_id = uuid.uuid4()
        accumulator = {
            "old-slug template": {
                "type": "primary",
                "count": 1,
                "url_ids": {source_url_id},
                "source": "sitemap",
            }
        }

        refined = pipeline._build_ai_refined_accumulator(
            accumulator,
            [
                {
                    "source_phrase": "old-slug template",
                    "phrase": "old slug template",
                    "type": "long-tail",
                }
            ],
            topic_terms={"old", "template"},
        )

        self.assertEqual(set(refined.keys()), {"old slug template"})
        self.assertEqual(refined["old slug template"]["type"], "long-tail")
        self.assertEqual(refined["old slug template"]["count"], 1)
        self.assertEqual(refined["old slug template"]["url_ids"], {source_url_id})


if __name__ == "__main__":
    unittest.main()
