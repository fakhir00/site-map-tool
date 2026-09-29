# Hub Spoke workspace rebuild — 29 September 2026

The workspace now treats a topical map as a set of distinct reader tasks, real pages, and directed links. Topic groups organize those pages; they do not automatically create another URL. The main topic is explicit and editable. A numerical page target is a planning preference, not a quality or ranking score.

## What changed

- Replaced the standalone workspace's string-parsed lists with a shared, inspectable map view. It offers topic groups, a page list, directed links, keyword decisions, search, format/evidence filters, and a page inspector.
- Added paste input, scan selection, an editable homepage keyword, and declared existing URLs alongside CSV/TXT uploads. CSV rows with missing source columns no longer crash the upload.
- Each new plan includes stable page IDs, topic-group membership, parent references, and a link plan with source URL, destination URL, suggested anchor, and relationship. Invalid/circular parents fall back to the main hub with visible review notes.
- Page briefs include reader outcome, scope, exclusions, and section headings. Writing and tool-building handoffs retain the selected brief and source project. The writing prompt receives the architecture requirements.
- The authority planner preserves the reviewed page format. Unknown volume no longer forces an interactive task into an article. Same-task articles can be consolidated even if their intent labels differ.
- Consolidation prefers an existing page and retains useful headings and incoming/outgoing links. Supporting keywords with a named section or question go there; unspecified placements remain page-level rather than all being pushed into the first H2.
- Removed full replanning triggered solely by a page-count shortfall, and removed the arbitrary minimum of three topic categories in authority mode. Structurally valid short plans are returned with their research shortfall.
- Bounded discovery and individual reviews to 45 seconds, limited repair/review rounds, and added a four-minute generation deadline. Late reviews use the remaining budget so a structurally valid draft can return with review-needed status. The browser shows elapsed time without pretending to know provider progress.
- Added a 300-distinct-keyword limit, including the main topic, before generation. Larger uploads can be edited down in the workspace. This avoids promising a complete disposition of thousands of keywords within a single bounded response.
- Preserved saved history, including older maps with only hub/layer labels. Editing inputs marks the displayed map as a previous result. A failed rebuild retains that map, and controls are locked during a build.
- Added JSON map, internal-link CSV, keyword-list, and architecture-brief exports. Existing URL links use the exact preserved URL.

## Validation

Final test results are recorded below after the verification run.

The regression coverage includes exact keyword placement, graph references, cycles, URL reuse, main-topic selection, format preservation, intent consolidation, shortfalls, input bounds, saved-plan ownership, and brief propagation. Browser checks exercise generation, exports, filters, keyboard navigation, phone layout, historical data, failed rebuilds, CSV edge cases, and writer/tool handoffs.

Backend provider responses and browser APIs are controlled fixtures. No live provider generation, production deployment, or ranking outcome is claimed. Screenshots in `dashboard/test-results/topical-map-desktop.png` and `topical-map-mobile.png` use clearly synthetic fixtures and are local review artifacts.

## Operating limits

- Build one focused subject at a time, with at most 300 distinct input keywords. The default target remains 25 spokes; the map can return fewer when distinct tasks do not justify more.
- Project crawl context still uses up to 30 successfully scraped owned pages and bounded excerpts. Declared URLs are user-provided inventory, not proof that their content was crawled or assessed. Partial coverage cannot establish absence across a whole site.
- Semantic decisions depend on the configured AI provider. Editorial proposals remain unverified demand hypotheses; unknown metrics stay unknown. An unavailable review remains visibly incomplete.
- Keep the generation tab open. Generation is a bounded request, not a durable background job. A completed map is saved to history, but an in-flight request is not guaranteed to survive a server restart.
- Older saved maps are displayed compatibly, without inventing an audit result or regenerating their contents. Rebuild them to receive the new page briefs and explicit graph metadata.
- Backend and dashboard changes are local. Deployment is still needed before hosted behavior changes.

The planning approach follows Google's guidance on [helpful, people-first content](https://developers.google.com/search/docs/fundamentals/creating-helpful-content) and [crawlable links with descriptive anchors](https://developers.google.com/search/docs/crawling-indexing/links-crawlable). These support useful content and navigation; they do not establish a guaranteed topical-authority score or ranking outcome.
