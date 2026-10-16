# Planning inventory follow-up — 15–16 October 2026

Stricter gap review could starve Hub Spoke because planning previously depended
primarily on the accepted new-gap table. Useful queries already answered by the
site disappeared along with rejected junk. Low gap counts could therefore hide
useful supporting keywords and prevent a scan with no gaps from starting a map.

## Changes

- Persist research candidates separately from confirmed gaps. Competitor,
  provider, autocomplete and AI research paths retain their inputs and explicit
  review outcomes. Missing decisions stay pending; explicit rejections are
  excluded from planning.
- Add a `covered` review outcome for useful queries already answered by an owned
  URL. It requires a reader need, evidence citation, target topic and exact known
  URL. It does not manufacture a missing answer or inflate the new-gap count.
- Both planning entry points combine accepted gaps, reviewed research, pending
  candidates, owned-page topics and the primary topic. A balanced selection caps
  each map at 300 keywords and reports omitted inventory.
- Keep measured zero values and unknown metrics distinct. AI proposals remain
  labeled as inferred ideas, including after usefulness review.
- Let the workspace start discovery from the main topic with no gap keywords.
  Show gap counts separately from planning counts and explain pending review.
- Give related topics without literal seed words a fair share of review slots.
  Existing relevance, brand, ownership and cannibalization checks remain active.
- Constrain the semantic review to actual current page targets. Live responses
  incorrectly treated already-assigned supporting keywords as separate URLs.
  Invalid-reference retries now name the offending pair and valid targets;
  explicit merge judgments still need the existing majority-YES evidence test.
- Permit the main topic hub to reuse a verified existing non-homepage URL, such
  as `/quiz/`. Ownership reconciliation previously selected that URL correctly
  and final validation then rejected it for not being `/`, wasting a full
  planning retry. The default for a new main hub remains `/`.

The new `research_keywords` table is created through the existing startup schema
initialization. It is project scoped, cleared on a fresh scan and removed with
its project. Historical discarded candidates cannot be recovered; rescan to
populate the new inventory. Existing saved work retains its current behavior.

## Verification

The isolated integration regression starts with 73 relevant research candidates
and one unrelated candidate. Review accepts two new gaps and marks 71 queries as
covered. Both the importer and actual architecture orchestration retain all 73
useful terms. With controlled AI responses, the resulting plan has seven existing
page targets and 66 supporting keywords; no duplicate new URLs are introduced.
This establishes the data flow and ownership behavior, not a promise that every
real set of 73 queries should produce seven pages.

Additional regressions cover zero-gap planning through both API routes, pending
research during a review outage, rejection handling, project isolation, measured
zero preservation, editorial labels, a 403-keyword inventory capped at 300 and
fresh-scan cleanup. Browser tests exercise main-topic-only generation and a
zero-gap import retaining research provenance in the build request.

Validation: **293 backend tests passed** through the offline runner. All **49
browser cases passed** across a full run and three targeted reruns. The initial
browser run hit three five-second render deadlines under host load; the new
import test now waits for its import response before inspecting the result.
Dashboard ESLint and the production build passed. The first lint invocation
collided with Playwright cleaning its results directory; the sequential rerun
passed. `git diff --check` passed.

## Live check and limits

A bounded live check uses 27 previously observed public autocomplete suggestions
and four public page summaries: the [homepage](https://www.animalsoulquiz.com/),
[quiz](https://www.animalsoulquiz.com/quiz/),
[wolf profile](https://www.animalsoulquiz.com/animals/wolf/) and
[owl profile](https://www.animalsoulquiz.com/animals/owl/). The configured AI
accounted for all 27: 18 potential gaps, six covered, three rejected and zero
unreviewed. The six covered queries now remain planning inputs. Partial owned
coverage cannot establish 18 confirmed gaps across the complete site.

The initial live architecture attempts failed because semantic review confused
supporting keywords with separate pages. After the conflict-target prompt and
feedback fix, the live discovery/planning/placement/review run completed with
**37 of 37 planning keywords used across 11 page targets, including 26 supporting
keywords**, and a passed semantic audit. This inventory includes editorial
discovery, so those counts are not 37 measured keywords or 11 confirmed gaps.
The run also exposed the non-homepage ownership validation conflict, fixed in
the final code and covered by a full architecture-orchestration regression.
The partial public inventory does not establish complete-site duplicate safety;
the hosted scan must supply all known owned URLs before release acceptance.

This is a local code change, not a deployment. Provider availability and quotas
remain external constraints. No measured search-volume increase or ranking
outcome is claimed, and a complete hosted rescan is still needed for release
acceptance.
