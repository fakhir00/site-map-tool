# Keyword research and architecture recovery — 17 October 2026

The reported failures had several separate causes. Increasing a keyword quota
alone would not fix them.

## Changes

- Prevent contradictory taxonomy exclusions from banning the site's own topic.
  A live provider response returned `animal husbandry` and `animal facts` as
  negative phrases. Splitting them into words accidentally excluded `animal`,
  suppressing the main seed, animal-profile research and AI suggestions. Protect
  words supported by the seeds and positive site evidence while preserving
  genuine exclusions such as `husbandry` and `veterinary`. Apply this safeguard
  both when parsing taxonomy and when assembling pipeline filters.
- Expand autocomplete research across focused, crawled site topics when paid
  keyword providers return too little. Stop at the observed-candidate target or
  the bounded request limit; do not fabricate search queries or metrics.
- Use natural, short research seeds instead of concatenating every qualifier
  from a page heading. Exclude competitor-navigation phrases at final storage,
  even if an upstream AI review approved them.
- Retain useful covered queries for planning existing-page improvements. New
  gaps, pending research and existing coverage remain separate concepts.
- Transport large architectures using keyword references and grouped supporting
  placements. Expand them into the existing public schema before validation.
  Reject truncated outer JSON instead of treating a nested page as a complete
  architecture.
- Resolve unambiguous planned URL destinations to their keyword labels. Repair
  malformed placement batches locally. Unplanned owned destinations still need
  complete page briefs, and unknown or ambiguous URLs remain invalid.
- Give large AI responses most of their stage budget while reserving time for
  fallback. The total request deadline remains bounded.
- Use stable page IDs during semantic review. Supporting queries on the same
  page are not competing URLs. Preserve valid merge findings from a partially
  malformed review and require another review of the resulting plan.
- Require both the same specific task and substantially interchangeable answers
  before merging. The old majority vote could collapse distinct entity pages
  merely because their audiences and article formats were similar. Directory
  summaries, detailed profiles, tools and substantive explanations can coexist.
- Independently verify proposed merges against the actual pairs of page briefs,
  without showing the first review's verdict. Check every pair in bounded
  batches. Missing or malformed decisions cannot authorize any merge. A live
  attempt exposed a cascade that reduced 35 pages to one; the independent check
  prevented unrelated profiles and explanations from being absorbed into hubs.
- Prefer the default-language URL when equivalent translated sitemap entries
  appear first. Previously `/ar/...` could displace the existing unprefixed
  page in both the crawl and the ownership context.
- Apply known competitor-brand exclusions to all architecture candidates,
  including older gap rows without per-keyword source metadata. Reject bare
  fragments such as `how to find` while retaining complete questions.
- Retry stalled semantic review through architecture repair within the same
  request. A saved map is replaced only after the complete plan passes.

## Live research evidence

A fresh scan of `animalsoulquiz.com` ran against real public pages and configured
providers in an isolated local database. It discovered 120 URLs and scraped 75
pages: 40 owned pages and 35 competitor pages across eight competitor domains.
It stored **134 gap rows**, exceeding the requested research target of 50.
Autocomplete recovery contributed 41; the competitor review contributed 92;
Apify keyword research contributed one. The research inventory separately
contained 123 covered, 136 opportunity, 34 pending and 99 rejected candidates.
Counts differ because gap storage deduplicates phrases and applies additional
checks. Eight competitor candidates remained unreviewed after partial provider
responses; this limitation was reported rather than treated as approval.

The scan began before the final competitor-brand storage guard was added. Its
134 rows therefore include a subsequently identified navigational phrase; the
architecture's relevance review must still exclude unsuitable inputs. The raw
scan count is not a claim that all 134 phrases should become pages.

Planning imports 300 of 342 available phrases, including covered queries and
owned-page topics. All known owned URLs remain available as context. This is
not 300 confirmed gaps or 300 measured-demand keywords. Unknown search-volume
and difficulty values remain unknown.

## Verification and release status

The first successful complete live architecture used **280 of 300 phrases across
29 pages**, comprising 29 page targets and 251 supporting placements. It reused
22 existing URLs, proposed seven new pages, excluded 20 phrases and passed the
semantic audit. Of the original 134 gap rows, 128 were retained. Inspection of
that output then prompted the final locale and historical-brand fixes above.
The second clean scan exposed the taxonomy conflict above and stopped at 21
gaps. Its actual provider output confirmed the exclusion of `animal`; this was
not a lack of available topics. Corrected research against the same fresh crawl
then stored **94 gaps**. A subsequent live map used **285 of 300 phrases across
56 pages**, reusing 44 existing URLs and proposing 12 new pages. It retained
84 of the 94 gap rows and passed semantic review. The saved
[keyword placements](animalsoulquiz-keyword-placements-2026-10-17.csv) and
[page plan](animalsoulquiz-page-plan-2026-10-17.md) record that run.

Repeated builds still exposed response-format and review-retry failures. See the
[19 October dotplotmaker investigation](dotplotmaker-map-recovery-2026-10-19.md)
for the subsequent reliability fixes and verification; one successful build
was not sufficient evidence that those remaining failures were resolved.

These checks use an isolated local database, not customer production records.
The hosted backend must run the updated revision before users receive the fixes.
Its public health endpoint still reported revision `839d946` during this check;
the newer local commits and current working-tree changes are not deployed there.
