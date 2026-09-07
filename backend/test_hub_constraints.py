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
        layers = {
            "Foundations": [spoke("kw 1"), spoke("kw 2")],
            "Action": [spoke("kw 3"), spoke("kw 4")],
            "Money": [spoke("kw 5"), spoke("kw 6")],
            "Quick Wins": [spoke("kw 7"), spoke("kw 8")],
        }
        return {
            "hubs": [{
                "hub_title": "MASTER HUB",
                "target_keyword": "circuit diagram",
                "layers": {},
                "sub_silos": [{"hub_title": "Silo", "target_keyword": "circuit basics", "layers": layers}],
            }]
        }

    def test_valid_map_passes(self):
        allowed = {"circuit diagram", "circuit basics", *(f"kw {index}" for index in range(1, 9))}
        self.assertIsNone(_validate_hub_and_spoke(self.valid_payload(), 10, "circuit diagram", allowed))

    def test_underfilled_silo_and_entity_spoke_fail(self):
        payload = self.valid_payload()
        payload["hubs"][0]["sub_silos"][0]["layers"]["Quick Wins"] = []
        self.assertIn("at least 8", _validate_hub_and_spoke(payload, 10, "circuit diagram", {"circuit basics", *(f"kw {i}" for i in range(1, 9))}))
        payload = self.valid_payload()
        self.assertIn("Entity keyword", _validate_hub_and_spoke(
            payload, 10, "circuit diagram", {"circuit diagram", "circuit basics", "entity:kw 1", *(f"kw {i}" for i in range(2, 9))}
        ))

    def test_wrong_master_and_duplicate_targets_fail(self):
        payload = self.valid_payload()
        self.assertIn("primary seed", _validate_hub_and_spoke(payload, 10, "network diagram"))
        payload = self.valid_payload()
        payload["hubs"][0]["sub_silos"][0]["layers"]["Action"][0] = spoke("kw 1")
        self.assertIn("Duplicate", _validate_hub_and_spoke(payload, 10, "circuit diagram"))

    def test_cluster_retries_invalid_model_output(self):
        valid = self.valid_payload()
        invalid = {"hubs": [valid["hubs"][0], {"hub_title": "Another hub", "layers": {}}]}
        keywords = [{"phrase": f"kw {index}", "type": "primary"} for index in range(1, 9)]
        keywords.append({"phrase": "circuit basics", "type": "primary"})
        with (
            patch("nlp.openrouter.is_ai_configured", return_value=True),
            patch("nlp.openrouter._achat_json", new=AsyncMock(side_effect=[invalid, valid])) as chat,
        ):
            result = asyncio.run(cluster_hub_and_spoke(keywords, main_keyword="circuit diagram"))
        self.assertEqual(result, valid)
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
        silos = payload["hubs"][0]["sub_silos"]
        self.assertGreaterEqual(len(silos), 3)
        self.assertTrue(all(sum(len(items) for items in silo["layers"].values()) >= 8 for silo in silos))
        rendered = json.dumps(payload).lower()
        self.assertIn("include h2: electrical standard", rendered)

    def test_cluster_uses_fallback_when_ai_is_unavailable(self):
        keywords = _seed_anchored_keyword_expansions(["circuit diagram maker"], set(), 100)
        with patch("nlp.openrouter.is_ai_configured", return_value=False):
            result = asyncio.run(cluster_hub_and_spoke(keywords, main_keyword="circuit diagram maker"))
        self.assertIsNotNone(result)
