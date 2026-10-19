# Dotplotmaker map generation recovery — 19 October 2026

The reported 87 gaps and 249 planning keywords are sufficient inputs. The
reported `Expecting property name enclosed in double quotes` failure occurs
when parsing an AI response; the Apify allowance message is a separate research
limitation. Map generation does not require new competitor results.

## Fixes

- Recover trailing commas in otherwise complete JSON without changing quoted
  text. Do not manufacture missing fields, values, or closing containers.
- For a complete but malformed architecture response, attempt one syntax-only
  repair within the original request deadline. Then run the same inventory,
  ownership, capability, placement, and semantic validations. Reject truncated
  responses and unsuccessful repairs; never save a partial map as approved.
- Ignore echoed briefs for already planned destinations during keyword placement
  recovery. Preserve the original page and URL. Invalid new targets get specific
  batch feedback instead of a generic duplicate-page error.
- Carry explicit page eligibility assessments from the independent merge review
  forward. Previously it could correctly reject a destructive merge while its
  page assessments were lost, leaving the first reviewer to repeat the same
  disputed merge indefinitely.
- Preserve valid partial page assessments across review retries only while the
  entire plan, keyword placement, and site context are unchanged. Any change
  invalidates that cache; a new negative assessment cannot inherit old approval.
  Every surviving spoke still requires its own complete eligibility assessment.

The JSON mode setting follows [DeepSeek's JSON output contract](https://api-docs.deepseek.com/guides/json_mode/).
JSON mode alone does not replace complete-response checks or semantic review.

## Verification

The offline backend suite passes **324 tests**. New regressions cover malformed
JSON, preservation of literal strings, refusal to complete truncated documents,
bounded repair deadlines, echoed page briefs, independent eligibility evidence,
unsupported capabilities, and invalidation of partial review results.

A live preliminary run used the freshly crawled dotplotmaker.com site context
before its gap research had completed. It started with 27 existing-topic inputs
and discovered additional editorial topics. It produced **30 spokes**, placing
**55 of 56 phrases** across 31 pages, and passed semantic review. These phrases
include existing topics and editorial proposals; they are not 55 newly measured
search queries. This verifies that zero new gaps do not prevent map generation.

The cloud project's exact 249-row inventory is not present in the local database.
Live verification uses fresh public site research in an isolated database and
does not modify customer projects.
