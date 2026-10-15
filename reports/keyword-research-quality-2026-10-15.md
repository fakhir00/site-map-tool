# Keyword research and SaaS workflow follow-up — 15 October 2026

The goal is useful, traceable keyword opportunities and a complete content plan:
each useful keyword becomes a page target or a supporting section; existing pages
are improved rather than duplicated. Keyword quantity, distinct page count and
measured search volume are different things. There is no minimum page count.

## Problems fixed in this follow-up

| Problem | Resulting behavior |
| --- | --- |
| A generic positive AI verdict could approve weak terms, including legacy keep-only responses | Every positive decision needs a reader need, missing answer, literal evidence citation and intended placement. Incomplete decisions receive one targeted repair; unchecked rows are withheld. |
| Manual keyword generation explicitly bypassed quality review | Manual generation uses the same review and receives owned-page context and existing-keyword exclusions before generating. |
| Research-provider suggestions bypassed semantic checks if AI was unconfigured | Candidates are withheld with a diagnostic explaining the missing review provider. Metrics alone do not establish relevance or a gap. |
| Keyword findings were dropped by storage/import paths | Competitor, autocomplete, Apify, DataForSEO and AI research retain review notes. Hub Spoke imports and both architecture routes carry those notes forward. |
| Duplicate imports could discard competitor provenance when choosing a record with metrics | Imports merge source domains and retain review notes while keeping the selected measured metrics. |
| Later editorial enrichment overwrote detailed research findings | Enrichment fills missing guidance only. It does not replace reviewed needs and placements, or overwrite measured metrics with AI values. |
| Partial review could look complete when some keywords passed | Completion messaging reports the unreviewed candidate count and preserves accepted results. |
| Users could not see why a keyword was selected | Each keyword with findings has expandable “Why this keyword?” details. |
| Keyword loading, intent, bulk-save/delete and clipboard failures could be silent or misleading | Errors are visible, loading can be retried, and copy success appears only after the clipboard write succeeds. |

The preceding research changes are already present in baseline commit `e845f7a`:
bounded extra searches for sparse results, source-balanced competitor sampling,
observed autocomplete fallback with unknown metrics, full known owned-URL
inventory with bounded scraping, and complete batched candidate accounting.
This follow-up strengthens usefulness checks instead of lowering those safeguards.

Useful related topics one or two semantic hops away remain eligible. Multiple
keywords can share a page. The architecture still independently reviews distinct
intent, existing URL ownership and cannibalization before proposing new pages.

## Verification and limits

- All 47 browser cases passed across the full run and targeted reruns. Four
  existing smoke checks initially hit render-time deadlines under host load and
  passed individually. The new keyword-load regression exposed hidden retries;
  it passed after disabling query retries and synchronizing the test with the
  failed network response.
- Dashboard lint and production build passed. The marketing build produced 11
  pages, with no missing local internal link targets. `git diff --check` passed.
- The final offline backend run passed all **284 tests**. A pre-existing 100 ms
  provider-fallback test was sensitive to host scheduling; its stage clock is now
  controlled while real async cancellation remains tested. The runner disables
  provider credentials and uses isolated test databases.

Reproduce backend checks with `.venvapp/bin/python backend/run_tests.py`. In
`dashboard`, run `npm run lint`, `npm run build`, and `npm run test:browser`
(Chromium or `PLAYWRIGHT_CHROME_PATH` is required). In `marketing`, run
`npm run build`.

A live configured-AI check reviewed 27 previously observed public autocomplete
suggestions against a partial public homepage summary. It accounted for all 27:
20 kept, seven rejected, zero unreviewed, across three requests including repair.
That exercise verifies the review contract, not 20 confirmed gaps or new pages.
The partial context did not establish all existing profile content; some proposed
placements needed the full site inventory. A subsequent prompt refinement makes
explicit that the homepage must not stand in for a missing profile URL.

A fresh fetch of `www.animalsoulquiz.com` failed DNS resolution in this environment.
The live check therefore used previously observed suggestions and a clearly
identified partial summary, not a fresh production crawl. No hosted full scan,
measured-volume increase, final live architecture, or ranking outcome is claimed.
Apify quotas and actual paid-provider credentials remain external dependencies;
autocomplete and AI suggestions never acquire invented volume or difficulty.

## Release acceptance

These changes are local. They do not rewrite historical scans or saved maps.
Deploy the backend and dashboard revisions together, verify the deployed revision
and provider connectivity in Settings, then rerun the affected project and rebuild
its map. Check the source/reader-need explanations, existing-page reuse, supporting
keyword assignments, links, and both writing destinations on that fresh run.

The automated checks cover application workflows with controlled responses. They
do not establish production capacity, provider uptime or that every possible input
is correct. A full hosted scan is still required before calling the hosted SaaS
release accepted.
