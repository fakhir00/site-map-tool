# Lunar Age keyword-gap diagnosis — 24 September 2026

Reviewed all 70 rows in `keywords-92e6e055-9ff3-4e8a-ad71-672dcd8b1aa5.csv`. The companion CSV retains every original field and adds an editorial classification, reason, destination, and distinct exported competitor-URL count.

| Editorial assessment | Rows |
|---|---:|
| Related, with existing topic coverage | 45 |
| Related, gap not yet verified | 6 |
| Broad or outside verified intent | 9 |
| Junk or needs rewriting | 10 |

These are editorial judgments, not measured search demand or rankings. Existing coverage means the task/topic is served; it does not mean every exact phrase occurs verbatim or that the page cannot be improved. No candidate here is certified as a new-page opportunity. Blank volume/difficulty fields mean unknown.

## Actual site scope

The [homepage](https://www.lunaragecalculator.com/) covers traditional age, age-at-birth, nominal age, calendar conversion and zodiac context. The [gender predictor](https://www.lunaragecalculator.com/chinese-age-calculator-gender-predictor/) already covers the chart, conception inputs, origins, methods, accuracy and comparisons. A [Korean lunar age tool](https://www.lunaragecalculator.com/korean-lunar-age-calculator/) also exists. These pages were inspected during this review. The linked zodiac page could not be fetched, so its completeness is unverified.

Consequently, Korean age and gender prediction are not inherently unrelated to this particular site. Domain-name-only filtering would remove legitimate topics. The major defect is confusing related keywords with missing content. Row 47, `chinese age calculator gender predictor`, even matches an existing owned page slug, despite being presented as an AI gap.

## Confirmed implementation defects and changes

1. Statistical extraction removed stopwords before forming n-grams, joining nonadjacent words and crossing sentence boundaries. It now preserves original adjacency and sentence boundaries.
2. URL extraction normalized `.php` into a keyword token. It now removes HTML/PHP/ASP extensions before constructing candidates.
3. Extractor frequency increased once per extraction method, including repeat sightings on the same page. It now counts distinct page IDs. Merged final competitor candidates also count distinct page IDs.
4. A successful empty AI review was treated as a provider failure and replaced with unreviewed raw candidates. Empty verdicts are now respected. An unavailable competitor quality review raises an explicit scan failure rather than silently publishing raw extraction. Generated suggestions also respect successful empty reviews.
5. Final competitor review lacked owned-page content. It now receives bounded owned-page excerpts and explicitly rejects already-served intents, not merely exact duplicate strings. Scope remains contextual; shared cultural vocabulary alone is insufficient.
6. Owned URL keyword matching generated only short n-grams, missing complete long tool slugs. It now retains full valid slugs, preventing the exact row-47 failure during subsequent generation.
7. CSV export labeled extraction frequency as competitor pages, including AI evidence. It now counts actual distinct competitor source URLs and preserves genuine zero metric values. In the supplied file, 45 rows have a count different from their distinct exported competitor URLs; for example, traditional Korean age reports six pages but lists one. This is a file-level consistency check, not a reconstructed database audit.
8. The dashboard's 94.2%, 99.1%, and 87.4% values, animated processing claims and synced state were hardcoded. The panel now reports only available scan activity and states that quality confidence is not measured.
9. An existing artifact regression exposed a repeated-word threshold that allowed `age korean age`. The threshold now rejects that malformed short phrase while retaining ordinary questions.

## Other observations and limits

- The displayed totals differ by exactly one synthetic AI source: 96/90 versus 95/89. This matches the supplied source list. The current worker count code already excludes AI/provider URLs; no deployment-version evidence was available to establish why the displayed totals were stale or inconsistent.
- Source domains with literal escaped dots need inspection against live stored records; the export contains normal source URLs. No speculative migration was applied.
- Competitor coverage is not keyword relevance. A general site's relevant page may still contain unrelated tools, menus, and comparison terms.
- Owned-page review is bounded to the first 20 scraped owned pages, 4,000 characters each. Exact owned-phrase checks remain in place across the existing pipeline. This improves coverage comparison but is not exhaustive semantic proof for large sites or content beyond those excerpts.
- AI quality decisions can still make mistakes. The regression tests verify code behavior, not a paid live model's judgment over a new crawl.
- Existing saved database rows have not been rewritten. Deploy the changed application and rerun the scan to regenerate results. CSV source counts are corrected at export time once deployed; extraction/coverage changes require a rescan.
- The original export remains untouched. The classified CSV is a review artifact, not a replacement list of verified gaps.
