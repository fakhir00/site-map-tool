# TASK: 4-Tier Keyword Classification + Tier-Aware Hub & Spoke Visualization

This prompt has two phases. Implement Phase 1 (backend classification) completely and
verify it before starting Phase 2 (frontend visualization) — Phase 2 depends entirely on
Phase 1's output shape.

---

## BACKGROUND / GOAL

Today, `filter_keyword_gap_recommendations()` tries to deduplicate same-intent keywords in
a single LLM prompt pass, and it's unreliable — near-duplicate keywords routinely survive
as separate rows, and `cluster_hub_and_spoke()` has no dedup logic of its own, so
cannibalizing duplicates end up as separate spokes.

We are replacing the single binary "merge or don't" decision with a **4-tier classification
system**, computed algorithmically (embeddings) with LLM verification only where it's
actually needed — not a full LLM judgment pass over the whole list.

### The two requirements this must satisfy simultaneously:
1. Every keyword shown to the user must be highly relevant to the Gold Hunter audit summary
   (Core Subject / Core Audience / Core Action) — **do not touch this existing gate.**
2. No two surviving keywords/pages may cannibalize the same search intent — enforced by the
   4-tier system below, not by a single LLM clustering pass.

### The 4 tiers:

| Tier | Name | Condition | Output |
|---|---|---|---|
| 1 | `merge` | Tight semantic match (same intent, confirmed) | Collapse to ONE keyword: highest volume, most natural phrasing |
| 2 | `subheading_group` | Related but LLM finds real nuance between them, OR borderline-tight match | ONE article; broadest phrase = title; rest become H2/H3 sections |
| 3 | `related` | Same topical sub-silo, but distinct intents | Separate articles/spokes, cross-linked to each other (not randomly linked) |
| 4 | `outlier` | No meaningful match to anything else | Standalone spoke, no special linking |

### Where this runs in the pipeline (already decided — do not change ordering):
Classification happens **before** keywords are written via `_store_keywords()` and before
they appear in the Keyword Gap table — same point in the pipeline where
`filter_keyword_gap_recommendations()` currently runs. Only the CLASSIFICATION happens here.
Full article brief generation for Tier 2 clusters stays a separate, on-demand step (reuse
the existing `generate_all_briefs()` / `build_article_brief()` flow) — do not generate full
briefs synchronously during the filter step, that's expensive and belongs later.

### Important scoping rule:
Only run this tiering system on keywords of `type` in `{"primary", "long-tail"}`. Do NOT
cluster `entity`, `lsi`, or `heading` type keywords into this system — they serve a different
structural purpose (schema markup, supporting terms, in-article headings) and should continue
feeding the existing "supporting entities" list untouched. Clustering them into tiers risks
deleting entities needed for schema coverage or wrongly promoting a heading fragment into a
spoke URL.

---

# PHASE 1: Backend — Two-Level Clustering + Tier Classification

## Step 1 — Dependencies

Confirm these are installed (already documented in the stack, verify they're actually in
`requirements.txt` and installed, not just listed):
```
sentence-transformers
scikit-learn
```

## Step 2 — Add clustering utilities to `backend/nlp/keywords.py`

```python
from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

_intent_model = SentenceTransformer("all-MiniLM-L6-v2")  # load once, module scope

VOLUME_RANK = {"High": 3, "Medium": 2, "Low": 1}

LEVEL1_THRESHOLD = 0.55   # loose: defines sub-silo membership
LEVEL2_THRESHOLD = 0.85   # tight: candidate for true duplication


def _embed(phrases: list[str]) -> np.ndarray:
    return _intent_model.encode(phrases, normalize_embeddings=True)


def cluster_level(keywords: list[dict], threshold: float) -> list[list[dict]]:
    """
    Generic single-level agglomerative clustering by cosine similarity threshold.
    `keywords` must each have a "phrase" key. Returns list of clusters (each a list
    of the original dicts).
    """
    if len(keywords) <= 1:
        return [[kw] for kw in keywords]

    phrases = [kw["phrase"] for kw in keywords]
    embeddings = _embed(phrases)

    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=1 - threshold,
        metric="cosine",
        linkage="average",
    )
    labels = clustering.fit_predict(embeddings)

    clusters: dict[int, list[dict]] = {}
    for label, kw in zip(labels, keywords):
        clusters.setdefault(label, []).append(kw)

    return list(clusters.values())


def pick_cluster_representative(cluster: list[dict]) -> dict:
    """Highest volume tier wins; tiebreak by shorter/more natural phrasing."""
    return sorted(
        cluster,
        key=lambda kw: (VOLUME_RANK.get(kw.get("volume", "Low"), 0), -len(kw["phrase"])),
        reverse=True,
    )[0]


def pick_broadest_phrase(cluster: list[dict]) -> dict:
    """
    For Tier 2 title selection: picks the phrase closest to the cluster's semantic
    centroid (most representative/broadest framing), not just the shortest string —
    substring/length heuristics fail when phrases don't share common substrings
    (e.g. "0dte risk management" vs "iron condor risk management").
    """
    phrases = [kw["phrase"] for kw in cluster]
    embeddings = _embed(phrases)
    centroid = embeddings.mean(axis=0, keepdims=True)
    sims = cosine_similarity(embeddings, centroid).flatten()
    return cluster[int(np.argmax(sims))]
```

## Step 3 — Add LLM verification call to `backend/nlp/openrouter.py`

Only called on Level-2 (tight) clusters with 2+ members. Use a cheap/fast model — this is a
small classification task, not generation.

```python
def verify_cluster_intent(cluster: list[dict], call_llm_fn) -> dict:
    """
    Verifies a tight (Level-2) cluster. Returns one of:
      {"verdict": "same_intent"}                     -> Tier 1 (merge)
      {"verdict": "related_nuance"}                   -> Tier 2 (subheading group)
      {"verdict": "different", "groups": [[...],[...]]} -> split, re-classify each group
    `call_llm_fn` = existing LLM wrapper already used elsewhere in this file.
    """
    if len(cluster) < 2:
        return {"verdict": "same_intent"}

    phrases = [kw["phrase"] for kw in cluster]

    prompt = f"""[SYSTEM COMMAND — INTENT CLUSTER VERIFICATION]

You are an SEO search-intent auditor. These keywords were flagged as very similar in
meaning by an automated similarity check:

{phrases}

Classify this group into exactly ONE of three verdicts:

1. "same_intent" — these are genuinely the SAME searcher intent (same goal, same
   audience, same journey stage), just phrased differently. They should become ONE
   page targeting ONE of these phrases.

2. "related_nuance" — these are closely related and could reasonably live on ONE
   comprehensive article, but each phrase represents a slightly distinct angle or
   sub-question worth its own section (H2/H3) within that article — not distinct
   enough to deserve fully separate pages.

3. "different" — at least one keyword here represents a meaningfully different
   intent (different audience, different goal, or different journey stage) and
   should NOT be grouped with the others at all.

**Examples:**
- "iron condor vs iron butterfly" / "iron butterfly vs iron condor" -> same_intent (word-order flip)
- "iron condor risk management" / "0dte iron condor risk management" / "0dte risk management" -> related_nuance (one is broader than the other two, all valid sections of one guide)
- "cash secured put strategy" / "cash secured put nvidia strategy" -> different (general vs ticker-specific — different searcher intent)

**Output rules:**
- If verdict is "same_intent" or "related_nuance", return: {{"verdict": "same_intent"}} or {{"verdict": "related_nuance"}}
- If verdict is "different", return: {{"verdict": "different", "groups": [["phrase1","phrase2"], ["phrase3"]]}}
  Every input phrase must appear in exactly one output group. Do not add, drop, or rewrite phrases.

Return ONLY the JSON object, nothing else.
"""
    return call_llm_fn(prompt, model="gpt-4o-mini", response_format="json")
```

## Step 4 — Tier classifier: `classify_keyword_tiers()` in `backend/nlp/keywords.py`

This is the orchestration function that ties Steps 2-3 together.

```python
def classify_keyword_tiers(keywords: list[dict], call_llm_fn) -> list[dict]:
    """
    Input: keywords already passed through relevance + volume gates (existing
    filter_keyword_gap_recommendations logic, minus its old Step 3 intent-clustering).
    Only pass keywords with type in {"primary", "long-tail"} — filter that at the
    call site before invoking this function.

    Output: list of tier records, e.g.:
      {"tier": "merge", "sub_silo": <id>, "cluster": [...], "representative_keyword": {...}}
      {"tier": "subheading_group", "sub_silo": <id>, "cluster": [...], "broadest": {...}}
      {"tier": "related", "sub_silo": <id>, "cluster_group_id": <id>, "members": [...]}
      {"tier": "outlier", "sub_silo": <id>, "keyword": {...}}
    """
    results = []
    level1_clusters = cluster_level(keywords, LEVEL1_THRESHOLD)

    for sub_silo_id, l1_cluster in enumerate(level1_clusters):
        if len(l1_cluster) == 1:
            results.append({
                "tier": "outlier",
                "sub_silo": sub_silo_id,
                "keyword": l1_cluster[0],
            })
            continue

        level2_clusters = cluster_level(l1_cluster, LEVEL2_THRESHOLD)
        used_in_tight_cluster = set()

        for l2_cluster in level2_clusters:
            if len(l2_cluster) < 2:
                continue  # handled as "related" below via leftovers

            verdict = verify_cluster_intent(l2_cluster, call_llm_fn)

            if verdict["verdict"] == "same_intent":
                results.append({
                    "tier": "merge",
                    "sub_silo": sub_silo_id,
                    "cluster": l2_cluster,
                    "representative_keyword": pick_cluster_representative(l2_cluster),
                })
                used_in_tight_cluster.update(kw["phrase"] for kw in l2_cluster)

            elif verdict["verdict"] == "related_nuance":
                results.append({
                    "tier": "subheading_group",
                    "sub_silo": sub_silo_id,
                    "cluster": l2_cluster,
                    "broadest": pick_broadest_phrase(l2_cluster),
                })
                used_in_tight_cluster.update(kw["phrase"] for kw in l2_cluster)

            else:  # "different" — LLM split it; treat sub-groups as related, not merged
                phrase_to_kw = {kw["phrase"]: kw for kw in l2_cluster}
                for group in verdict["groups"]:
                    group_kws = [phrase_to_kw[p] for p in group if p in phrase_to_kw]
                    if group_kws:
                        used_in_tight_cluster.update(kw["phrase"] for kw in group_kws)
                # fall through — these remain in the Level-1 cluster as "related" below

        # everything in this Level-1 (sub-silo) cluster not absorbed into a Tier 1/2
        # group is "related" — same topic, distinct intent, should cross-link
        leftovers = [kw for kw in l1_cluster if kw["phrase"] not in used_in_tight_cluster]
        if leftovers:
            results.append({
                "tier": "related",
                "sub_silo": sub_silo_id,
                "cluster_group_id": f"silo-{sub_silo_id}",
                "members": leftovers,
            })

    return results
```

## Step 5 — Wire into the pipeline (`backend/workers/pipeline.py`)

Replace the old Step 3 "Intent Clustering" section of the `filter_keyword_gap_recommendations`
prompt (remove it from the prompt text — normalization/relevance/volume gates stay exactly as
they are, only the final "Step 3: Intent Clustering" and "Step 4: Final Output" dedup
instruction are removed from that prompt). Keep the prompt's cap on total keywords returned.

After `filter_keyword_gap_recommendations()` returns its filtered list:

```python
from backend.nlp.keywords import classify_keyword_tiers

# split by type — only primary/long-tail go through tiering
clusterable = [kw for kw in filtered_keywords if kw.get("type") in ("primary", "long-tail")]
passthrough = [kw for kw in filtered_keywords if kw.get("type") not in ("primary", "long-tail")]

tier_results = classify_keyword_tiers(clusterable, call_llm_fn=<existing_llm_wrapper>)

# passthrough (entity/lsi/heading) keywords continue feeding the existing
# "supporting entities" bucket exactly as before — do not tier them.

# tier_results is what gets stored / passed to _store_keywords() and to
# cluster_hub_and_spoke() — NOT the old flat deduped list.
```

Apply this at both places the filter currently runs (per-URL-chunk in Step 5, and after
`generate_ai_keywords_sync()` in Step 6), and ensure `cluster_hub_and_spoke()` now consumes
`tier_results` instead of a flat keyword list.

## Step 6 — Data model changes

Add to whatever model/schema currently stores keyword gap results (check
`backend/models/keyword.py` or equivalent):
```python
tier: str            # "merge" | "subheading_group" | "related" | "outlier"
sub_silo_id: int
cluster_group_id: str | None      # only for "related" tier — used by link planner
article_title: str | None         # only for "subheading_group" — from pick_broadest_phrase
h_tags: list[str] | None          # only for "subheading_group" — other cluster members
merged_from: list[str] | None     # only for "merge" — the dropped duplicate phrases, kept for audit/debug
```

## Step 7 — Downstream consumers

- **`build_article_brief()` calls for Tier 2 clusters:** when generating a brief for a
  `subheading_group`, pass ALL cluster phrases and instruct the brief generator: "cover all
  these related search intents in one article; use the broadest phrase as title; structure
  remaining phrases as H2/H3 sections." Scale `target_word_count` up proportionally to cluster
  size (e.g. base word count + ~500 per additional intent in the cluster) — do not use a flat
  word count for every Tier 2 article regardless of how many intents it covers.
- **`InternalLinkPlanner`:** replace `random.shuffle(siblings)` sibling selection with
  cosine-nearest-neighbor selection using the same embeddings, AND always link all members of
  the same `cluster_group_id` (Tier 3 "related") to each other explicitly, regardless of
  general link-planning rules — this is the anti-cannibalization signal, don't let it get
  randomized away.

## Step 8 — Testing / acceptance criteria

1. Run against a real project's keyword list (not synthetic data) — ideally the same one used
   to validate the earlier fix.
2. Print out, per sub-silo: which keywords ended up in each tier, and for `merge`/
   `subheading_group` tiers, the LLM verdict and reasoning.
3. Confirm:
   - No two `outlier` or `related` tier keywords represent the same intent (spot-check
     manually against a sample).
   - `merge` clusters only ever contain genuinely identical-intent phrases (check against the
     known false-positive cases: ticker-specific vs general, dollar-amount-specific queries,
     etc. — these should NOT merge).
   - `subheading_group` article titles read naturally as titles, not just "the shortest
     phrase."
   - Total keyword count reduction is reasonable (per the earlier analysis on a real 203-row
     CSV, expect roughly 10-15% Tier 1 merges, not 50%+ — if you're seeing much higher
     merge rates, `LEVEL2_THRESHOLD` is too loose).
4. Tune `LEVEL1_THRESHOLD` / `LEVEL2_THRESHOLD` against real data, not assumptions — these are
   the two levers, not the LLM prompt wording.

---

# PHASE 2: Frontend — Tier-Aware Hub & Spoke View

Only start this after Phase 1 is verified and `tier_results` (with the Step 6 schema) is
actually being persisted and available via API.

## Step 1 — API response shape

Confirm/update the endpoint that feeds `HubSpokeView` (likely under
`backend/routers/keywords.py` or similar) to return the tiered structure grouped by
`sub_silo_id`, including `tier`, `article_title`, `h_tags`, `cluster_group_id`, and
`merged_from` fields per node, as defined in Phase 1 Step 6.

## Step 2 — Update `HubSpokeView` node rendering (React)

Each node must branch on `tier`:

- **`tier: "merge"`** — render as a normal spoke node. Add a small subtitle/badge:
  `"({merged_from.length} combined)"`. On hover/click, show the dropped duplicate phrases
  (from `merged_from`) in a tooltip — don't just silently discard them from the UI, the user
  should be able to see what was merged for audit purposes.

- **`tier: "subheading_group"`** — render as a visually distinct node (different color/icon —
  e.g. purple, vs the default spoke color). Must be expandable/collapsible: clicking it reveals
  `h_tags[]` as an indented child list beneath the node (accordion, or child nodes in
  `react-flow` if that's what's already in use per the architecture doc's frontend). Label the
  node with `article_title`, not the raw keyword phrase.

- **`tier: "related"`** — render as a normal spoke node, same as today, but the graph must
  also draw a distinct edge/connector (e.g. dashed line, different from the pillar→spoke solid
  lines) between every pair of nodes sharing the same `cluster_group_id`. This is the one new
  edge type — don't reuse the pillar-hierarchy edge style for it, it needs to read visually as
  "these are siblings," not "these are parent/child."

- **`tier: "outlier"`** — render exactly as today, no changes.

## Step 3 — Legend / UI affordance

Add a small legend to the Hub & Spoke view explaining the 4 node types (merged / multi-intent
article / related-linked / standalone) — since this is a new visual language on top of the
existing map, users need a one-time explanation of what the colors/connectors mean.

## Step 4 — Testing / acceptance criteria

1. Load a project that has all 4 tiers present (use Phase 1's test project).
2. Confirm the map renders without layout breakage — `subheading_group` nodes with several
   `h_tags` shouldn't overlap siblings when expanded.
3. Confirm `related` connector lines only appear within the correct `cluster_group_id` groups,
   not across unrelated sub-silos.
4. Confirm clicking a `merge` node's tooltip shows the actual dropped phrases (not an empty
   list — verify `merged_from` is actually populated from Phase 1's backend output).

## CONSTRAINTS (both phases)

- Do not weaken or merge the existing audit-summary relevance gate (Core Subject/Audience/
  Action) into this clustering logic — it stays a separate, untouched step.
- Do not tier `entity`, `lsi`, or `heading` type keywords — only `primary` and `long-tail`.
- Keep the embedding model loaded once at module scope (runs inside a multithreaded pipeline
  per the architecture doc — repeated loads are wasteful).
- `verify_cluster_intent()` only runs on Level-2 clusters with 2+ members — never on
  singletons.
- Classification (Phase 1) must complete before keywords are shown in the Keyword Gap table.
  Full brief generation for Tier 2 clusters stays a separate, later, on-demand step — do not
  generate briefs synchronously inside the filter/classification pass.
