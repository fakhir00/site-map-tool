import asyncio
import json
from unittest import TestCase
from unittest.mock import AsyncMock, patch

from nlp.openrouter import _validate_hub_and_spoke, build_hub_spoke_fallback, cluster_hub_and_spoke
from workers.pipeline import _seed_anchored_keyword_expansions


def spoke(keyword):
    return f"Useful title (Target Keyword: {keyword})"


class HubConstraintTests(TestCase):
    def valid_payload(self):
        return {
            "hubs": [{
                "hub_title": "MASTER HUB",
                "target_keyword": "circuit diagram",
                "layers": {"Strategic articles": [spoke(f"kw {index}") for index in range(1, 11)]},
                "sub_silos": [],
            }]
        }

    def test_valid_map_passes(self):
        allowed = {"circuit diagram", *(f"kw {index}" for index in range(1, 11))}
        self.assertIsNone(_validate_hub_and_spoke(self.valid_payload(), 10, "circuit diagram", allowed))

    def test_plan_requires_ten_to_twenty_flat_spokes(self):
        payload = self.valid_payload()
        payload["hubs"][0]["layers"]["Strategic articles"].pop()
        self.assertIn("10 to 20", _validate_hub_and_spoke(payload, 10, "circuit diagram", {f"kw {i}" for i in range(1, 11)}))
        payload = self.valid_payload()
        self.assertIn("Entity keyword", _validate_hub_and_spoke(
            payload, 10, "circuit diagram", {"circuit diagram", "entity:kw 1", *(f"kw {i}" for i in range(2, 11))}
        ))

    def test_wrong_master_and_duplicate_targets_fail(self):
        payload = self.valid_payload()
        self.assertIn("primary seed", _validate_hub_and_spoke(payload, 10, "network diagram"))
        payload = self.valid_payload()
        payload["hubs"][0]["layers"]["Strategic articles"][1] = spoke("kw 1")
        self.assertIn("Duplicate", _validate_hub_and_spoke(payload, 10, "circuit diagram"))

    def test_cluster_retries_invalid_model_output(self):
        def plan(count):
            return {
                "master_hub": {"article_title": "Circuit Diagram", "target_keyword": "circuit diagram", "targeted_keywords": ["circuit diagram"]},
                "spokes": [{"spoke_category": "Guides", "article_title": f"Article {i}", "target_keyword": f"kw {i}"} for i in range(1, count + 1)],
                "filtered_irrelevant_keywords": [], "total_relevant_keywords_covered": count + 1, "interlinking_strategy": "Loop",
            }
        invalid, valid = plan(9), plan(10)
        keywords = [{"phrase": f"kw {index}", "type": "primary"} for index in range(1, 11)]
        with (
            patch("nlp.openrouter.is_ai_configured", return_value=True),
            patch("nlp.openrouter._achat_json", new=AsyncMock(side_effect=[invalid, valid])) as chat,
        ):
            result = asyncio.run(cluster_hub_and_spoke(keywords, main_keyword="circuit diagram"))
        self.assertEqual(len(result["spokes"]), 10)
        self.assertEqual(sum(len(items) for items in result["hubs"][0]["layers"].values()), 10)
        self.assertEqual(chat.await_count, 2)

    def test_fallback_builds_balanced_unique_constraint_safe_map(self):
        keywords = _seed_anchored_keyword_expansions(["circuit diagram maker"], set(), 100)
        # Add duplicates and entities; they must become H2s rather than URLs.
        keywords.extend([
            {"phrase": "circuit diagram maker tutorials", "type": "long-tail"},
            {"phrase": "electrical standard", "type": "entity"},
        ])
        payload = build_hub_spoke_fallback(keywords, "circuit diagram maker")
        allowed = {
            ("entity:" if item["type"] == "entity" else "") + item["phrase"]
            for item in keywords
        }

        self.assertIsNone(_validate_hub_and_spoke(
            payload, len(keywords), "circuit diagram maker", allowed
        ))
        rendered = json.dumps(payload).lower()
        self.assertIn("include: electrical standard", rendered)

    def test_cluster_uses_fallback_when_ai_is_unavailable(self):
        keywords = _seed_anchored_keyword_expansions(["circuit diagram maker"], set(), 100)
        with patch("nlp.openrouter.is_ai_configured", return_value=False):
            result = asyncio.run(cluster_hub_and_spoke(keywords, main_keyword="circuit diagram maker"))
        self.assertIsNotNone(result)
