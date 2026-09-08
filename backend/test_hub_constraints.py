import asyncio
import json
from unittest import TestCase
from unittest.mock import AsyncMock, patch

from nlp.openrouter import (
    _deepseek_plan_to_hub_schema,
    _sanitize_detailed_hub_plan,
    _validate_hub_and_spoke,
    build_hub_spoke_fallback,
    cluster_hub_and_spoke,
)
from workers.pipeline import _seed_anchored_keyword_expansions


def spoke(keyword):
    return f"{keyword.title()} (Target Keyword: {keyword})"


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

    def test_validator_rejects_word_order_cannibalization(self):
        payload = self.valid_payload()
        payload["hubs"][0]["layers"]["Strategic articles"][0] = spoke("iron condor vs iron butterfly")
        payload["hubs"][0]["layers"]["Strategic articles"][1] = spoke("iron butterfly vs iron condor")
        allowed = {
            "circuit diagram", "iron condor vs iron butterfly", "iron butterfly vs iron condor",
            *(f"kw {index}" for index in range(3, 11)),
        }
        self.assertIn("Duplicate keyword intent", _validate_hub_and_spoke(
            payload, 10, "circuit diagram", allowed
        ))

    def test_cleanup_removes_irrelevant_and_duplicate_spokes(self):
        keywords = [
            {"phrase": "circuit diagram", "type": "primary"},
            {"phrase": "circuit symbols guide", "type": "long-tail"},
            {"phrase": "guide circuit symbols", "type": "long-tail"},
            {"phrase": "circuit troubleshooting", "type": "long-tail"},
        ]
        raw = {
            "master_hub": {"article_title": "Circuit Diagram", "target_keyword": "circuit diagram"},
            "spokes": [
                {
                    "article_title": "Circuit Symbols Guide",
                    "target_keyword": "circuit symbols guide",
                    "h2_sections": [
                        {"h2_heading": "Circuit troubleshooting", "targeted_keywords_placed_here": ["circuit troubleshooting", "celebrity news"]},
                        {"h2_heading": "Car insurance rates", "targeted_keywords_placed_here": []},
                    ],
                    "faq_schema_questions": [{"question": "Celebrity news today?", "targeted_keywords_placed_here": []}],
                    "entity_terms": ["circuit troubleshooting", "celebrity news"],
                },
                {"article_title": "Reordered Symbols", "target_keyword": "guide circuit symbols"},
                {"article_title": "Circuit Symbols Guide", "target_keyword": "circuit troubleshooting"},
                {"article_title": "Car Insurance Quotes", "target_keyword": "car insurance quotes"},
            ],
        }

        result = _sanitize_detailed_hub_plan(raw, keywords, "circuit diagram")

        self.assertEqual([item["target_keyword"] for item in result["spokes"]], ["circuit symbols guide"])
        self.assertEqual(result["_deduplication_check"]["duplicates_removed"], 2)
        self.assertIn("car insurance quotes", result["filtered_irrelevant_keywords"])
        included = result["spokes"][0]["h2_sections"][0]["targeted_keywords_placed_here"]
        self.assertIn("guide circuit symbols", included)
        self.assertNotIn("celebrity news", included)
        self.assertEqual(result["spokes"][0]["entity_terms"], ["circuit troubleshooting"])
        self.assertEqual(result["spokes"][0]["faq_schema_questions"], [])
        self.assertEqual(len(result["spokes"][0]["h2_sections"]), 1)

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

    def test_detailed_plan_canonicalizes_slugs_and_preserves_keyword_roles(self):
        raw = {
            "master_hub": {
                "article_title": "Circuit Diagram Maker",
                "target_keyword": "Circuit Diagram Maker",
                "slug": "bad slug",
                "page_type": "tool",
                "targeted_keywords": ["circuit drawing platform"],
                "h2_sections": [{
                    "h2_heading": "How it works",
                    "section_definition": "Explain the workflow.",
                    "targeted_keywords_placed_here": ["draw circuit diagrams"],
                }],
                "faq_schema_questions": [{
                    "question": "Is it free?",
                    "targeted_keywords_placed_here": ["free circuit diagram maker"],
                }],
                "entity_terms": ["IEC 60617"],
            },
            "spokes": [{
                "spoke_category": "Tutorials",
                "article_title": f"Article {index}",
                "target_keyword": f"circuit guide {index}",
                "slug": "/same-slug/",
                "page_type": "article",
                "h2_sections": [{
                    "h2_heading": "Practical steps",
                    "section_definition": "Show the process.",
                    "targeted_keywords_placed_here": [f"draw circuit {index}"],
                }],
                "faq_schema_questions": [{
                    "question": "What is required?",
                    "targeted_keywords_placed_here": [f"circuit requirements {index}"],
                }],
                "entity_terms": [f"component {index}"],
            } for index in range(1, 11)],
        }

        result = _deepseek_plan_to_hub_schema(raw, "circuit diagram maker")

        self.assertEqual(result["master_hub"]["slug"], "/circuit-diagram-maker/")
        self.assertTrue(result["master_hub"]["tool_functions"])
        self.assertEqual(result["spokes"][0]["slug"], "/circuit-guide-1/")
        self.assertEqual(result["spokes"][0]["h2_sections"][0]["targeted_keywords_placed_here"], ["draw circuit 1"])
        self.assertEqual(result["spokes"][0]["faq_schema_questions"][0]["targeted_keywords_placed_here"], ["circuit requirements 1"])
        self.assertEqual(result["spokes"][0]["entity_terms"], ["component 1"])
        self.assertIn("free circuit diagram maker", result["hubs"][0]["h2_keywords"])
        self.assertIn("iec 60617", result["hubs"][0]["h2_keywords"])
