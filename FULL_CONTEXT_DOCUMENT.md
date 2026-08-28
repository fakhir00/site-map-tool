# SiteMapSEO — Full SaaS Context Document (v2)

> **Purpose:** This document describes every component, database model, API endpoint, AI agent prompt, pipeline step, algorithm, configuration setting, and design decision of the SiteMapSEO SaaS application. It is designed so that any LLM or engineer can fully understand the entire system at 100% depth and answer any question about it.

> **Last Updated:** 2026-08-27

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
- **NLP:** `spacy` (en_core_web_sm), `rake-nltk`, `keybert` (all-MiniLM-L6-v2), `nltk`, `scikit-learn`, `sentence-transformers`
- **Task Queue:** Celery + Redis (production), FastAPI BackgroundTasks (local dev)
- **Deployment:** Backend on Render, Frontend on Vercel, PostgreSQL on Render
- **Containerization:** `docker-compose.yml` for full local stack (postgres + redis + backend + celery worker + dashboard)

---

## 2. REPOSITORY STRUCTURE

```
sit map tool/
├── .env                              # Root env vars (DEEPSEEK_API_KEY, etc.)
├── docker-compose.yml                # Full local stack: postgres + redis + backend + worker + dashboard
├── sitemapseo.db                     # Root SQLite DB (for quick local testing)
├── FULL_CONTEXT_DOCUMENT.md          # THIS FILE
├── QA_Engineer_claude_skill.md       # QA agent skill document
├── antigravity_4tier_clustering_and_hubspoke.md  # Architecture reference doc
├── master-prompt-theme.txt           # Master prompt template reference
├── test_*.py                         # Various root-level test scripts
│
├── backend/
│   ├── .env                          # Backend-specific env vars
│   ├── Dockerfile                    # Python 3.11 container image
│   ├── requirements.txt              # All Python dependencies
│   ├── init.sql                      # PostgreSQL schema bootstrap
│   ├── init_db.py                    # DB initialization script
│   ├── sitemapseo.db                 # Backend SQLite DB (primary local dev)
│   ├── diag.py                       # Diagnostic script
│   ├── test_diag.py                  # Hub-spoke test diagnostic
│   ├── test_hub.py                   # Hub-spoke integration test
│   ├── test_kw4.py / test_kw5.py / test_kw6.py  # Keyword tier classification tests
│   ├── test_pydantic.py              # Schema validation tests
│   ├── prompt_output.txt             # Sample LLM prompt output for debugging
│   │
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                   # FastAPI app entry point, CORS, lifespan, runtime schema migrations
│   │   ├── config.py                 # Pydantic Settings (all env vars with defaults)
│   │   ├── database.py               # Async SQLAlchemy engine + session factory (get_db dependency)
│   │   ├── models.py                 # All SQLAlchemy ORM models (12 tables)
│   │   ├── schemas.py                # All Pydantic request/response schemas
│   │   │
│   │   ├── auth/
│   │   │   ├── router.py             # POST /api/auth/register, /api/auth/login, GET /api/auth/me
│   │   │   └── jwt.py                # JWT token creation + get_current_user dependency
│   │   │
│   │   ├── projects/
│   │   │   └── router.py             # CRUD for projects (/api/projects)
│   │   │
│   │   ├── scan/
│   │   │   └── router.py             # Start/Pause/Resume/Status of scans
│   │   │
│   │   ├── keywords/
│   │   │   └── router.py             # List/Generate/Export/Save/Delete keywords, Hub-Spoke, Top Picks
│   │   │                             # (835 lines — the LARGEST router, contains Phase 1-5 Hub-Spoke logic)
│   │   │
│   │   ├── content/
│   │   │   ├── router.py             # Article generation endpoints
│   │   │   └── service.py            # Article generation pipeline (brief → prompt → audit loop)
│   │   │
│   │   ├── goldhunter/
│   │   │   ├── router.py             # POST /api/goldhunter/scan, GET /api/goldhunter/history
│   │   │   └── scraper.py            # fetch_url_content() for Gold Hunter
│   │   │
│   │   └── website_prompts/
│   │       ├── router.py             # Intent analysis + prompt generation
│   │       └── service.py            # Intent + Prompt + Gap Page flows
│   │
│   ├── nlp/
│   │   ├── openrouter.py             # ALL AI agent prompts and LLM API calls (1500 lines)
│   │   └── keywords.py               # Keyword extraction, cleaning, validation, NLP utilities,
│   │                                 # 4-Tier clustering, intent hashing, cannibalization detection (556 lines)
│   │
│   ├── scraping/
│   │   ├── sitemap.py                # XML sitemap parsing, extract_all_urls_from_domain()
│   │   ├── crawler.py                # HTTP scraping with BeautifulSoup/trafilatura
│   │   ├── filters.py                # URL filtering (filter_blog_urls, etc.)
│   │   └── apify_client_module.py    # Google search via Apify, website crawling
│   │
│   └── workers/
│       ├── pipeline.py               # The main scan pipeline (1615 lines — multithreaded)
│       └── celery_app.py             # Celery application config (for production)
│
├── dashboard/
│   ├── package.json / vite.config.ts / tsconfig.json
│   └── src/
│       ├── App.tsx                    # React Router setup (public/private routes)
│       ├── main.tsx                   # Vite entry point
│       ├── index.css / App.css        # Global styles
│       │
│       ├── lib/
│       │   ├── api.ts                # API client (fetch wrapper, auth, types)
│       │   └── demoBackend.ts        # In-browser demo backend for Vercel preview
│       │
│       ├── pages/
│       │   ├── ProjectsList.tsx       # Dashboard home — list of projects
│       │   ├── ProjectDetail.tsx      # Project detail — scan progress + keyword table
│       │   ├── GoldHunter.tsx         # Gold Hunter URL audit
│       │   ├── WebsitePromptGenerator.tsx  # Website prompt generator
│       │   ├── GapPageGenerator.tsx   # Gap page prompt generator
│       │   ├── ScanInterface.tsx      # Quick scan interface
│       │   ├── WriteBlog.tsx          # Blog article generation
│       │   ├── WriteBlogArticle.tsx   # Individual article view
│       │   ├── SavedKeywords.tsx      # Keyword bank
│       │   ├── Login.tsx              # Login page
│       │   ├── Register.tsx           # Registration page
│       │   └── Settings.tsx           # User settings
│       │
│       └── components/
│           ├── DashboardLayout.tsx    # Sidebar + top nav + responsive drawer
│           ├── KeywordsTable.tsx      # Main keyword results table (paginated, filterable)
│           ├── HubSpokeView.tsx       # Hub & Spoke visualization (tree rendering)
│           ├── CompetitorGraph.tsx     # Competitor domain graph
│           ├── SemanticMetrics.tsx     # Semantic analysis metrics
│           ├── LiveSignals.tsx        # Live scan progress signals
│           ├── GeneratedArticlePanel.tsx  # Article preview panel
│           ├── SavedKeywordsTable.tsx  # Saved keywords table
│           ├── ThemeProvider.tsx       # Dark/light theme context
│           ├── ThemeToggle.tsx         # Theme toggle button
│           └── ui/                    # shadcn/ui primitives
│
└── marketing/                         # Marketing assets directory
```

---

## 3. DATABASE MODELS (12 Tables)

**File:** `backend/app/models.py` (200 lines)

### 3.1 User
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID (PK) | Auto-generated via `uuid.uuid4` |
| `email` | String(255) | Unique, required |
| `password_hash` | String(255) | bcrypt hash |
| `full_name` | String(255) | Optional |
| `google_id` | String(255) | For Google OAuth |
| `plan` | String(50) | Default: `"free"` |
| `is_active` | Boolean | Default: `True` |
| `created_at` / `updated_at` | DateTime (TZ) | |

**Relationships:** `projects`, `keyword_bank`, `goldhunter_scans`

### 3.2 Project
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID (PK) | |
| `user_id` | UUID (FK → users) | CASCADE delete |
| `name` | String(255) | Project display name |
| `domain` | String(512) | Target competitor domain to analyze |
| `own_domain` | String(512) | User's own website domain |
| `scan_frequency` | String(50) | Default: `"once"` |
| `url_filter_patterns` | JSON | Default: `["/blog/", "/news/", "/post/", "/article/"]` |
| `target_keywords` | JSON | Array of seed keyword strings |
| `audit_summary` | Text | Gold Hunter audit summary (used for strict filtering) |
| `status` | String(50) | `"pending"` / `"running"` / `"paused"` / `"complete"` / `"error"` |
| `search_locale` | String(10) | Default: `"us"` |
| `urls_found` / `urls_processed` / `urls_failed` / `total_keywords` | Integer | Live counters |
| `created_at` / `last_scanned_at` / `next_scan_at` | DateTime | |

**Relationships:** `scan_jobs`, `urls`, `keywords`, `article_drafts`

### 3.3 ScanJob
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID (PK) | |
| `project_id` | UUID (FK → projects) | |
| `status` | String(50) | `"queued"` / `"running"` / `"complete"` / `"error"` |
| `celery_task_id` | String(255) | Celery task ID or `"local-background-task"` |
| `error_message` | Text | |
| `started_at` / `finished_at` / `created_at` | DateTime | |

### 3.4 Url
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID (PK) | |
| `project_id` | UUID (FK → projects) | |
| `scan_job_id` | UUID (FK → scan_jobs) | Optional |
| `url` | Text | Full URL |
| `source_type` | String(50) | `"own"` / `"competitor"` / `"ai"` |
| `source_domain` | String(512) | e.g., `"competitor.com"` or `"AI Recommendations"` |
| `status` | String(50) | `"pending"` / `"scraped"` / `"failed"` |
| `h1` | Text | Page H1 heading (extracted from slug) |
| `word_count` | Integer | |
| `readability_score` | Float | |
| `publish_date` | Date | |
| `scraped_at` | DateTime | |
| `retry_count` | Integer | Default: 0 |

**Unique constraint:** `(project_id, url)`

### 3.5 Keyword
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID (PK) | |
| `project_id` | UUID (FK → projects) | |
| `phrase` | Text | The keyword phrase |
| `keyword_type` | String(50) | `"primary"` / `"lsi"` / `"long-tail"` / `"entity"` / `"heading"` / `"top-pick"` |
| `frequency` | Integer | How many competitor URLs target this keyword |
| `search_volume` | Integer | Estimated (nullable) |
| `difficulty` | Float | Estimated (nullable) |
| `tier` | String(50) | `"merge"` / `"subheading_group"` / `"related"` / `"outlier"` (nullable) |
| `sub_silo_id` | Integer | Sub-silo assignment (nullable) |
| `cluster_group_id` | String(100) | For `"related"` tier cross-linking (nullable) |
| `article_title` | Text | For `"subheading_group"` broadest phrase (nullable) |
| `h_tags` | JSON | For `"subheading_group"` other cluster members (nullable) |
| `merged_from` | JSON | For `"merge"` tier, dropped duplicate phrases (nullable) |
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
| `done_at` | DateTime | When marked done |

**Unique constraint:** `(user_id, keyword_id)`
**Query behavior:** Done items are hidden after 2 days.

### 3.8 HubSpokeCluster
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID (PK) | |
| `project_id` | UUID (FK, unique) | One cluster per project |
| `mapping_data` | JSON | The full Hub/Spoke JSON structure |
| `created_at` | DateTime | |

### 3.9 ArticleDraft
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID (PK) | |
| `project_id` | UUID (FK → projects) | |
| `keyword_id` | UUID (FK → keywords) | |
| `status` | String(50) | `"generating"` / `"passed"` / `"needs_revision"` / `"error"` |
| `title` | String(255) | |
| `content_markdown` | Text | The generated Master Prompt or final article |
| `audit_score` | Float | 0-100 |
| `generation_attempts` | Integer | |
| `research_summary` | JSON | Contains `brief`, `competitor_pages`, `own_pages`, `master_prompt` |
| `audit_feedback` | JSON | Contains `score`, `passed`, `strengths`, `issues`, `revision_notes` |
| `created_at` / `updated_at` | DateTime | |

**Index:** `ix_article_drafts_project_created_at` on `(project_id, created_at)`

### 3.10 GoldHunterScan
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID (PK) | |
| `user_id` | UUID (FK → users) | |
| `input_url` | String(2048) | |
| `audit_summary` | Text | Full AI audit text |
| `seeds` | JSON | Array of `{keyword, justification}` |
| `created_at` | DateTime | |

---

## 4. RUNTIME SCHEMA MIGRATIONS

**File:** `backend/app/main.py` → `_ensure_runtime_schema()`

On startup, the app checks for missing columns and adds them if needed. This handles schema evolution without formal migration tools:

**SQLite path:**
- Uses `PRAGMA table_info(tablename)` to check existing columns
- Adds missing columns via `ALTER TABLE ... ADD COLUMN`

**PostgreSQL path:**
- Uses `information_schema.columns` to check existing columns
- Converts `url_filter_patterns` from `ARRAY` to `JSONB` if needed

**Migrated columns:**
- `projects.target_keywords` (JSON)
- `projects.search_locale` (VARCHAR(10))
- `urls.source_type` (VARCHAR(50))
- `urls.source_domain` (VARCHAR(512))
- `keywords.tier` (VARCHAR(50))
- `keywords.sub_silo_id` (INTEGER)
- `keywords.cluster_group_id` (VARCHAR(100))
- `keywords.article_title` (TEXT)
- `keywords.h_tags` (JSON)
- `keywords.merged_from` (JSON)

---

## 5. API ENDPOINTS (All Routes)

### 5.1 Authentication (`/api/auth`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/register` | Register new user (email, password, full_name) |
| POST | `/api/auth/login` | Login (email, password) → JWT token |
| GET | `/api/auth/me` | Get current user profile |

### 5.2 Projects (`/api/projects`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/projects` | List all user projects |
| POST | `/api/projects` | Create new project |
| GET | `/api/projects/{id}` | Get project detail |
| DELETE | `/api/projects/{id}` | Delete project |
| GET | `/api/projects/{id}/stats` | Get project statistics |
| GET | `/api/projects/{id}/sources` | Get grouped source domains |

### 5.3 Scan (`/api/projects/{id}/scan`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `.../scan/start` | Start a new scan (dispatches background pipeline) |
| GET | `.../scan/status` | Get scan progress (percent, URLs found/processed) |
| POST | `.../scan/pause` | Pause a running scan |
| POST | `.../scan/resume` | Resume a paused scan |
| GET | `.../scan/jobs` | List recent scan jobs (max 20) |

### 5.4 Keywords (`/api/projects/{id}/keywords`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `.../keywords` | List keywords (paginated, filterable, sortable) |
| POST | `.../keywords/generate` | Generate 25 AI keywords from seed keywords |
| POST | `.../keywords/top-picks` | Generate top 5-10 picks from existing keywords |
| POST | `.../keywords/hub-spoke` | Generate Hub & Spoke clustering (Phase 1-5 pipeline) |
| GET | `.../keywords/hub-spoke` | Get existing Hub & Spoke data + tier metadata |
| GET | `.../keywords/export` | Export keywords as CSV |
| POST | `.../keywords/{kw_id}/save` | Save keyword to bank |
| POST | `.../keywords/bulk-save` | Bulk save keywords |
| POST | `.../keywords/bulk-delete` | Bulk delete keywords (cascades to HubSpoke mapping) |

### 5.5 Keyword Bank (`/api/keyword-bank`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/keyword-bank` | Get user's saved keywords (hides done items >2 days old) |
| POST | `/api/keyword-bank/bulk-action` | Bulk mark done / not done / delete |

### 5.6 Content (`/api/projects/{id}`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `.../keywords/{kw_id}/article/generate` | Generate article Master Prompt for a keyword |
| POST | `/api/projects/manual-generate` | Generate prompt from manual keyword input |
| POST | `.../articles/{art_id}/write-final` | Write the final article from the Master Prompt |
| GET | `.../articles` | List article drafts |

### 5.7 Website Prompts (`/api/website-prompts`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `.../analyze-intent` | Analyze search intent for a keyword |
| POST | `.../generate` | Generate a full website prompt |
| POST | `.../generate-gap-page` | Generate a gap page prompt |

### 5.8 Gold Hunter (`/api/goldhunter`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/goldhunter/scan` | Audit a URL and extract 3 seed keywords |
| GET | `/api/goldhunter/history` | Get scan history |

### 5.9 Health
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Returns `{"status": "ok", "service": "SiteMapSEO API"}` |

---

## 6. THE SCAN PIPELINE (Multithreaded)

**File:** `backend/workers/pipeline.py` → `run_full_pipeline()` (1615 lines)

### Step-by-Step Flow:

1. **Load Project & Job** from the database.
2. **Extract seed keywords** from `project.target_keywords`.
3. **Discover competitor domains** via Google search (DuckDuckGo or Apify).
   - Uses an LLM "Competitor Judge" agent to validate domains are true competitors.
4. **Concurrent URL Discovery (4 threads):**
   - Each thread takes a domain from a `domain_queue`.
   - Calls `extract_all_urls_from_domain()` (sitemap parsing + crawl fallback).
   - Applies URL filter patterns (e.g., `/blog/`, `/news/`).
   - Saves discovered URLs to the database.
   - Pushes URL IDs into a shared `url_queue`.
5. **Concurrent Scraping & Extraction (4 threads):**
   - Each thread pulls batches of 50 URL IDs from the `url_queue`.
   - Scrapes basic metadata (H1, word count) from URL slug structure.
   - Calls `extract_keywords_from_urls_ai()` to extract keywords from URL slugs.
   - **IMMEDIATELY** runs `filter_keyword_gap_recommendations()` (the strict LLM sanity filter) on each chunk.
   - Stores only the filtered keywords to the database via `_store_keywords()`.
   - This allows keywords to appear in real-time on the frontend during the scan.
6. **AI Keyword Generation:** Calls `generate_ai_keywords_sync()` to create 25 additional AI-recommended keywords. These also pass the strict filter.
7. **Sync project counts** and mark the job as complete.

### Pipeline Execution Modes:
- **`resume_existing=False`:** Full scan — clears previous results, discovers competitors, crawls everything.
- **`resume_existing=True`:** Resume — picks up pending URLs from the database, skips URL discovery.

### Key Helper Functions:
| Function | Purpose |
|----------|---------|
| `_discover_competitor_domains()` | Google search → LLM competitor judge |
| `_discover_content_urls()` | Sitemap parsing + crawl fallback + URL filtering |
| `_queue_discovered_urls()` | Save URL rows to DB |
| `_url_keyword_candidates()` | Extract candidate phrases from URL slug |
| `_url_display_title()` | Generate human-readable title from URL path |
| `_url_words()` | Extract word tokens from URL path |
| `_refine_keyword_gap_recommendations()` | Full LLM filter + heuristic fallback |
| `_remove_covered_keywords()` | Remove keywords already on the user's own site |
| `_store_keywords()` | Upsert keywords + KeywordUrl links to DB |
| `_own_sitemap_keyword_phrases()` | Extract keywords from own site URLs |
| `_is_blocked_competitor_root()` | Check if domain is in the hardcoded blocklist |
| `_mark_running()` / `_mark_complete()` | Update project + job status |
| `_sync_project_counts()` | Recount URLs and keywords |

### Blocked Competitor Domains:
```python
blocked_roots = {
    "amazon.com", "apple.com", "britannica.com", "cambridge.org",
    "collinsdictionary.com", "colorado.edu", "dictionary.com",
    "duckduckgo.com", "facebook.com", "github.com", "google.com",
    "instagram.com", "linkedin.com", "longdo.com", "merriam-webster.com",
    "microsoft.com", "pinterest.com", "soundcloud.com", "reddit.com",
    "tiktok.com", "wikipedia.org", "x.com", "yahoo.com",
    "yellowpages.com", "youtube.com",
}
```

---

## 7. HUB & SPOKE GENERATION PIPELINE (5 Phases)

**File:** `backend/app/keywords/router.py` → `generate_hub_spoke()` (Lines 225-472)

This is the core endpoint (`POST /{project_id}/keywords/hub-spoke`) that generates the topical authority map. It runs in 5 sequential phases:

### Phase 1: Filter
- Loads all keywords from the project database.
- Drops keywords containing **past years** (e.g., 2023, 2024, 2025 when current year is 2026).
- Drops keywords with `tier` = `"merge"` or `"subheading_group"` (they don't need standalone spokes).
- If zero candidates remain after filtering, raises HTTP 400.

### Phase 2: Send to LLM
- Takes the **top 200** keywords (by frequency) as `clean_keywords_for_llm`.
- Remaining keywords (201+) are stored in `remaining` for Phase 4 auto-placement.
- Each keyword is sent as `{"phrase": ..., "type": ..., "is_ai": ...}`.

### Phase 3: The AI Skeleton
- Calls `cluster_hub_and_spoke()` (in `openrouter.py`) with the 200 keywords.
- This is the main LLM call that returns the full `{hubs: [...]}` JSON structure.
- The LLM prompt enforces **Triple Gate + Hard Rules** (see Section 8).
- Returns the full master hub + sub-silos + layers + spokes.

### Phase 4: Auto-Map Remaining Keywords
- Takes any keywords that weren't in the top 200.
- Uses `phrase_similarity()` (Jaccard on stemmed tokens) to find the best matching spoke in the LLM skeleton.
- Places each overflow keyword into the closest hub/sub-silo/layer with a generated title: `"{phrase.title()} (Target Keyword: {phrase})"`.
- Falls back to `"🧱 Foundations"` layer if no good match found.
- Threshold: Only places if `best_sim > 0` (any positive similarity).

### Phase 5: Semantic Deduplication
This is the **post-processing deduplication layer** that runs AFTER the LLM output:

**Algorithm:**
1. **Tokenize:** For each slug, remove stopwords (`guide, how, to, use, for, and, vs, the, of`), sort tokens alphabetically.
2. **Preload hub/sub-silo titles:** Hub and sub-silo target keywords are added to `seen_tokens_list` FIRST, preventing foundation spokes from duplicating silo titles.
3. **80% overlap threshold:** For each spoke's `(Target Keyword: ...)`, tokenize and compare against all `seen_tokens_list`. If overlap ≥ 80%, it's a duplicate and removed.
4. **First wins:** The first seen token set claims the slot; subsequent duplicates are dropped.

**Why this exists:** The LLM sometimes generates multiple spokes that are token-order rearrangements of the same keywords (e.g., `calendar-baby-gender` vs `baby-gender-calendar`). This phase catches those.

### Final Step: Persist
- Saves the final `clusters` JSON to `HubSpokeCluster.mapping_data` (upsert — one record per project).

---

## 8. AI AGENT PROMPTS (ALL PROMPTS — Complete Reference)

**File:** `backend/nlp/openrouter.py` (1500 lines)

### 8.1 AI Provider Configuration

**Priority chain** (checked in order, first one with an API key wins):
1. **TokenRouter** → `TOKENROUTER_API_KEY` / `TOKENROUTER_MODEL` (default: `moonshotai/kimi-k3-free`)
2. **DeepSeek** → `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL` (default: `deepseek-chat`)
3. **Groq** → `GROQ_API_KEY` / `GROQ_MODEL` (default: `llama-3.3-70b-versatile`)
4. **OpenRouter** → `OPENROUTER_API_KEY` / `OPENROUTER_MODEL` (default: `openai/gpt-4o-mini`)

**Two model slots:**
- `_provider_config(use_writing_model=False)` → Normal model for classification/filtering.
- `_provider_config(use_writing_model=True)` → Writing model for long-form generation (uses `TOKENROUTER_WRITING_MODEL`).

**Rate limit fallback:** If Groq returns a `RateLimitError`, automatically falls back to the writing model.

### 8.2 JSON Parsing (`_parse_json_payload`)
- Strips markdown code fences (`\`\`\`json ... \`\`\``)
- Falls back to regex extraction of `{...}` objects if JSON is malformed or truncated
- Unwraps `{"data": ...}` wrapper if present

### 8.3 Gold Nugget Agent (`generate_gold_hunter_seeds`)

**Function:** `async generate_gold_hunter_seeds(url, url_content) -> dict`
**Temperature:** 0.3 | **Max Tokens:** 2500

**Phases:**
1. **SITE AUDIT:** Extract Primary Keyword, Industry/Niche, Core Action, Target Audience, Capabilities (DOES), Hard Boundaries (DOES NOT)
2. **DOMAIN FENCING:** Ban umbrella terms. Block adjacent misaligned domains. Force-inject specific anchors for vague primary keywords.
3. **GAP DISCOVERY:** Identify Tool Gaps and Content Gaps. Generate 5-6 candidate seeds.
4. **TRIPLE GATE FILTER:**
   - Gate A (Volume): Must imply 1,000+ monthly searches
   - Gate B (Sitemap Depth): Top 10 results must be content-heavy sites with deep sitemaps
   - Gate C (Thematic Relevance): Must tie back to Core Action
5. **USE-CASE BROADENING:** If Primary Keyword fails Sitemap Gate, pivot to content-rich modifiers.
6. **FINAL OUTPUT:** 3 strongest seeds with justifications.

**Return:** `{"audit_summary": "...", "seeds": [{"keyword": "...", "justification": "..."}]}`

### 8.4 AI Keyword Generator (`generate_ai_keywords` / `generate_ai_keywords_sync`)

**Function:** `async generate_ai_keywords(seed_keywords) -> list[dict]` / `sync` version
**Temperature:** 0.35 | **Max Tokens:** 1600

Generates exactly **25 keywords**: 5 primary, 5 LSI, 5 long-tail, 5 entity, 5 heading.

**Quality Rules:**
- Every keyword must be highly semantically relevant to seed keywords
- Must include at least one meaningful seed keyword term exactly
- LSI keywords must include the seed term plus a semantic modifier
- No hallucinated terms, fake brands, or off-topic phrases
- Phrases: natural, lowercase, 2-6 words

**Post-processing:** Results pass through `filter_keyword_gap_recommendations()` as a second filter.

### 8.5 URL Keyword Extractor (`extract_keywords_from_urls_ai`)

**Function:** `extract_keywords_from_urls_ai(seed_keywords, urls) -> list[dict]` (sync)
**Temperature:** 0.1 | **Max Tokens:** 2500

Processes URLs in chunks of 100. For each chunk:
- Sends URL IDs + full URLs
- LLM infers target keywords from URL slugs
- Returns `{"phrase": "...", "type": "...", "url_ids": ["uuid-1", ...]}`

### 8.6 Keyword Sanity Filter (`filter_keyword_gap_recommendations`)

**Function:** `filter_keyword_gap_recommendations(seed_keywords, candidates, audit_summary?, max_keywords=60) -> list[dict]`
**Temperature:** 0.1 | **Max Tokens:** 2500

This is the **strict, multi-step LLM filter** that all keywords must pass through:

**Step 0: Natural Language Normalization**
- Reverse awkward structures: `"board games using spin wheel"` → `"spin the wheel board game"`
- Prioritize shorter, standard collocations (3-4 words)

**Step 1: Strict Seed Relevance Gate**
- Reject anything not directly supporting the seed keywords
- Aggressively reject generic umbrella terms, tangential topics

**Step 2: Anti-Cannibalization & Deduplication**
- Group variations with the same search intent
- Keep only ONE normalized keyword per intent

**Step 3: Volume Gate**
- Estimate monthly search volume
- Keep if 500+, reject if below

**Step 4: Final Output**
- Return deduplicated keywords with: `source_phrase`, `phrase`, `volume` (High/Medium/Low), `type`

**Audit Context:** If `audit_summary` is provided (from Gold Hunter), the filter uses it to extract Core Subject, Core Audience, and Core Action for even stricter filtering.

### 8.7 Intent Cluster Verifier (`verify_cluster_intent`)

**Function:** `verify_cluster_intent(cluster: list[dict]) -> dict` (sync)
**Temperature:** 0.1 | **Max Tokens:** 500

Used by the 4-Tier Classification system. Classifies a tight cluster as one of:
- `"same_intent"` → Tier 1 (merge) — same searcher intent, just different phrasings
- `"related_nuance"` → Tier 2 (subheading group) — related but distinct angles for one article
- `"different"` + `groups` → Split, re-classify each group separately

### 8.8 Competitor Domain Judge (`judge_competitor_domains`)

**Function:** `judge_competitor_domains(seed_keywords, own_domain, candidates, audit_summary?, max_domains=25) -> list[dict]`
**Temperature:** 0.1 | **Max Tokens:** 1200

Final gatekeeper for whether a discovered domain is a true business competitor:
- Reject dictionaries, marketplaces, social networks, forums, docs portals
- Strict topical niche match: reject broad software blogs for micro-tool sites
- Returns: `{"domain": "...", "verdict": "accept|reject", "confidence": 0-100, "reason": "..."}`

### 8.9 AI Top Picks (`generate_ai_top_picks`)

**Function:** `async generate_ai_top_picks(seed_keywords, existing_keywords) -> list[dict]`
**Temperature:** 0.35 | **Max Tokens:** 600

Selects the **absolute best 5-10 keywords** from the existing keyword list (not inventing new ones). Marks them as `keyword_type = "top-pick"`.

### 8.10 Hub & Spoke Clusterer (`cluster_hub_and_spoke`)

**Function:** `async cluster_hub_and_spoke(keywords) -> dict`
**Temperature:** 0.15 | **Max Tokens:** 8000

This is the **master LLM prompt** that generates the entire topical authority map. The prompt enforces the "Triple Gate Algorithm" constraints:

**Step 1: Master Hub**
- Identify the broadest core entity
- Use the FIRST keyword (highest volume) as the master hub target keyword
- EXACTLY 1 Master Hub — no exceptions
- Create `"🧱 FOUNDATION SPOKES (Authority)"` and `"💰 MASTER COMMERCIAL SPOKES"` layers

**Step 2: Sub-Silos**
- **TOPICAL NEIGHBORHOOD:** Keep only sub-topics within 2 semantic hops of the master hub. Discard anything 5+ hops away.
- **SUB-SILO CAP:** Maximum 5 sub-silos. Never 6 or more. Rank by topical density, keep top 5.
- **ARTICLE THRESHOLD:** Each sub-silo must have at least 8 supporting articles. Merge sub-silos with fewer into the closest neighbor.
- Each sub-silo enforces the **3-Layer Stack:**
  1. 🧱 Foundations: "What Is X?", "History of X", Databases
  2. ⚙️ Action: "How to X", "Step-by-Step", Tutorials, Tools
  3. 💰 Money: "Best X", "Buy X", "X Services"

**Step 3: Intent Tags & Cannibalization Rules (CRITICAL)**
- Tools get `[Tool]` tag; articles get `[Write]` tag
- **ANTI-CANNIBALIZATION:** Never use the exact same Target Keyword twice. If multiple variations share the same search intent (semantic similarity > 0.65), keep the highest search volume one as main Target Keyword and append redundant ones as `[Include H2: redundant_keyword]` format. Only ONE article per intent.

**Step 4: Handling Entities**
- Entity-type keywords are FORBIDDEN from being standalone articles
- Must be grouped under related articles as H2 suggestions: `"[Title] (Target Keyword: ...) [Include H2: entity1, entity2]"`

**Step 5: Zero Competition Quick-Wins**
- AI-generated keywords (`is_ai: true`) go to `"⚡️ ZERO COMPETITION QUICK-WINS"` layer

**Step 6: NOISE / DISCARD Bin**
- Completely unrelated keywords go to `"🗑️ NOISE / DISCARD"` hub

**HARD RULES SUMMARY:**
- EXACTLY 1 Master Hub only
- 3 to 5 Sub-Silos maximum
- 30 to 50 Articles total
- No empty sub-silos
- No off-topic keywords
- No cannibal duplicates (merge >0.65 semantic similarity as [Include H2: keyword])
- No sub-silos under 8 articles

**Output JSON Schema:**
```json
{
  "hubs": [
    {
      "hub_title": "📍 MASTER HUB: [Topic]",
      "target_keyword": "[keyword]",
      "layers": {
        "🧱 FOUNDATION SPOKES (Authority)": ["[Title] (Target Keyword: [kw])"],
        "⚙️ CORE STRATEGY": ["..."]
      },
      "sub_silos": [
        {
          "hub_title": "🪐 SUB-SILO 1: [Category] — [Overview]",
          "target_keyword": "[keyword]",
          "layers": {
            "🧱 Foundations": ["..."],
            "⚙️ Action": ["..."],
            "💰 Money": ["..."],
            "⚡️ ZERO COMPETITION QUICK-WINS": ["..."]
          }
        }
      ]
    },
    {
      "hub_title": "🗑️ NOISE / DISCARD",
      "target_keyword": "noise",
      "layers": {"Unrelated Keywords": ["..."]},
      "sub_silos": []
    }
  ]
}
```

### 8.11 Article Brief Builder (`build_article_brief`)

**Function:** `build_article_brief(...) -> dict`
**Temperature:** 0.2 | **Max Tokens:** 2600 | Uses writing model

Creates a comprehensive writer-ready brief containing:
- `search_intent`, `reader_persona`, `article_angle`
- `recommended_title`, `meta_description`
- `content_gaps`: 5-10 competitor weaknesses
- `competitor_takeaways`: 4-8 patterns
- `unique_value`: 4-8 differentiation strategies
- `must_include_terms`: 8-16 important terms/entities
- `proof_points`: 3-8 evidence types
- `outline`: 7-12 section objects with `heading`, `intent`, `points`
- `faq`: 4-8 Q&A objects
- `avoid`: 4-8 pitfalls

### 8.12 Master Prompt Writer (`write_prompt`)

**Function:** `write_prompt(...) -> str`
**Temperature:** 0.0 | **Max Tokens:** 4500

Generates a structured Master Prompt template with these sections:
1. `# CONTENT WRITING ASSIGNMENT` — Primary keyword
2. `# ARTICLE STRUCTURE` — Full heading outline (H1 + H2s with bullets)
3. `# SEMANTIC OPTIMIZATION` — Entities, key phrases, NLP keywords, skip-gram pairs
4. `# SEO GUIDELINES` — 30+ detailed writing rules (see Section 9)
5. `# INTRODUCTION WRITING INSTRUCTIONS` — Implicit definition, benefits, uses, components
6. `# COMPETITOR CONTENT ANALYSIS` — Full competitor content
7. Ends with `BEGIN WRITING THE ARTICLE NOW:`

### 8.13 Prompt Auditor (`audit_prompt`)

**Function:** `audit_prompt(prompt_markdown) -> dict`
**Temperature:** 0.0 | **Max Tokens:** 800

Verifies the Master Prompt has all required sections. Returns:
- `score`: 0-100
- `passed`: boolean
- `strengths`: array of strings
- `issues`: array of missing sections/formatting errors
- `revision_notes`: concrete instructions to fix

### 8.14 Article Writer (`write_final_article`)

**Function:** `write_final_article(master_prompt, revision_notes?) -> str`
**Temperature:** 0.28 | **Max Tokens:** 4500 | Uses writing model

System prompt: *"You are a world-class SEO strategist, subject-matter ghostwriter, and ruthless editor."*

### 8.15 Article Auditor (`audit_article`)

**Function:** `audit_article(primary_keyword, brief, article_markdown) -> dict`
**Temperature:** 0.1 | **Max Tokens:** 1800

Returns:
- `score`: 0-100
- `passed`: boolean (must be ≥92)
- `keyword_intent_score`: 0-100 (must be ≥90)
- `gap_coverage_score`: 0-100 (must be ≥90)
- `strengths`, `issues`, `revision_notes`, `missing_sections`

---

## 9. SEO WRITING RULES (Embedded in Master Prompt)

The Master Prompt template contains **30+ SEO writing rules** that are sent to the article-writing LLM. Key rules:

1. **Don't distance the answer from the question** — answer immediately, then elaborate
2. **Singularity and Plurality matter** for micro semantics
3. **Don't Use Analogies** — they confuse search engines
4. **Avoid coreference errors** — don't use ambiguous pronouns
5. **Don't create unnecessary sentences** — minimize token usage
6. **Use abbreviations in parentheses** on first mention (e.g., "Bitcoin (BTC)")
7. **Don't send the reader to the back of the article** — no "As stated before"
8. **Give Safe Answers** — cite evidence, avoid absolute claims
9. **Bold the answer, not the search term**
10. **Put "if" statements in the second part** of the sentence
11. **Optimize subordinate text** — "To do X..." not "X is..."
12. **Match adjective/predicate/noun order** between questions and answers
13. **Give examples after plural nouns**
14. **Use numeric values** — "There are 5 reasons..." not "There are many reasons..."
15. **Cut the fluff out** — delete all contextless words
16. **Be Certain** — state facts, not possibilities
17. **Use consistent Part of Speech tags** in list items
18. **Prioritize attributes and contexts** matching the question
19. **Include diverse measurement units**
20. **Boolean questions start with Yes or No**
21. **Omit needless words** — vigorous writing is concise
22. **Use active voice**
23. **Avoid AI-giveaway phrases** — "dive into", "unleash", "delve", "tapestry", etc.
24. **Avoid marketing language** — no hype or promotional words
25. **Kill specific banned words** — "meticulous", "realm", "crucial", "robust", "vibrant", etc.

---

## 10. 4-TIER KEYWORD CLASSIFICATION SYSTEM

**File:** `backend/nlp/keywords.py` → `classify_keyword_tiers()` (Lines 476-554)

This system runs BEFORE the Hub & Spoke generation. It classifies keywords into 4 tiers using a two-level clustering approach:

### Level 1: Loose Clustering (Jaccard threshold = 0.55)
Groups keywords into sub-silo candidates. Keywords in the same Level-1 cluster are topically related.

### Level 2: Tight Clustering (Jaccard threshold = 0.85)
Within each Level-1 cluster, finds potential true duplicates. Each tight cluster is then verified by the LLM via `verify_cluster_intent()`:

| Tier | Description | What Happens |
|------|-------------|--------------|
| **Tier 1: merge** | Exact same intent (e.g., word-order flips) | Keep one representative (highest volume), drop others |
| **Tier 2: subheading_group** | Related nuances | Create one article with the broadest phrase as title, others as H2/H3 |
| **Tier 3: related** | Loosely related, same sub-silo | Keep all as separate articles, interlink them |
| **Tier 4: outlier** | Stands alone in its Level-1 cluster | Standalone article |

### Similarity Function: `phrase_similarity()`
```python
def phrase_similarity(phrase1, phrase2):
    set1 = get_intent_word_set(phrase1)  # stemmed, stopword-free
    set2 = get_intent_word_set(phrase2)
    if set1.issubset(set2) or set2.issubset(set1): return 1.0
    return len(set1 & set2) / len(set1 | set2)  # Jaccard
```

### Intent Hashing: `generate_intent_hash()`
- Strips stopwords
- Stems words (handles plurals, gerunds)
- Sorts alphabetically
- Result: `"options trading strategies"` and `"trading option strategy"` → same hash

### Cannibalization Detection: `check_intent_cannibalization()`
Returns `True` if:
- One phrase's word set is a perfect subset of the other, OR
- Jaccard similarity ≥ 0.6

---

## 11. NLP & KEYWORD PROCESSING

**File:** `backend/nlp/keywords.py` (556 lines)

### Core Functions:

| Function | Purpose |
|----------|---------|
| `clean_phrase(phrase)` | Lowercase, strip, normalize whitespace, remove non-ASCII, replace underscores |
| `is_valid_keyword(phrase, min_len=3, min_words=1)` | Length, pattern, stopword, digit ratio, char length checks |
| `is_publishable_keyword(phrase, min_words=2, topic_terms=None)` | Final display-worthiness gate + optional topic relevance |
| `seed_keyword_terms(keywords)` | Extract unique non-stopword terms from seed keywords |
| `keyword_terms(phrase, min_len=2)` | Extract meaningful terms (handles plurals: `"words"` → `"word"`) |
| `extract_keywords_from_page(text, h1, h2s, h3s)` | Full extraction: RAKE + KeyBERT + SpaCy NER + heading n-grams |
| `extract_rake_keywords(text, max=20)` | RAKE algorithm (bigrams/trigrams) |
| `extract_statistical_keywords(text, max=20)` | Dependency-free n-gram frequency fallback |
| `extract_keybert_keywords(text, max=15)` | KeyBERT semantic similarity extraction |
| `extract_spacy_entities(text)` | Named entity recognition (ORG, PRODUCT, GPE, PERSON, etc.) |
| `extract_noun_chunks(text)` | SpaCy noun phrase extraction |
| `extract_heading_keywords(h1, h2s, h3s)` | Bigram/trigram extraction from headings |

### Stopword Lists:
- **STOPWORDS:** 100+ common English words (articles, pronouns, connectors, etc.)
- **GENERIC_UI_WORDS:** 30+ UI-related terms (button, click, menu, etc.)
- **IGNORED_TOPIC_TERMS:** Tool-related terms excluded from seed matching (calculator, maker, generator, etc.)
- **COMMON_SHORT_TOKENS:** Valid short keywords (AI, API, SaaS, SEO, etc.)

### Keyword Type Normalization:
```python
ALLOWED_KEYWORD_TYPES = {"primary", "lsi", "long-tail", "entity", "heading"}
# "longtail" → "long-tail", "entities" → "entity", etc.
```

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

## 13. KEYWORD QUALITY PIPELINE (End-to-End Flow)

The keyword filtering pipeline has **7 layers**:

1. **URL Slug Extraction:** Keywords are extracted from competitor URL path segments (e.g., `/best-circuit-diagram-maker` → `"best circuit diagram maker"`). Function: `_url_keyword_candidates()`.

2. **`is_publishable_keyword()`:** Local Python validation — must be 2+ words, not all stopwords, no gibberish patterns, ASCII only.

3. **Seed Relevance Gate:** Keywords must contain at least one term from `seed_keyword_terms()`. Controlled by `topic_terms` parameter.

4. **Own-Site Deduplication:** Keywords already present on the user's own website URLs are removed. Function: `_remove_covered_keywords()`.

5. **LLM Sanity Filter (`filter_keyword_gap_recommendations`):** The strict AI filter that:
   - Uses Gold Hunter audit summary to extract Core Subject, Core Audience, Core Action
   - Normalizes awkward phrasings
   - Rejects anything outside the core topic
   - Estimates search volume (reject < 500)
   - Clusters by intent to prevent cannibalization
   - Returns at most 60 filtered keywords

6. **4-Tier Classification (`classify_keyword_tiers`):** Mathematical clustering using Jaccard similarity + LLM verification to assign merge/subheading/related/outlier tiers.

7. **Hub & Spoke Clustering + Semantic Deduplication:** Final organizational layer with 80% token overlap deduplication.

---

## 14. ARTICLE GENERATION PIPELINE

**File:** `backend/app/content/service.py`

### Phase 1: Master Prompt Generation
1. Collect competitor research pages (scrape content from competitor URLs).
2. Search Google for additional competitor content if needed.
3. Use LLM Competitor Judge to validate competitor domains.
4. Build article brief via `build_article_brief()`.
5. Generate Master Prompt via `write_prompt()`.
6. Audit the Master Prompt via `audit_prompt()`.
7. Repeat up to **5 attempts** until audit passes (score ≥ 92).

### Phase 2: Final Article Generation
1. Feed the Master Prompt to `write_final_article()`.
2. Run **local quality checks** (`_local_article_quality_issues()`):
   - No code fences in article
   - No AI meta commentary ("as an AI...")
   - At least 900 words
   - Exactly one H1
   - At least five H2 sections
   - Primary keyword appears in text
   - FAQ section exists
3. Run LLM article audit via `audit_article()`.
4. If score < 92, generate revision notes and retry.
5. Repeat up to **20 attempts**.

---

## 15. FRONTEND PAGES & COMPONENTS

### 15.1 Dashboard Routes
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

### 15.2 Key Components

**DashboardLayout.tsx** (9419 bytes)
- Collapsible sidebar with navigation links
- Responsive drawer for mobile
- Top nav with theme toggle and user menu
- Icons: Home, Compass, Search, Bookmark, FileText, PenTool, Settings, Crosshair

**KeywordsTable.tsx** (20940 bytes)
- Paginated keyword table with:
  - Type filter dropdown (all, primary, lsi, long-tail, entity, heading, top-pick)
  - Search input
  - Sort options (frequency, phrase, created_at)
  - Multi-select checkboxes
  - Bulk save/delete actions
  - CSV export
  - Per-row article generation
  - Source URL tooltips

**HubSpokeView.tsx** (18330 bytes)
- Visual tree rendering of the Hub & Spoke JSON structure
- Expandable/collapsible sections
- Emoji-based layer icons (🧱, ⚙️, 💰, ⚡️, 🗑️)
- URL slug display for each spoke
- `[Write]` / `[Make Tool]` intent tags
- Spoke title cleaning (`cleanHubTitle()`)
- `generateSpokeSlug()` for URL generation
- Copy-to-clipboard for the full map
- Download as `.txt` file

**CompetitorGraph.tsx** (4660 bytes)
- Visual graph showing competitor domains and their scraped URL counts

**LiveSignals.tsx** (2737 bytes)
- Real-time scan progress indicators
- Polls scan status endpoint

**GeneratedArticlePanel.tsx** (14844 bytes)
- Full Master Prompt preview in markdown
- Audit score display with pass/fail indicator
- Copy-to-clipboard
- "Write Final Article" button
- Article generation status tracking

**SavedKeywordsTable.tsx** (8158 bytes)
- Saved keyword bank table
- Mark done/not done
- Bulk actions
- Notes display

**SemanticMetrics.tsx** (6851 bytes)
- Semantic analysis metrics visualization

### 15.3 API Client (`dashboard/src/lib/api.ts`)
- Uses `fetch()` with JWT Bearer token auth from `localStorage`
- Automatic redirect to `/login` on 401 responses
- Default timeout: 20 seconds
- Article generation timeout: 5 minutes (300 seconds)
- Demo backend mode: `VITE_ENABLE_DEMO_BACKEND=true` for Vercel preview without a backend

### 15.4 Theme System
- `ThemeProvider.tsx` + `ThemeToggle.tsx`
- Dark/light mode with system preference detection
- Theme stored in `localStorage` under `"sitemap-theme"` key
- Default: `"dark"`

---

## 16. CONFIGURATION (All Environment Variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./sitemapseo.db` | Async database URL |
| `SYNC_DATABASE_URL` | Auto-derived | Sync database URL for pipeline worker |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis for Celery |
| `USE_CELERY` | `false` | Use Celery workers vs BackgroundTasks |
| `SECRET_KEY` | `super-secret-jwt-key...` | JWT signing key |
| `ALGORITHM` | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `10080` (7 days) | JWT token lifetime |
| `FRONTEND_URL` | `http://localhost:3000` | CORS allowed origin |
| `TOKENROUTER_API_KEY` | `""` | Primary AI provider |
| `TOKENROUTER_MODEL` | `moonshotai/kimi-k3-free` | Default model |
| `TOKENROUTER_WRITING_MODEL` | `moonshotai/kimi-k3-free` | Writing model |
| `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL` | `""` / `deepseek-chat` | DeepSeek fallback |
| `GROQ_API_KEY` / `GROQ_MODEL` | `""` / `llama-3.3-70b-versatile` | Groq fallback |
| `OPENROUTER_API_KEY` / `OPENROUTER_MODEL` | `""` / `openai/gpt-4o-mini` | OpenRouter fallback |
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
| `SCRAPE_DELAY_MIN` | `1.0` | Min delay between scrape requests (seconds) |
| `SCRAPE_DELAY_MAX` | `3.0` | Max delay between scrape requests (seconds) |
| `REQUEST_TIMEOUT` | `5` | HTTP request timeout (seconds) |
| `MAX_RETRIES` | `3` | Max HTTP retries |
| `ENABLE_KEYBERT` | `false` | Enable KeyBERT extraction |
| `ENABLE_SPACY` | `true` | Enable SpaCy NER extraction |

### Database URL Auto-Normalization
The `Settings` class automatically converts:
- `postgres://` → `postgresql+asyncpg://` (for async)
- Derives `SYNC_DATABASE_URL` from async URL (replaces `+asyncpg` → plain `postgresql://`)
- Handles `sqlite+aiosqlite:///` → `sqlite:///` sync conversion

---

## 17. DEPLOYMENT ARCHITECTURE

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
# Services:
# - postgres:5432 (PostgreSQL 16 Alpine)
# - redis:6379 (Redis 7 Alpine)
# - backend:8000 (FastAPI + uvicorn --reload)
# - celery worker (4 concurrency, queues: default,scrape,nlp)
# - dashboard:3000 (Vite dev server)
```

### Docker Compose Services:
| Service | Container Name | Port | Image |
|---------|---------------|------|-------|
| `postgres` | `sitemapseo_db` | 5432 | `postgres:16-alpine` |
| `redis` | `sitemapseo_redis` | 6379 | `redis:7-alpine` |
| `backend` | `sitemapseo_api` | 8000 | Custom Dockerfile |
| `worker` | `sitemapseo_worker` | — | Same image as backend |
| `dashboard` | `sitemapseo_dashboard` | 3000 | `node:20-alpine` |

---

## 18. AUTHENTICATION SYSTEM

- **JWT-based** authentication with HS256 algorithm
- Tokens expire after **7 days** (`ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7`)
- Password hashing with **bcrypt**
- `get_current_user` FastAPI dependency extracts user from Bearer token
- Frontend stores token in `localStorage`
- CORS allows credentials from localhost:3000, localhost:3001, localhost:5173 + configured `FRONTEND_URL`

---

## 19. PYDANTIC SCHEMAS (Request/Response)

**File:** `backend/app/schemas.py` (276 lines)

### Input Schemas:
| Schema | Purpose |
|--------|---------|
| `UserRegister` | Registration (email, password min 8 chars, full_name) |
| `UserLogin` | Login (email, password) |
| `ProjectCreate` | New project (name, domain, own_domain, target_keywords, search_locale) |
| `SaveKeywordRequest` | Save single keyword (notes) |
| `KeywordBulkSaveRequest` | Bulk save (keyword_ids, notes) |
| `KeywordBulkDeleteRequest` | Bulk delete (keyword_ids) |
| `KeywordBankBulkActionRequest` | Bank actions (keyword_bank_ids, action: mark_done/mark_not_done/delete) |
| `WebsiteIntentRequest` | Intent analysis (keyword, manual_competitors, short_mode) |
| `WebsitePromptGenerateRequest` | Prompt generation (keyword, intent, competitors) |

### Output Schemas:
| Schema | Purpose |
|--------|---------|
| `UserOut` | User profile |
| `TokenResponse` | JWT token + user |
| `ProjectOut` | Full project with status and counters |
| `ProjectStats` | Project statistics |
| `ProjectSourceOut` | Source domain statistics |
| `ScanJobOut` | Scan job details |
| `ScanProgress` | Real-time scan progress |
| `KeywordOut` | Single keyword with sources + tier metadata |
| `KeywordListResponse` | Paginated keyword list |
| `KeywordSourceOut` | Source URL info |
| `ArticleDraftOut` | Article with audit score and research |
| `WebsiteIntentResponse` | Intent analysis result |
| `WebsitePromptGenerateResponse` | Generated prompt with audit score |
| `UrlOut` | URL with scrape metadata |

### Domain Validation:
- `ProjectCreate.domain` auto-prepends `https://` and validates via `urlparse`
- `ProjectCreate.own_domain` same treatment, nullable
- `UserRegister.password` must be ≥ 8 characters

---

## 20. DESIGN DECISIONS & BUG FIXES LOG

### Resolved Issues:

1. **Foundation Spoke = Silo Slug Bug:** The first foundation spoke under each sub-silo used to duplicate the silo's own slug (e.g., `/korean-age-vs-international-age/` appeared as both the silo URL and its first foundation spoke). **Fix:** Phase 5 preloads hub/sub-silo target keywords into `seen_tokens_list` before processing spokes, so the first spoke is automatically flagged as a duplicate.

2. **Multiple Master Hubs:** The LLM prompt was not strictly enforced to produce exactly 1 master hub. **Fix:** Added `HARD RULE: You MUST create exactly ONE (1) Master Hub` and `remove the multiple master if needed constraint`.

3. **Slug = Full Title Bug:** Slugs were sometimes the full article title instead of just the primary keyword. **Fix:** `generateSpokeSlug()` on the frontend extracts only the `(Target Keyword: ...)` from the spoke title and slugifies that.

4. **Tool vs Write Misclassification:** Text articles were being tagged as `[Make Tool]`. **Fix:** The prompt now specifies that only calculators, generators, and software get `[Tool]` tags.

5. **Keyword Cannibalization:** Multiple near-identical keywords were getting separate spokes. **Fix:** Multi-layer defense — LLM anti-cannibalization rules + Phase 5 semantic deduplication + `[Include H2: ...]` folding for redundant intent.

6. **Yellowpages Scraping:** `yellowpages.com` was passing the competitor filter. **Fix:** Added to `blocked_roots` in `pipeline.py`.

7. **Off-Topic Keywords Passing Filter:** The LLM keyword filter was not strict enough. **Fix:** Added Gold Hunter audit context (`Core Subject`, `Core Audience`, `Core Action`) to the filter prompt, creating a second layer of topical enforcement.

8. **Sub-Silo Explosion:** The LLM was creating 6+ sub-silos. **Fix:** Added hard cap of 3-5 sub-silos and minimum 8 articles per silo in the prompt.

9. **H2 Keyword Folding (Current):** Instead of completely discarding redundant intent keywords, the system now keeps the highest-volume one as the main Target Keyword and appends others as `[Include H2: redundant_keyword]` format.

---

## 21. TESTING INFRASTRUCTURE

### Test Scripts:
| Script | Purpose |
|--------|---------|
| `backend/test_diag.py` | End-to-end Hub & Spoke generation test using DeepSeek API |
| `backend/test_hub.py` | Hub & Spoke clustering integration test |
| `backend/test_kw4.py` - `test_kw6.py` | 4-Tier keyword classification unit tests |
| `backend/test_pydantic.py` | Schema validation tests |
| `test_api.py` | Root-level API endpoint tests |
| `test_db.py` | Database connection tests |
| `test_hub_spoke.py` | Hub-spoke endpoint tests |
| `test_key.py` | Keyword extraction tests |
| `test_prompt.py` | Prompt generation tests |
| `test_empty_project.py` | Empty project edge case test |
| `test_get_api.py` | GET endpoint tests |

---

## 22. COMPLETE FUNCTION INDEX

### `backend/nlp/openrouter.py` (1500 lines)
| Function | Line | Async | Purpose |
|----------|------|-------|---------|
| `normalize_keyword_type()` | 14 | No | Normalize keyword type strings |
| `_provider_config()` | 27 | No | Select AI provider by priority |
| `is_ai_configured()` | 60 | No | Check if any AI key exists |
| `ai_provider_name()` | 64 | No | Get current provider name |
| `ai_generated_source()` | 68 | No | Returns fixed AI source URL tuple |
| `_sync_client()` | 72 | No | Create sync OpenAI client |
| `_async_client()` | 80 | No | Create async OpenAI client |
| `_strip_code_fences()` | 88 | No | Remove markdown code fences |
| `_parse_json_payload()` | 97 | No | Parse JSON with fallback extraction |
| `_achat_json()` | 126 | Yes | Async JSON chat completion |
| `_chat_json()` | 152 | No | Sync JSON chat completion |
| `_chat_text()` | 178 | No | Sync text chat completion with rate limit fallback |
| `verify_cluster_intent()` | 215 | No | LLM intent verification for clustering |
| `generate_ai_keywords()` | 276 | Yes | Generate 25 AI keywords |
| `generate_ai_keywords_sync()` | 366 | No | Sync version of above |
| `extract_keywords_from_urls_ai()` | 456 | No | Extract keywords from URL slugs |
| `generate_ai_top_picks()` | 536 | Yes | Select top 5-10 keywords |
| `filter_keyword_gap_recommendations()` | 602 | No | Strict keyword sanity filter |
| `judge_competitor_domains()` | 715 | No | Validate competitor domains |
| `build_article_brief()` | 793 | No | Create article brief |
| `write_prompt()` | 850 | No | Generate Master Prompt |
| `audit_prompt()` | 1172 | No | Audit Master Prompt |
| `write_final_article()` | 1211 | No | Write article from prompt |
| `audit_article()` | 1240 | No | Audit article quality |
| `generate_gold_hunter_seeds()` | 1287 | Yes | Gold Hunter scan |
| `cluster_hub_and_spoke()` | 1365 | Yes | Hub & Spoke clustering |

### `backend/nlp/keywords.py` (556 lines)
| Function | Line | Purpose |
|----------|------|---------|
| `clean_phrase()` | 65 | Normalize keyword phrase |
| `is_valid_keyword()` | 75 | Validate keyword format |
| `keyword_terms()` | 105 | Extract meaningful terms |
| `seed_keyword_terms()` | 119 | Extract terms from seed keywords |
| `is_publishable_keyword()` | 129 | Final display-worthiness check |
| `extract_rake_keywords()` | 143 | RAKE extraction |
| `extract_statistical_keywords()` | 176 | Frequency-based n-gram extraction |
| `extract_keybert_keywords()` | 195 | KeyBERT semantic extraction |
| `extract_spacy_entities()` | 221 | SpaCy NER extraction |
| `extract_noun_chunks()` | 240 | SpaCy noun phrase extraction |
| `_intent_stem()` | 270 | Lightweight word stemmer |
| `generate_intent_hash()` | 280 | Intent fingerprint for deduplication |
| `get_intent_word_set()` | 295 | Stemmed word set for comparison |
| `check_intent_cannibalization()` | 301 | Binary cannibalization check |
| `extract_heading_keywords()` | 327 | Heading n-gram extraction |
| `extract_keywords_from_page()` | 372 | Full extraction pipeline |
| `phrase_similarity()` | 417 | Jaccard similarity on stemmed tokens |
| `cluster_level()` | 430 | Average-linkage clustering |
| `pick_cluster_representative()` | 459 | Highest volume cluster representative |
| `pick_broadest_phrase()` | 468 | Shortest phrase in cluster |
| `classify_keyword_tiers()` | 476 | Full 4-tier classification pipeline |

---

*End of Full Context Document (v2)*
