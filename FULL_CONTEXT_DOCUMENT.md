# SiteMapSEO — Full SaaS Context Document

> **Purpose:** This document describes every component, database model, API endpoint, AI agent prompt, pipeline step, and configuration setting of the SiteMapSEO SaaS application. It is designed so that any LLM can fully understand the system and answer questions about it.

---

## 1. PRODUCT OVERVIEW

**SiteMapSEO** is an AI-powered SEO intelligence SaaS tool. It helps website owners discover keyword gaps by crawling competitor sitemaps, extracting keywords from their URL structures, and using LLMs to filter, cluster, and generate content strategies.

### Core Value Proposition
- **Competitor Sitemap Intelligence:** Automatically crawls the sitemaps and content URLs of your competitors to discover what keywords they rank for that you don't.
- **AI Keyword Gap Analysis:** Uses LLMs (GPT-4o-mini, Groq, DeepSeek, TokenRouter) to extract, filter, and validate keyword gaps.
- **Hub & Spoke Architecture:** Organizes discovered keywords into a topical authority map (Master Hub → Sub-Silos → Foundation/Action/Money Spokes).
- **AI Article Generation:** Generates full SEO articles with a multi-step pipeline: Research → Brief → Master Prompt → Article → Audit loop.
- **Gold Hunter:** A quick-scan tool that audits any URL and returns 3 high-value seed keywords.

### Tech Stack
- **Backend:** Python 3.11, FastAPI, SQLAlchemy (async + sync), PostgreSQL (production) / SQLite (local dev)
- **Frontend:** React 18 + TypeScript + Vite, shadcn/ui components, React Router v6
- **AI Providers:** OpenAI-compatible API clients via `openai` SDK pointing at:
  - TokenRouter (primary, `https://api.tokenrouter.com/v1`)
  - DeepSeek (`https://api.deepseek.com`)
  - Groq (`https://api.groq.com/openai/v1`)
  - OpenRouter (`https://openrouter.ai/api/v1`)
- **Scraping:** `requests`, `httpx`, `BeautifulSoup4`, `trafilatura`, `lxml`, `duckduckgo-search`, Apify client
- **NLP:** `spacy`, `rake-nltk`, `keybert`, `nltk`, `scikit-learn`, `sentence-transformers`
- **Task Queue:** Celery + Redis (production), FastAPI BackgroundTasks (local dev)
- **Deployment:** Backend on Render, Frontend on Vercel, PostgreSQL on Render

---

## 2. REPOSITORY STRUCTURE

```
sit map tool/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app entry point, CORS, lifespan
│   │   ├── config.py            # Pydantic Settings (env vars)
│   │   ├── database.py          # Async SQLAlchemy engine + session
│   │   ├── models.py            # All SQLAlchemy ORM models
│   │   ├── schemas.py           # All Pydantic request/response schemas
│   │   ├── auth/
│   │   │   ├── router.py        # POST /api/auth/register, /api/auth/login, GET /api/auth/me
│   │   │   └── jwt.py           # JWT token creation + get_current_user dependency
│   │   ├── projects/
│   │   │   └── router.py        # CRUD for projects (/api/projects)
│   │   ├── scan/
│   │   │   └── router.py        # Start/Pause/Resume/Status of scans
│   │   ├── keywords/
│   │   │   └── router.py        # List/Generate/Export/Save/Delete keywords, Hub-Spoke, Top Picks
│   │   ├── content/
│   │   │   ├── router.py        # Article generation endpoints
│   │   │   └── service.py       # Article generation pipeline (brief → prompt → audit loop)
│   │   ├── goldhunter/
│   │   │   ├── router.py        # POST /api/goldhunter/scan, GET /api/goldhunter/history
│   │   │   └── scraper.py       # fetch_url_content() for Gold Hunter
│   │   └── website_prompts/
│   │       ├── router.py        # Intent analysis + prompt generation
│   │       └── service.py       # Intent + Prompt + Gap Page flows
│   ├── nlp/
│   │   ├── openrouter.py        # ALL AI agent prompts and LLM API calls (1392 lines)
│   │   └── keywords.py          # Keyword extraction, cleaning, validation, NLP utilities
│   ├── scraping/
│   │   ├── sitemap.py           # XML sitemap parsing, extract_all_urls_from_domain()
│   │   ├── crawler.py           # HTTP scraping with BeautifulSoup/trafilatura
│   │   ├── filters.py           # URL filtering (filter_blog_urls, etc.)
│   │   └── apify_client_module.py  # Google search via Apify, website crawling
│   ├── workers/
│   │   └── pipeline.py          # The main scan pipeline (multithreaded)
│   ├── requirements.txt
│   └── Dockerfile
├── dashboard/
│   └── src/
│       ├── App.tsx              # React Router setup
│       ├── lib/
│       │   ├── api.ts           # API client (fetch wrapper, auth, types)
│       │   └── demoBackend.ts   # In-browser demo backend for Vercel preview
│       ├── pages/
│       │   ├── ProjectsList.tsx     # Dashboard home — list of projects
│       │   ├── ProjectDetail.tsx    # Project detail — scan progress + keyword table
│       │   ├── GoldHunter.tsx       # Gold Hunter URL audit
│       │   ├── WebsitePromptGenerator.tsx  # Website prompt generator
│       │   ├── GapPageGenerator.tsx  # Gap page prompt generator
│       │   ├── ScanInterface.tsx     # Quick scan interface
│       │   ├── WriteBlog.tsx         # Blog article generation
│       │   ├── WriteBlogArticle.tsx  # Individual article view
│       │   ├── SavedKeywords.tsx     # Keyword bank
│       │   ├── Login.tsx / Register.tsx  # Auth pages
│       │   └── Settings.tsx          # User settings
│       └── components/
│           ├── DashboardLayout.tsx   # Sidebar + top nav
│           ├── KeywordsTable.tsx     # Main keyword results table
│           ├── HubSpokeView.tsx      # Hub & Spoke visualization
│           ├── CompetitorGraph.tsx    # Competitor domain graph
│           ├── SemanticMetrics.tsx    # Semantic analysis metrics
│           ├── LiveSignals.tsx       # Live scan progress signals
│           ├── GeneratedArticlePanel.tsx  # Article preview panel
│           ├── SavedKeywordsTable.tsx     # Saved keywords table
│           └── ThemeProvider.tsx / ThemeToggle.tsx
└── docker-compose.yml           # Full local stack: postgres + redis + backend + worker + dashboard
```

---

## 3. DATABASE MODELS

### 3.1 User
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID (PK) | Auto-generated |
| `email` | String(255) | Unique, required |
| `password_hash` | String(255) | bcrypt hash |
| `full_name` | String(255) | Optional |
| `google_id` | String(255) | For Google OAuth |
| `plan` | String(50) | Default: "free" |
| `is_active` | Boolean | Default: True |
| `created_at` / `updated_at` | DateTime | |

**Relationships:** `projects`, `keyword_bank`, `goldhunter_scans`

### 3.2 Project
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID (PK) | |
| `user_id` | UUID (FK → users) | CASCADE delete |
| `name` | String(255) | Project display name |
| `domain` | String(512) | Target competitor domain to analyze |
| `own_domain` | String(512) | User's own website domain |
| `scan_frequency` | String(50) | "once" |
| `url_filter_patterns` | JSON | Default: `["/blog/", "/news/", "/post/", "/article/"]` |
| `target_keywords` | JSON | Array of seed keyword strings |
| `audit_summary` | Text | Gold Hunter audit summary (used for strict filtering) |
| `status` | String(50) | "pending" / "running" / "paused" / "complete" / "error" |
| `search_locale` | String(10) | Default: "us" |
| `urls_found` / `urls_processed` / `urls_failed` / `total_keywords` | Integer | Counters |
| `created_at` / `last_scanned_at` / `next_scan_at` | DateTime | |

**Relationships:** `scan_jobs`, `urls`, `keywords`, `article_drafts`

### 3.3 ScanJob
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID (PK) | |
| `project_id` | UUID (FK → projects) | |
| `status` | String(50) | "queued" / "running" / "complete" / "error" |
| `celery_task_id` | String(255) | Celery task ID or "local-background-task" |
| `error_message` | Text | |
| `started_at` / `finished_at` / `created_at` | DateTime | |

### 3.4 Url
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID (PK) | |
| `project_id` | UUID (FK → projects) | |
| `scan_job_id` | UUID (FK → scan_jobs) | |
| `url` | Text | Full URL |
| `source_type` | String(50) | "own" / "competitor" / "ai" |
| `source_domain` | String(512) | e.g., "competitor.com" or "AI Recommendations" |
| `status` | String(50) | "pending" / "scraped" / "failed" |
| `h1` | Text | Page H1 heading |
| `word_count` | Integer | |
| `readability_score` | Float | |
| `publish_date` | Date | |
| `scraped_at` | DateTime | |
| `retry_count` | Integer | |

**Unique constraint:** `(project_id, url)`

### 3.5 Keyword
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID (PK) | |
| `project_id` | UUID (FK → projects) | |
| `phrase` | Text | The keyword phrase |
| `keyword_type` | String(50) | "primary" / "lsi" / "long-tail" / "entity" / "heading" / "top-pick" |
| `frequency` | Integer | How many competitor URLs target this keyword |
| `search_volume` | Integer | Estimated (nullable) |
| `difficulty` | Float | Estimated (nullable) |
| `created_at` / `updated_at` | DateTime | |

**Unique constraint:** `(project_id, phrase)`

### 3.6 KeywordUrl (Junction Table)
| Column | Type | Notes |
|--------|------|-------|
| `keyword_id` | UUID (PK, FK → keywords) | |
| `url_id` | UUID (PK, FK → urls) | |

### 3.7 KeywordBank (Saved Keywords)
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID (PK) | |
| `user_id` | UUID (FK → users) | |
| `keyword_id` | UUID (FK → keywords) | |
| `notes` | Text | User notes |
| `saved_at` | DateTime | |
| `is_done` | Boolean | Default: False |
| `done_at` | DateTime | |

### 3.8 HubSpokeCluster
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID (PK) | |
| `project_id` | UUID (FK, unique) | One cluster per project |
| `mapping_data` | JSON | The full Hub/Spoke JSON structure |

### 3.9 ArticleDraft
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID (PK) | |
| `project_id` | UUID (FK → projects) | |
| `keyword_id` | UUID (FK → keywords) | |
| `status` | String(50) | "generating" / "passed" / "needs_revision" / "error" |
| `title` | String(255) | |
| `content_markdown` | Text | The generated Master Prompt or final article |
| `audit_score` | Float | 0-100 |
| `generation_attempts` | Integer | |
| `research_summary` | JSON | Contains `brief`, `competitor_pages`, `own_pages`, `master_prompt` |
| `audit_feedback` | JSON | Contains `score`, `passed`, `strengths`, `issues`, `revision_notes` |

### 3.10 GoldHunterScan
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID (PK) | |
| `user_id` | UUID (FK → users) | |
| `input_url` | String(2048) | |
| `audit_summary` | Text | Full AI audit text |
| `seeds` | JSON | Array of `{keyword, justification}` |

---

## 4. API ENDPOINTS

### 4.1 Authentication (`/api/auth`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/register` | Register new user (email, password, full_name) |
| POST | `/api/auth/login` | Login (email, password) → JWT token |
| GET | `/api/auth/me` | Get current user profile |

### 4.2 Projects (`/api/projects`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/projects` | List all user projects |
| POST | `/api/projects` | Create new project |
| GET | `/api/projects/{id}` | Get project detail |
| DELETE | `/api/projects/{id}` | Delete project |
| GET | `/api/projects/{id}/stats` | Get project statistics |
| GET | `/api/projects/{id}/sources` | Get grouped source domains |

### 4.3 Scan (`/api/projects/{id}/scan`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `.../scan/start` | Start a new scan (dispatches background pipeline) |
| GET | `.../scan/status` | Get scan progress (percent, URLs found/processed) |
| POST | `.../scan/pause` | Pause a running scan |
| POST | `.../scan/resume` | Resume a paused scan |
| GET | `.../scan/jobs` | List recent scan jobs |

### 4.4 Keywords (`/api/projects/{id}/keywords`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `.../keywords` | List keywords (paginated, filterable, sortable) |
| POST | `.../keywords/generate` | Generate AI keywords from seed keywords |
| POST | `.../keywords/top-picks` | Generate top 5-10 picks from existing keywords |
| POST | `.../keywords/hub-spoke` | Generate Hub & Spoke clustering |
| GET | `.../keywords/hub-spoke` | Get existing Hub & Spoke data |
| GET | `.../keywords/export` | Export keywords as CSV |
| POST | `.../keywords/{kw_id}/save` | Save keyword to bank |
| POST | `.../keywords/bulk-save` | Bulk save keywords |
| POST | `.../keywords/bulk-delete` | Bulk delete keywords |

### 4.5 Keyword Bank (`/api/keyword-bank`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/keyword-bank` | Get user's saved keywords |
| POST | `/api/keyword-bank/bulk-action` | Bulk mark done / not done / delete |

### 4.6 Content (`/api/projects/{id}`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `.../keywords/{kw_id}/article/generate` | Generate article Master Prompt for a keyword |
| POST | `/api/projects/manual-generate` | Generate prompt from manual keyword input |
| POST | `.../articles/{art_id}/write-final` | Write the final article from the Master Prompt |
| GET | `.../articles` | List article drafts |

### 4.7 Website Prompts (`/api/website-prompts`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `.../analyze-intent` | Analyze search intent for a keyword |
| POST | `.../generate` | Generate a full website prompt |
| POST | `.../generate-gap-page` | Generate a gap page prompt |

### 4.8 Gold Hunter (`/api/goldhunter`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/goldhunter/scan` | Audit a URL and extract 3 seed keywords |
| GET | `/api/goldhunter/history` | Get scan history |

### 4.9 Health
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Returns `{"status": "ok"}` |

---

## 5. THE SCAN PIPELINE (Multithreaded)

**File:** `backend/workers/pipeline.py` → `run_full_pipeline()`

### Step-by-Step Flow:

1. **Load Project & Job** from the database.
2. **Extract seed keywords** from `project.target_keywords`.
3. **Discover competitor domains** via Google search (DuckDuckGo or Apify).
   - Uses an LLM "Competitor Judge" agent to validate domains are true competitors.
4. **Concurrent URL Discovery (4 threads):**
   - Each thread takes a domain from a queue.
   - Calls `extract_all_urls_from_domain()` (sitemap parsing + crawl fallback).
   - Applies URL filter patterns (e.g., `/blog/`, `/news/`).
   - Saves discovered URLs to the database.
   - Pushes URL IDs into a shared `url_queue`.
5. **Concurrent Scraping & Extraction (4 threads):**
   - Each thread pulls batches of 50 URL IDs from the `url_queue`.
   - Scrapes basic metadata (H1, word count) from URL slug structure.
   - Calls `extract_keywords_from_urls_ai()` to extract keywords from URL slugs.
   - **IMMEDIATELY** runs `filter_keyword_gap_recommendations()` (the strict LLM sanity filter) on the chunk.
   - Stores only the filtered keywords to the database via `_store_keywords()`.
   - This allows keywords to appear in real-time on the frontend.
6. **AI Keyword Generation:** Calls `generate_ai_keywords_sync()` to create 25 additional AI-recommended keywords. These also pass the strict filter.
7. **Sync project counts** and mark the job as complete.

### Key Helper Functions:
- `_discover_competitor_domains()` — Google search → LLM competitor judge
- `_discover_content_urls()` — Sitemap parsing + crawl fallback + URL filtering
- `_queue_discovered_urls()` — Save URL rows to DB
- `_url_keyword_candidates()` — Extract candidate phrases from URL slug
- `_refine_keyword_gap_recommendations()` — Full LLM filter + heuristic fallback
- `_remove_covered_keywords()` — Remove keywords already on the user's own site
- `_store_keywords()` — Upsert keywords + KeywordUrl links to DB
- `_own_sitemap_keyword_phrases()` — Extract keywords from own site URLs

---

## 6. AI AGENT PROMPTS (ALL PROMPTS)

All prompts are defined in `backend/nlp/openrouter.py`.

### 6.1 Gold Nugget Agent (`generate_gold_hunter_seeds`)

**Purpose:** Audit any URL and extract 3 high-value seed keywords.

```
[SYSTEM COMMANDS]

You are the Gold Nugget Agent. Your purpose is to mine 3 high-value seed keywords from any given URL.

INPUT URL: {url}
URL CONTENT: {url_content[:10000]}

PHASE 1: SITE AUDIT
Audit the URL's visible content (Title, H1, Meta, Features, Copy). Extract:
- Primary Keyword
- Industry / Niche
- Core Action (the exact transformation the tool performs)
- Target Audience
- Capabilities (DOES)
- Hard Boundaries (DOES NOT)

PHASE 2: DOMAIN FENCING
Ban umbrella terms (general, basic, professional, engineering). Block adjacent misaligned domains. If the Primary Keyword is vague, force-inject the strongest specific anchor discovered during the audit.

PHASE 3: GAP DISCOVERY
Identify missing elements. Classify into:
- Tool Gaps (missing features, sub-tools, variations)
- Content Gaps (missing educational guides, comparisons, use-case tutorials)
Generate a pool of 5-6 candidate seeds that directly relate to the Core Action.

PHASE 4: THE TRIPLE GATE FILTER (MANDATORY)
Reject any seed that fails any single gate.

Gate A (Volume): Must imply 1,000+ monthly searches.
Gate B (Sitemap Depth): The Top 10 results must be content-heavy sites with deep sitemaps.
Gate C (Thematic Relevance): The seed must explicitly tie back to the site's Core Action.

PHASE 5: USE-CASE BROADENING (THE PIVOT)
If the Primary Keyword fails the Sitemap Gate due to shallow tool competitors, force-inject a high-volume, content-rich use-case modifier.

PHASE 6: FINAL OUTPUT
Select the 3 strongest seeds. Provide audit summary and 3 seeds with justifications.

Return JSON: { "audit_summary": "...", "seeds": [...] }
```

### 6.2 AI Keyword Generator (`generate_ai_keywords` / `generate_ai_keywords_sync`)

**Purpose:** Generate 25 high-quality keyword opportunities from seed keywords.

```
You are an expert SEO keyword strategist. Use the seed keywords as the strict topic boundary.
Generate exactly 25 high-quality keyword opportunities: exactly 5 primary, 5 LSI, 5 long-tail, 5 entity, and 5 heading keywords.

Seed keywords: {seed_keywords}

Quality rules:
- Every keyword MUST be highly semantically relevant to the primary seed keywords.
- Absolutely NO unrelated keywords, hallucinated terms, or irrelevant BS.
- Keep phrases natural, lowercase, 2 to 6 words.
- Every phrase must include at least one meaningful seed keyword term exactly.
- For LSI keywords, include the seed term plus a semantic modifier.

Return JSON array: [{"phrase": "...", "type": "primary|lsi|long-tail|entity|heading"}]
```

### 6.3 URL Keyword Extractor (`extract_keywords_from_urls_ai`)

**Purpose:** Extract SEO keywords from competitor URL slugs.

```
[SYSTEM COMMAND — URL KEYWORD EXTRACTION]
You are an expert SEO data analyst.
Seed topic: {seed_keywords}

I will provide a JSON array of competitor URLs.
Read the URL slugs and intelligently INFER the exact core SEO keywords those pages are targeting.

Rules:
- ONLY extract keywords highly relevant to the seed topic.
- Normalize keywords to a natural search phrase (lowercase, 2 to 6 words).
- Include the exact UUIDs of the URLs that target each keyword.
- "type" should be one of: primary, lsi, long-tail, entity.

Return JSON array: [{"phrase": "...", "type": "...", "url_ids": ["uuid-1", "uuid-2"]}]
```

### 6.4 Keyword Sanity Filter (`filter_keyword_gap_recommendations`)

**Purpose:** Aggressively filter and deduplicate keyword gap candidates. This is the STRICT filter.

```
[SYSTEM COMMAND — FINAL KEYWORD SANITY FILTER]

**AGENT AUDIT SUMMARY (GOLD HUNTER)**
{audit_summary}

**NEW AUDIT-BASED RULES:**
1. Extract the Core Subject, Core Audience, and Core Action from the Agent Audit Summary.
2. Apply the Hard Block Rules: Reject any keyword or topics outside the Core Subject.
3. Keep only keywords that serve the Core Audience and enable the Core Action.

**Step 0: NATURAL LANGUAGE NORMALIZATION (CRITICAL)**
For every raw keyword, rewrite it into a natural human search query:
- Reverse awkward structures: "board games using spin wheel" → "spin the wheel board game"
- Remove redundant words
- Use common search patterns
- Prioritize shorter, standard collocations (3-4 words)

**Step 1: STRICT SEED RELEVANCE GATE (CRITICAL)**
Compare against seed keywords. If completely unrelated, REJECT IMMEDIATELY.

**Step 2: Volume Gate**
Estimate monthly search volume. Keep if 500+, reject if below.

**Step 3: Intent Clustering (Anti-Cannibalization)**
Group queries sharing the same user intent. Merge subset phrases. Select highest-volume as PRIMARY.

**Step 4: Final Output**
Output ONLY one keyword per intent cluster (max {max_keywords}).
Return JSON: [{"source_phrase": "...", "phrase": "...", "volume": "High|Medium|Low", "type": "..."}]
```

### 6.5 Competitor Domain Judge (`judge_competitor_domains`)

**Purpose:** Final gatekeeper for whether a domain is a true competitor.

```
You are the final competitor judge for an SEO SaaS.

**AGENT AUDIT SUMMARY (GOLD HUNTER)**
{audit_summary}

**AUDIT-BASED RULES:**
1. Extract Core Subject, Core Audience, Core Action from the Audit Summary.
2. Reject sites not thematically relevant.

Target site: {own_domain}
Primary keyword set: {seed_keywords}
Candidate competitors: {candidates}

STRICT TOPICAL NICHE MATCH: Aggressively reject any domain that belongs to a broader industry or different topical niche.
Reject dictionaries, marketplaces, social networks, forums, docs portals, and generic informational sites.
Only accept domains that are DIRECT, dedicated competitors.

Return JSON: [{"domain": "...", "verdict": "accept|reject", "confidence": 0-100, "reason": "..."}]
```

### 6.6 AI Top Picks (`generate_ai_top_picks`)

**Purpose:** Select the absolute best 5-10 keywords FROM the existing keyword list.

```
You are an expert SEO keyword strategist.
Select the absolute best 5 to 10 keywords STRICTLY FROM THIS LIST.
These should be "Top Picks" - high intent, strong relevance, and maximum SEO value.

Seed keywords: {seed_keywords}
Existing keywords (choose ONLY from these): {existing_keywords}

Return JSON: [{"phrase": "exact phrase from list", "type": "primary|long-tail"}]
```

### 6.7 Hub & Spoke Clusterer (`cluster_hub_and_spoke`)

**Purpose:** Organize keywords into a topical authority map.

```
Take a raw, flat Hub-and-Spoke list of keywords and transform it into a visually optimized, layered, ranking-ready SEO architecture.

Step 1: The Master Hub — Identify the broadest core entity.
  ├── 🧱 FOUNDATION SPOKES (Authority)
  └── 💰 MASTER COMMERCIAL SPOKES

Step 2: Sub-Silos — 2-5 distinct sub-themes.
  Each Sub-Silo enforces the 3-Layer Stack:
  1. 🧱 Foundations: "What Is X?", "History of X", Databases
  2. ⚙️ Action: "How to X", "Step-by-Step", Tutorials, Tools
  3. 💰 Money: "Best X", "Buy X", "X Services"

Step 3: Intent Tagging — Append [Tool] or [Blog] to each spoke.

Step 4: Zero Competition Quick-Wins — AI-generated keywords go to ⚡️ layer.

Return JSON: {"hubs": [{"hub_title": "...", "layers": {"🧱 ...": ["..."], "💰 ...": ["..."]}}]}
```

### 6.8 Article Brief Builder (`build_article_brief`)

**Purpose:** Create a writer-ready brief from competitor research.

```
You are a master SEO content strategist building a writer-ready brief for a gap keyword article.

Return JSON with:
- "search_intent", "reader_persona", "article_angle"
- "recommended_title", "meta_description"
- "content_gaps": 5-10 competitor weaknesses
- "competitor_takeaways": 4-8 patterns from competitors
- "unique_value": 4-8 ways to be more useful
- "must_include_terms": 8-16 important terms
- "proof_points": 3-8 evidence types
- "outline": 7-12 section objects with heading, intent, points
- "faq": 4-8 question/answer_angle objects
- "avoid": 4-8 pitfalls
```

### 6.9 Master Prompt Writer (`write_prompt`)

**Purpose:** Generate a complete Master Prompt template for article writing.

The Master Prompt includes these sections:
1. `# CONTENT WRITING ASSIGNMENT` — Primary keyword
2. `# ARTICLE STRUCTURE` — Full heading outline (H1, H2s with bullet points)
3. `# SEMANTIC OPTIMIZATION` — Entities, key phrases, NLP keywords
4. `# SEO GUIDELINES` — 30+ detailed SEO writing rules including:
   - Don't distance the question from the answer
   - Singularity and plurality matter for micro semantics
   - Don't use analogies
   - Avoid coreference errors
   - Bold the answer, not the search term
   - Put "if" statements in the second part of the sentence
   - Boolean questions should start with Yes or No
   - Use numeric values
   - Cut the fluff out
   - Be certain (state facts, not possibilities)
   - etc.
5. `# INTRODUCTION WRITING INSTRUCTIONS` — Implicit definition, benefits, uses, components
6. `# COMPETITOR CONTENT ANALYSIS` — Full competitor content for reference
7. Ends with `BEGIN WRITING THE ARTICLE NOW:`

### 6.10 Prompt Auditor (`audit_prompt`)

**Purpose:** Verify the Master Prompt has all required sections.

```
Verify:
1. Starts with "# CONTENT WRITING ASSIGNMENT"
2. Has "## PRIMARY KEYWORD" section
3. Has "# ARTICLE STRUCTURE" with outline
4. Has "# SEO GUIDELINES"
5. Has "# INTRODUCTION WRITING INSTRUCTIONS"
6. Ends with "BEGIN WRITING THE ARTICLE NOW:"

Return JSON: {"score": 0-100, "passed": bool, "strengths": [...], "issues": [...], "revision_notes": [...]}
```

### 6.11 Article Writer (`write_final_article`)

**System prompt:**
```
You are a world-class SEO strategist, subject-matter ghostwriter, and ruthless editor.
You write practical, source-grounded articles that satisfy search intent and outperform generic competitor content.
```

Uses the Master Prompt as the user prompt. Temperature: 0.28, max_tokens: 4500. Uses the writing model.

### 6.12 Article Auditor (`audit_article`)

**Purpose:** Grade whether the article deserves to be published.

```
Audit this SEO article as a demanding SEO editor.

Return JSON:
- "score": 0-100
- "passed": boolean
- "keyword_intent_score": 0-100
- "gap_coverage_score": 0-100
- "strengths", "issues", "revision_notes", "missing_sections"

Pass criteria:
- score >= 92
- keyword_intent_score >= 90
- gap_coverage_score >= 90
```

The article generation pipeline will retry up to 20 times until the article passes.

---

## 7. ARTICLE GENERATION PIPELINE

**File:** `backend/app/content/service.py`

### Phase 1: Master Prompt Generation
1. Collect competitor research pages (scrape content from competitor URLs).
2. Search Google for additional competitor content if needed.
3. Use LLM Competitor Judge to validate competitor domains.
4. Build article brief via `build_article_brief()`.
5. Generate Master Prompt via `write_prompt()`.
6. Audit the Master Prompt via `audit_prompt()`.
7. Repeat up to 5 attempts until audit passes (score ≥ 92).

### Phase 2: Final Article Generation
1. Feed the Master Prompt to `write_final_article()`.
2. Run local quality checks (`_local_article_quality_issues()`):
   - No code fences in article
   - No AI meta commentary ("as an AI...")
   - At least 900 words
   - Exactly one H1
   - At least five H2 sections
   - Primary keyword appears in text
   - FAQ section exists
3. Run LLM article audit via `audit_article()`.
4. If score < 92, generate revision notes and retry.
5. Repeat up to 20 attempts.

---

## 8. CONFIGURATION (Environment Variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./sitemapseo.db` | Async database URL |
| `SYNC_DATABASE_URL` | Auto-derived | Sync database URL for pipeline worker |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis for Celery |
| `USE_CELERY` | `false` | Use Celery workers vs BackgroundTasks |
| `SECRET_KEY` | `super-secret-jwt-key...` | JWT signing key |
| `FRONTEND_URL` | `http://localhost:3000` | CORS allowed origin |
| `TOKENROUTER_API_KEY` | `""` | Primary AI provider |
| `TOKENROUTER_MODEL` | `moonshotai/kimi-k3-free` | Default model |
| `TOKENROUTER_WRITING_MODEL` | `moonshotai/kimi-k3-free` | Writing model |
| `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL` | | DeepSeek fallback |
| `GROQ_API_KEY` / `GROQ_MODEL` | | Groq fallback |
| `OPENROUTER_API_KEY` / `OPENROUTER_MODEL` | | OpenRouter fallback |
| `APIFY_API_TOKEN` | `""` | Apify for Google search & crawling |
| `MAX_URLS_PER_SCAN` | `5000` | Max URLs to discover per scan |
| `MAX_COMPETITOR_DOMAINS` | `10` | Max competitor domains to analyze |
| `GOOGLE_SERP_RESULT_LIMIT` | `10` | Google results per query |
| `MAX_CONTENT_URLS_PER_DOMAIN` | `8` | URLs to extract per competitor domain |
| `MAX_COMPETITOR_JUDGE_CANDIDATES` | `20` | Domains to send to LLM judge |
| `AI_KEYWORD_GAP_CANDIDATE_LIMIT` | `80` | Max candidates for keyword filter |
| `AI_KEYWORD_GAP_RESULT_LIMIT` | `60` | Max results from keyword filter |
| `ARTICLE_RESEARCH_SOURCE_LIMIT` | `5` | Competitor pages to scrape for articles |
| `ARTICLE_GENERATION_MAX_ATTEMPTS` | `5` | Master Prompt generation retries |

### AI Provider Priority (checked in order):
1. **TokenRouter** → `TOKENROUTER_API_KEY`
2. **DeepSeek** → `DEEPSEEK_API_KEY`
3. **Groq** → `GROQ_API_KEY`
4. **OpenRouter** → `OPENROUTER_API_KEY`

The `use_writing_model=True` flag switches to `TOKENROUTER_WRITING_MODEL` for article-length generation tasks.

---

## 9. FRONTEND PAGES & COMPONENTS

### 9.1 Dashboard Routes
| Route | Page | Description |
|-------|------|-------------|
| `/` | `ProjectsList` | Home — list of projects with create/delete |
| `/projects/:id` | `ProjectDetail` | Scan progress, keyword table, Hub/Spoke view |
| `/gold-hunter` | `GoldHunter` | URL audit → seed keyword extraction |
| `/website-prompts` | `WebsitePromptGenerator` | Generate website prompts |
| `/gap-page-prompts` | `GapPageGenerator` | Generate gap page prompts |
| `/scan` | `ScanInterface` | Quick scan interface |
| `/write-blog` | `WriteBlog` | Manual article generation |
| `/write-blog/:projectId` | `WriteBlogArticle` | Article view/edit |
| `/saved-keywords` | `SavedKeywords` | Keyword bank |
| `/settings` | `Settings` | User settings |
| `/login` / `/register` | Auth pages | |

### 9.2 Key Components
- **KeywordsTable:** Paginated table with type filter, search, multi-select, bulk save/delete, CSV export, article generation
- **HubSpokeView:** Visual tree rendering of the Hub & Spoke JSON structure
- **CompetitorGraph:** Shows competitor domains and their URL counts
- **LiveSignals:** Real-time scan progress indicators
- **GeneratedArticlePanel:** Markdown preview of generated articles with audit scores
- **SemanticMetrics:** Semantic analysis visualization

### 9.3 API Client (`dashboard/src/lib/api.ts`)
- Uses `fetch()` with JWT Bearer token auth
- Automatic redirect to `/login` on 401
- 20s timeout for normal requests, 5min timeout for article generation
- Has a demo backend mode (`VITE_ENABLE_DEMO_BACKEND=true`) for Vercel preview without a backend

---

## 10. DEPLOYMENT ARCHITECTURE

### Production
- **Backend:** Render Web Service (Python, uvicorn)
- **Frontend:** Vercel (React/Vite static build)
- **Database:** Render PostgreSQL
- **Environment variables** set in Render and Vercel dashboards

### Local Development
```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd dashboard
npm install
npm run dev
```

### Docker (Full Stack)
```bash
docker-compose up -d
# postgres:5432 + redis:6379 + backend:8000 + celery worker + dashboard:3000
```

---

## 11. NLP & KEYWORD PROCESSING

**File:** `backend/nlp/keywords.py`

Key functions:
- `clean_phrase(phrase)` — Lowercase, strip, normalize whitespace
- `is_publishable_keyword(phrase, min_words=2, topic_terms=None)` — Validates a keyword is display-worthy (not too short, not stopword-only, not gibberish)
- `seed_keyword_terms(keywords)` — Extract unique non-stopword terms from seed keywords
- `extract_keywords_from_page(text, ...)` — SpaCy + RAKE + KeyBERT extraction from page text

**Stopwords, blocked patterns, and quality rules** ensure that only natural, searchable phrases make it through the pipeline.

---

## 12. SCRAPING SUBSYSTEM

### 12.1 Sitemap Parser (`backend/scraping/sitemap.py`)
- `extract_all_urls_from_domain(domain)` — Fetches `/sitemap.xml`, `/sitemap_index.xml`, `/robots.txt` for sitemap references
- Recursively parses nested sitemap indexes
- Falls back to a shallow crawl if no sitemap found

### 12.2 Page Crawler (`backend/scraping/crawler.py`)
- `scrape_page(url, ...)` — Full page scraping with:
  - BeautifulSoup + trafilatura text extraction
  - H1, H2, H3 heading extraction
  - Word count, readability score (textstat)
  - Publish date detection
  - Retry logic with configurable delays

### 12.3 URL Filters (`backend/scraping/filters.py`)
- `filter_blog_urls(urls, patterns)` — Keep only URLs matching content patterns
- Filters out images, PDFs, static assets, login pages, etc.

### 12.4 Apify Integration (`backend/scraping/apify_client_module.py`)
- `search_google_via_apify(query, max_results, country_code)` — Real Google SERP results
- `crawl_competitor_content_via_apify(domain, max_pages)` — Playwright-based crawling
- `extract_apify_page_content(url)` — Single page extraction via Cheerio scraper

---

## 13. KEYWORD QUALITY PIPELINE (How keywords are filtered)

The keyword filtering pipeline has multiple layers:

1. **URL Slug Extraction:** Keywords are extracted from competitor URL path segments (e.g., `/best-circuit-diagram-maker` → "best circuit diagram maker").

2. **`is_publishable_keyword()`:** Local Python validation — must be 2+ words, not all stopwords, no gibberish patterns.

3. **Seed Relevance Gate:** Keywords must contain at least one term from the seed keywords.

4. **Own-Site Deduplication:** Keywords already present on the user's own website URLs are removed.

5. **LLM Sanity Filter (`filter_keyword_gap_recommendations`):** The strict AI filter that:
   - Uses the Gold Hunter audit summary to extract Core Subject, Core Audience, Core Action
   - Rejects anything outside the core topic
   - Normalizes awkward phrasings
   - Estimates search volume (reject < 500)
   - Clusters by intent to prevent cannibalization
   - Returns at most 60 filtered keywords

6. **Hub & Spoke Clustering:** Final organizational layer grouping keywords into a topical authority map.

---

## 14. AUTHENTICATION SYSTEM

- **JWT-based** authentication with HS256 algorithm
- Tokens expire after 7 days (`ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7`)
- Password hashing with bcrypt
- `get_current_user` FastAPI dependency extracts user from Bearer token
- Frontend stores token in `localStorage`

---

*End of Full Context Document*
