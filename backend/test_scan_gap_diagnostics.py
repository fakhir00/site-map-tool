import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from workers.pipeline import _competitor_gap_completion_message, _process_competitor_keyword_gaps


class GapDiagnosticTests(unittest.TestCase):
    def run_stage(self, *, page_count=2, extracted=None, reviewed=None, covered=False):
        db = MagicMock()
        db.execute.return_value.scalar.return_value = page_count
        db.execute.return_value.scalars.return_value.all.return_value = [
            SimpleNamespace(url='https://own.example/', h1='Age tool', scraped_text='Lunar age calculator')]
        source_id = uuid.uuid4()
        db.execute.return_value.all.return_value = [(source_id, 'https://competitor.example', 'https://competitor.example/age')]
        candidate = {'phrase': 'lunar age calculator', 'url_ids': [str(source_id)]}
        extracted = [candidate] if extracted is None else extracted
        reviewed = [candidate] if reviewed is None else reviewed
        stats = {}
        with patch('workers.pipeline._store_keywords') as store, patch(
            'workers.pipeline._own_content_keyword_phrases', return_value={'lunar age calculator'} if covered else set()
        ):
            count = _process_competitor_keyword_gaps(
                db, uuid.uuid4(), ['lunar age calculator'], {'lunar', 'age'}, set(), '',
                MagicMock(return_value=extracted), MagicMock(return_value=reviewed), MagicMock(), MagicMock(),
                diagnostics=stats,
            )
            self.assertEqual(store.called, bool(count))
        return stats, count

    def test_zero_scraped_pages_is_a_scraping_outcome(self):
        stats, count = self.run_stage(page_count=0)
        self.assertEqual(stats['outcome'], 'no_scraped_pages')
        message = _competitor_gap_completion_message(count, ['competitor.example'], stats, [])
        self.assertIn('scrape errors', message)

    def test_empty_extraction_is_not_an_ai_rejection(self):
        stats, _ = self.run_stage(extracted=[])
        self.assertEqual(stats['outcome'], 'no_candidates')
        self.assertEqual(stats['scraped_pages'], 2)

    def test_successful_empty_review_does_not_suggest_provider_failure(self):
        stats, count = self.run_stage(reviewed=[])
        self.assertEqual(stats['outcome'], 'review_rejected')
        self.assertEqual(stats['relevant_candidates'], 1)
        message = _competitor_gap_completion_message(count, ['competitor.example'], stats, [])
        self.assertIn('No additional uncovered opportunities were confirmed', message)
        self.assertNotIn('provider', message.lower())
        self.assertNotIn('retry', message.lower())

    def test_final_phrase_rejection_is_identified(self):
        stats, _ = self.run_stage(reviewed=[{'phrase': 'age korean age'}])
        self.assertEqual(stats['outcome'], 'quality_rejected')
        self.assertEqual(stats['reviewed_candidates'], 1)
        self.assertEqual(stats['quality_candidates'], 0)

    def test_covered_candidates_are_not_a_research_failure(self):
        stats, count = self.run_stage(covered=True)
        self.assertEqual(stats['outcome'], 'already_covered')
        self.assertEqual(stats['covered_candidates'], 1)
        message = _competitor_gap_completion_message(count, ['competitor.example'], stats, [])
        self.assertIn('already represented', message)
        self.assertNotIn('limited', message)

    def test_success_records_counts_and_has_no_warning(self):
        stats, count = self.run_stage()
        self.assertEqual(stats['stored_gaps'], 1)
        self.assertIsNone(_competitor_gap_completion_message(count, ['competitor.example'], stats, []))

    def test_discovery_and_legacy_results_do_not_invent_a_stage(self):
        self.assertIn('search unavailable', _competitor_gap_completion_message(0, [], {}, ['search unavailable']))
        self.assertIn('diagnostics are unavailable', _competitor_gap_completion_message(0, ['competitor.example'], {}, []))

    def test_valid_search_with_no_matching_pages_does_not_blame_provider_status(self):
        message = _competitor_gap_completion_message(0, [], {}, [
            'Apify returned 30 organic results; 4 candidate sites; none had enough matching page evidence'])
        self.assertIn('Review the seed keywords and site scope', message)
        self.assertNotIn('provider status', message)
