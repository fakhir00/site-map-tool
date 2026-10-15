# Topical-authority workflow repair

> Historical implementation note. The fixed 25-spoke target described below has
> been removed. Current planning has no minimum or target URL count and preserves
> useful supporting keywords within pages. See
> [the current keyword-quality follow-up](keyword-research-quality-2026-10-15.md).

The intended output is one homepage plus roughly 20–30 distinct supporting blogs, reference pages and tools. Existing pages belong in the map as pages to improve. A related keyword is not automatically a new URL; a brief mention on an existing page does not automatically exhaust a deeper instructional intent.

## Failures found

| Failure | Effect | Change |
|---|---|---|
| Old page minimum used the square root of inventory size | 70 keywords encouraged only nine total pages | Production build routes now request 25 spokes, with a 20–30 planning range, excluding the homepage |
| Architect could use only supplied keyword targets | Missing topics could never enter the map | Added bounded topic discovery grounded in exact supplied keyword evidence; proposals receive a separate evidence label and no invented volume or difficulty |
| Automatic page promotion and word-overlap reassignment | Could create pages just to satisfy a count and override meaningful semantic assignments | Authority mode preserves reviewed intent assignments and reports a shortfall instead of promoting variants |
| Generic instructional wording was treated as a brand prefix | `how to calculate lunar age` was discarded | Restricted that heuristic to product/review entities; regression reproduced the loss of this spoke before the fix |
| Tool classification keyed on the word “calculator” | `lunar age calculator accuracy` was incorrectly turned into a tool | Accuracy, errors, mistakes and troubleshooting queries retain informational intent; a regression reproduced this before the fix |
| Gap filtering treated a served topic too broadly | A homepage summary could eliminate a distinct deep guide | Coverage filtering now distinguishes full task satisfaction from mentions, summaries and adjacent topics |
| Architecture did not receive the owned-page crawl inventory | Existing tools could be planned again at new URLs | Both production routes attach owned-page excerpts and preserve supplied existing URLs; maps label create versus update |
| Output did not report completion against the user's goal | A tiny map looked like a completed authority plan | UI/export show actual spokes, target range, new/existing counts, and research/review status |

## Current behavior

1. Import Gap Hunter keywords or upload a keyword file and site context.
2. Choose the desired spoke target; default 25 means a 20–30 range. The homepage is additional.
3. Propose missing tasks across instructional, comparison, reference, troubleshooting and tool intents. Exact evidence citations establish input grounding, not measured demand.
4. Have the architect evaluate both supplied keywords and new proposals, consolidating same-intent variations and preserving distinct tasks.
5. Review relevance and overlapping intents, then attach existing URLs and verify structural consistency again.
6. Return a map with create/update actions and evidence labels. If a sufficiently large inventory produces a small first map, make one bounded replanning attempt. If distinct intents remain insufficient, report the shortfall; do not pad the map.

A shortfall is not a successful 25-spoke plan. An unavailable semantic review produces `needs_review`. Proposed topics remain editorial hypotheses even when semantic review passes. Keyword count, page count, and Google authority are different measurements.

## Validation

Final verification: **95 tests passed**, dashboard production build passed, and `git diff --check` passed.

- The regression suite covers expansion evidence, rejection of unsupported proposals, unknown metrics, a 25-spoke full orchestration fixture, existing URL reuse, hub/spoke links, insufficient evidence without filler, unavailable discovery/review, API target propagation, and owned-page context.
- Existing architecture, pipeline filtering, CSV export, and project workflow regressions are also included.
- Tests use controlled provider responses; the 25-spoke fixture verifies orchestration, not live keyword demand or actual Google rankings.
- A real run using the original 70-keyword CSV, a partial manually summarized owned-page inventory, and the configured DeepSeek provider was attempted. It failed with HTTP 402, `Insufficient Balance`. No live generated plan is claimed.
- Owned-page input is bounded to 30 successfully scraped pages with 3,000 characters per page. Uploaded lists without a project require the user to supply existing-page context. A partial crawl cannot prove absence across the entire website.
- Changes are local and require deployment before the hosted tool changes. Rebuild the architecture to use the new planner; saved historical maps remain historical results.

Google recommends helpful, reliable, people-first content and useful internal links. A numerical page target is a practical planning aid, not a ranking guarantee: [Google Search Essentials](https://developers.google.com/search/docs/essentials) and [helpful content guidance](https://developers.google.com/search/docs/fundamentals/creating-helpful-content).
