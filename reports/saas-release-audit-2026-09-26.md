# SaaS release audit — 26 September 2026

## Production finding

The public Render health endpoint returned `status: ok`, `database: connected`,
and **revision `0f49dec`**. The checkout started this audit at **`c566caa`**.
Render therefore lacks the later authority-planning and detailed scan-outcome
changes already in this repository. The owner confirmed Render uses manual
deployment. This explains why the previous warning can persist after local fixes;
it does not establish why the original hosted scan accepted no competitor keywords.

The Vercel dashboard returned HTTP 200 and its JavaScript bundle points at
`https://site-map-tool.onrender.com/api`. The first Render health request timed out;
a subsequent request succeeded. That observation alone does not identify a cause.

No production account, scan records, Render logs, or deployment controls were
accessed. Changes from this audit are local and have not been deployed.

## Confirmed defects repaired

| Area | Failure | Change |
|---|---|---|
| AI requests | The old fallback could select the same failing provider again; JSON requests had no provider failover | Shared synchronous/asynchronous provider fallback, correct per-provider models, sanitized errors and a 60-second failure cooldown |
| Provider visibility | Settings omitted AI balance/access failures | Authenticated passive status plus an explicit small connection test; backend revision displayed |
| API errors | Some failed AI calls became empty successful results | Keyword generation and website prompts propagate provider-unavailable errors; API returns an actionable 503 |
| Keyword metrics | AI-generated volume/difficulty could replace measured fields | DeepSeek provides editorial guidance only; measured fields are preserved |
| Completion warning | Messages containing DataForSEO were hidden | Stored completion diagnostics remain visible |
| Counts | Stats counted synthetic AI/provider rows as crawled pages | Stats count actual owned and competitor pages |
| Pagination | Zero page size could reach invalid pagination calculations | API rejects page sizes below one |
| Account switch | Cached previous-account data could remain in the UI | Query cache cleared on logout, login and registration |
| Saved keywords | Failed updates were silent; copy announced success before completion | API failures are displayed, clipboard writes are awaited, and clipboard rejection is explained |
| Gold Hunter | Failed project creation was not displayed | Project-creation errors appear in the existing error panel |
| Blog creation | A spoke's originating project was lost in navigation | Project ID is preserved through navigation and article creation |
| Long AI operations | Several generation actions used the short request timeout | Those actions use the existing AI request timeout |
| Website prompts | Error paths referenced an undefined logger; backend-only deployment omitted the root theme file; empty output could succeed | Logger defined, theme bundled with backend, empty generation rejected |
| Gap-page templates | A deterministic template was labeled audit score 100 | Score is null and UI shows “Not audited” |
| Marketing contact | Form submitted a placeholder provider key and accepted HTTP success without checking application success | Configured public form key and response validation; visible email fallback when unconfigured |
| Dashboard dependencies | npm identified seven vulnerable dependency entries | Compatible patches applied; npm reported zero remaining vulnerabilities |

The earlier CSV classification remains in `lunarage-diagnosis.md` and
`lunarage-keyword-audit.csv`. Related phrases are not automatically content gaps.
The existing authority planner targets 25 spokes, includes owned-page context,
and distinguishes editorial proposals from researched keywords. Producing a
target number of pages does not establish search demand or guarantee rankings.

## Validation coverage

The final offline backend run passed **144 tests**. All **24 browser checks**
passed, including complete prompt-generation flows, scan creation, authority-plan
shortfalls, saved-keyword failure handling and account switching. Dashboard lint
and production build passed. Marketing built **11 pages**, with no missing local
internal links. `git diff --check` passed.

- Offline backend tests cover extraction, relevance, owned coverage, authority
  planning, provider fallback, scan diagnostics, start/pause/resume, stale jobs,
  dispatch failure, authentication, ownership, imports/exports, saved work,
  article failure/rewrite and website prompt generation. The runner uses isolated
  test databases and disables configured provider credentials.
- Browser tests cover all 11 authenticated dashboard routes and both public auth
  pages, unauthenticated redirects, AI diagnostics, visible completion warnings,
  blog project selection, and account switching. API responses are mocked: these
  are UI regression checks, not a hosted end-to-end scan.
- Dashboard lint and production build; marketing production build and internal
  link check across 11 generated HTML pages.
- Small live test requests succeeded with the locally configured DeepSeek and
  OpenRouter credentials. This does not verify Render's environment variables,
  competitor scraping, research-provider quotas, or a full live scan.
- A requested live 25-spoke generation using the original CSV has not run in
  this audit: automatic approval review rejected sending the CSV/site-context
  payload to external AI services and consuming credits without specific
  approval. Explicit user approval is pending. No live plan is claimed.

Reproduce the offline checks from the repository root:

```sh
.venvapp/bin/python backend/run_tests.py
```

In `dashboard`, run `npm run lint`, `npm run build`, and `npm run test:browser`.
Browser tests need Playwright Chromium or `PLAYWRIGHT_CHROME_PATH` set to an
installed Chrome executable. In `marketing`, run `npm run build`.

## Manual deployment and hosted acceptance

1. Commit and push the reviewed changes to the branch connected to Render and
   Vercel. Existing `c566caa` includes earlier fixes but not this audit's changes.
2. In Render, manually deploy that new commit. Verify the public
   `https://site-map-tool.onrender.com/api/health` response reports its first seven
   commit characters and `database: connected`. Remaining on `0f49dec` means the
   new backend is not running.
3. Deploy the dashboard with `VITE_API_URL=https://site-map-tool.onrender.com/api`.
   Confirm Settings displays the same backend revision.
4. In Settings, run “Test AI connection” and inspect Apify/DataForSEO status using
   the deployed service's credentials. Fix any actual account/quota errors shown.
5. Rerun the lunar-age project. Inspect the saved scan outcome and Render's
   `Competitor gap diagnostics` log entry. Distinguish failed scraping from no
   relevant candidates, already-covered topics, and quality rejection. Zero
   accepted gaps can be a valid result; do not pad it with junk to hide a warning.
6. Build the 25-spoke plan and review proposed topics, existing-page reuse, and
   duplicate intent. Open a spoke in Write Blog and confirm it remains attached
   to this project. Export the keywords and check source URLs and page counts.

The marketing contact form needs `PUBLIC_WEB3FORMS_ACCESS_KEY` at build time for
delivery. Without it, the site offers its existing contact email; message delivery
has not been tested. AI runtime status is process-local and expires after five
minutes; the explicit Settings test checks the process serving that request.

This audit verifies the listed workflows and regression cases. Hosted acceptance,
load testing, every input combination, and external-service uptime remain outside
that evidence. It is not a guarantee that every function is defect-free.
