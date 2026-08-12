# Ship Readiness Report — SiteMapSEO

## Verdict

🟡 **SHIP WITH KNOWN ISSUES**

## Score

| Category | Score |
|---|---|
| Security | 4/10 |
| Functionality | 7/10 |
| Reliability | 6/10 |
| UX | 7/10 |
| Performance | 6/10 |
| Accessibility | 5/10 |
| Production Configuration | 4/10 |
| Code Quality | 7/10 |
| **Overall** | **57/100** |

---

## Architecture Overview

| Component | Technology |
|---|---|
| Frontend | React 19 + Vite + TailwindCSS v4 + TanStack React Query |
| Backend | Python FastAPI (async) |
| Database | SQLite (local dev) / PostgreSQL (production via docker-compose) |
| Auth | JWT (HS256) via `python-jose` + `bcrypt` |
| Background Jobs | FastAPI `BackgroundTasks` (local) / Celery + Redis (docker) |
| Third-party APIs | OpenRouter (LLM), Apify (scraping), Groq (LLM alternative) |
| Deployment | Vercel (dashboard + marketing), Render (backend) |
| Payments | None (skipped per user request) |

---

## P0 — Ship Blockers

### P0-001: Hardcoded Default JWT Secret Key
```
ID: P0-001
Severity: P0
Category: Security
Location: backend/app/config.py:11
```

**Problem:** The JWT `SECRET_KEY` has a hardcoded default value `"super-secret-jwt-key-change-in-production-32chars"`. If the `SECRET_KEY` environment variable is not set in production, every user token can be forged by anyone who reads the source code (which is public on GitHub).

**Reproduction:** Deploy without setting `SECRET_KEY` env var. The default is used. Any attacker can mint valid JWT tokens for any user.

**Expected:** Application should refuse to start if `SECRET_KEY` is not explicitly provided, or at minimum it should never use a predictable default.

**Actual:** App silently uses the hardcoded default.

**Impact:** Complete authentication bypass. Any user's account can be impersonated.

**Evidence:** [config.py:11](file:///Users/fakhirbaig/Documents/GitHub/sit%20map%20tool/backend/app/config.py#L11)

**Recommended Fix:** Remove the default value. Raise an error on startup if `SECRET_KEY` is not set. Or generate a random key on first boot and persist it.

---

### P0-002: Hardcoded JWT Secret in docker-compose.yml
```
ID: P0-002
Severity: P0
Category: Security
Location: docker-compose.yml:46, 74
```

**Problem:** The docker-compose file hardcodes the same default `SECRET_KEY: super-secret-jwt-key-change-in-production-32chars` in plain text for both the backend and worker services. This is committed to the public repository.

**Expected:** Secrets should be injected via environment variables or Docker secrets, never hardcoded in version-controlled files.

**Impact:** Same as P0-001 — complete authentication bypass for any Docker deployment that uses the compose file unmodified.

**Evidence:** [docker-compose.yml:46](file:///Users/fakhirbaig/Documents/GitHub/sit%20map%20tool/docker-compose.yml#L46)

**Recommended Fix:** Replace with `SECRET_KEY: ${SECRET_KEY:?SECRET_KEY must be set}` to force explicit configuration.

---

### P0-003: Database Password Hardcoded in docker-compose.yml
```
ID: P0-003
Severity: P0
Category: Security
Location: docker-compose.yml:10, 42-43, 70-71
```

**Problem:** PostgreSQL credentials `sitemapseo` / `sitemapseo_secret` are hardcoded in the compose file committed to a public repo.

**Impact:** Any attacker who gains network access to the PostgreSQL port can authenticate with these credentials.

**Recommended Fix:** Use environment variable substitution: `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Must be set}`.

---

## P1 — Critical Issues

### P1-001: No Rate Limiting on Any API Endpoint
```
ID: P1-001
Severity: P1
Category: Security / Reliability
Location: All API routers
```

**Problem:** There is zero rate limiting on any endpoint — including `/api/auth/register`, `/api/auth/login`, keyword generation, article generation, and scan start. An attacker can:
- Brute-force passwords via `/api/auth/login`
- Create unlimited accounts via `/api/auth/register`
- Exhaust OpenRouter/Apify API quotas by spamming generation endpoints
- Launch unlimited concurrent scans

**Impact:** API abuse, credential stuffing, cost explosion from third-party API calls, and denial of service.

**Recommended Fix:** Add `slowapi` or similar rate-limiting middleware. Critical limits: login (5/min), register (3/min), AI generation (10/min per user), scan start (2/min per user).

---

### P1-002: No Password Reset or Email Verification Flow
```
ID: P1-002
Severity: P1
Category: Functionality / Security
Location: backend/app/auth/
```

**Problem:** There is no password reset endpoint and no email verification. If a user forgets their password, they have no recovery path. Accounts can be registered with any email without verification.

**Impact:** Users are locked out permanently if they forget their password. Fake/disposable emails can register unlimited accounts.

**Recommended Fix:** Implement a `/api/auth/forgot-password` and `/api/auth/reset-password` flow. Add email verification on registration.

---

### P1-003: No CSRF Protection
```
ID: P1-003
Severity: P1
Category: Security
Location: backend/app/main.py
```

**Problem:** The API uses Bearer tokens stored in `localStorage`, which is good for CSRF resistance. However, `allow_credentials=True` is set in CORS with a broad allow list. If the frontend ever switches to cookie-based auth, CSRF becomes exploitable immediately.

**Impact:** Low immediate risk (Bearer tokens), but the CORS configuration is overly permissive for a production SaaS.

**Recommended Fix:** Tighten CORS `allow_origins` to only the exact production dashboard URL. Remove localhost origins in production.

---

### P1-004: CORS Allows Localhost in Production
```
ID: P1-004
Severity: P1
Category: Security
Location: backend/app/main.py:101-107
```

**Problem:** The CORS middleware *always* allows `http://localhost:3000`, `http://127.0.0.1:3000`, `http://localhost:5173`, and `http://127.0.0.1:5173` regardless of environment. In production, these should not be present.

**Impact:** An attacker running a malicious page on localhost can make authenticated cross-origin requests to the production API.

**Recommended Fix:** Only include localhost origins when `DEBUG` or a development flag is true.

---

### P1-005: `save_keyword` Endpoint Missing `await db.commit()`
```
ID: P1-005
Severity: P1
Category: Data Integrity
Location: backend/app/keywords/router.py:322-324
```

**Problem:** The `save_keyword` endpoint adds a `KeywordBank` entry but never explicitly commits. It relies on the `get_db()` dependency's auto-commit in the `finally` block, which does call `await session.commit()`. However, the endpoint returns `{"message": "Keyword saved to bank"}` *before* the commit actually happens. If the commit fails (e.g., unique constraint violation), the user sees success but data isn't persisted.

**Impact:** Inconsistent success messaging. The user may believe a keyword was saved when it wasn't.

**Recommended Fix:** Add `await db.commit()` before returning the success response, or wrap in a try/except to catch IntegrityError.

---

### P1-006: `register` Endpoint Missing `await db.commit()`
```
ID: P1-006
Severity: P1
Category: Data Integrity
Location: backend/app/auth/router.py:24-29
```

**Problem:** Same issue as P1-005. The register endpoint calls `db.add(user)` and `await db.flush()` but never explicitly commits. It relies on the dependency's auto-commit. If something fails between `flush` and the dependency cleanup, the user gets a token for a user that was never persisted.

**Impact:** A user could receive a valid JWT token for a user record that doesn't exist in the database.

**Recommended Fix:** Add `await db.commit()` after `await db.refresh(user)`.

---

## P2 — Major Issues

### P2-001: No Input Length Validation on Most Text Fields
```
ID: P2-001
Severity: P2
Category: Security / Reliability
Location: backend/app/schemas.py
```

**Problem:** `ProjectCreate.name`, `ProjectCreate.domain`, keyword phrases, article content, and website prompt inputs have no max length validation. A user could submit a 10MB project name or a 1MB keyword phrase.

**Impact:** Database bloat, potential memory exhaustion, and possible denial of service.

**Recommended Fix:** Add `max_length` constraints to all string fields in Pydantic schemas.

---

### P2-002: No Pagination on Keyword Bank Endpoint
```
ID: P2-002
Severity: P2
Category: Performance
Location: backend/app/keywords/router.py:327-349
```

**Problem:** The `/api/keyword-bank` endpoint returns ALL saved keywords with no pagination. As the user's bank grows, this response will become increasingly large.

**Impact:** Slow load times and potential timeouts for power users.

**Recommended Fix:** Add `page` and `page_size` query params similar to the keywords endpoint.

---

### P2-003: Background Scan Has No Timeout or Cancellation Mechanism
```
ID: P2-003
Severity: P2
Category: Reliability
Location: backend/workers/pipeline.py
```

**Problem:** When a scan is dispatched as a `BackgroundTask`, there is no timeout. A scan that encounters slow/hanging competitors will run indefinitely, consuming server resources. There is a "pause" mechanism but no way to fully cancel/kill a stuck background task.

**Impact:** Resource exhaustion on the server. A single stuck scan could degrade performance for all users.

**Recommended Fix:** Add a maximum scan duration (e.g., 30 minutes). Check for cancellation/pause status between URL scrapes.

---

### P2-004: SQL Injection Risk via Search Parameter
```
ID: P2-004
Severity: P2
Category: Security
Location: backend/app/keywords/router.py:39
```

**Problem:** The keyword search uses `Keyword.phrase.ilike(f"%{search}%")`. While SQLAlchemy parameterizes this correctly by default, using raw string interpolation with `ilike` in some edge cases can be problematic. The `%` and `_` characters in user input act as SQL wildcards.

**Impact:** A user searching for `%` gets all results. Searching for `_` matches any single character. Not a true SQL injection, but unexpected behavior.

**Recommended Fix:** Escape `%` and `_` characters in the search input before passing to `ilike`.

---

### P2-005: Double-Submit/Double-Click Not Fully Prevented
```
ID: P2-005
Severity: P2
Category: Reliability / UX
Location: Dashboard UI — scan start, keyword generation, article generation
```

**Problem:** While `useMutation` from TanStack Query provides `isPending` state that disables buttons, there's no server-side idempotency. Rapidly double-clicking "Start Scan" before the first request completes could create duplicate scan jobs (the 409 check relies on `project.status == "running"` which may not be committed yet).

**Impact:** Duplicate scans, duplicate AI generations consuming API credits.

**Recommended Fix:** Add server-side idempotency keys or database-level locking (SELECT FOR UPDATE) on the project status check.

---

### P2-006: Settings Page is Read-Only
```
ID: P2-006
Severity: P2
Category: Functionality
Location: dashboard/src/pages/Settings.tsx
```

**Problem:** The Settings page displays user profile information but provides no way to edit it. There's no way to change name, email, or password. The "Plan" section shows the current plan but has no upgrade/downgrade mechanism.

**Impact:** Users cannot update their profile information after registration.

**Recommended Fix:** Add edit forms for name and password change at minimum.

---

### P2-007: Article List Limited to 10 Items With No Pagination
```
ID: P2-007
Severity: P2
Category: Performance / UX
Location: backend/app/content/router.py:147
```

**Problem:** The articles endpoint has a hardcoded `.limit(10)` with no pagination.

**Impact:** Users who generate more than 10 articles per project can never see their older ones.

**Recommended Fix:** Add pagination like the keywords endpoint.

---

## P3 — Minor Issues

### P3-001: `datetime.utcnow` is Deprecated
```
ID: P3-001
Severity: P3
Category: Code Quality
Location: backend/app/models.py (lines 23, 24, 47, 68, 107, 108, 135, 156, 157), backend/app/auth/jwt.py (lines 42-43)
```

**Problem:** `datetime.utcnow()` is deprecated in Python 3.12+. Should use `datetime.now(timezone.utc)`.

---

### P3-002: Leftover Debug/Test Files in Backend Root
```
ID: P3-002
Severity: P3
Category: Code Quality
Location: backend/
```

**Problem:** Multiple test/debug files exist in the backend root: `debug_pipeline.py`, `test_ddg.py`, `test_full_flow.py`, `test_pipeline.py`, `test_pipeline_helpers.py`, `test_run.py`, `apify_test_output.txt`. Also a stray CSV file in the repo root: `keywords-97972d86-...csv`.

**Impact:** Clutters the codebase. Could expose internal implementation details.

**Recommended Fix:** Move tests to a `tests/` directory. Remove debug files and stray CSVs.

---

### P3-003: `console.error` Calls in Production Frontend
```
ID: P3-003
Severity: P3
Category: Code Quality
Location: dashboard/src/components/GeneratedArticlePanel.tsx:45, dashboard/src/pages/WebsitePromptGenerator.tsx:73, GapPageGenerator.tsx:73
```

**Problem:** `console.error('Failed to copy text: ', err)` in clipboard copy fallback. Minor, but production code shouldn't log to console.

---

### P3-004: No Logout Confirmation
```
ID: P3-004
Severity: P3
Category: UX
Location: Dashboard sidebar
```

**Problem:** Clicking "Log out" immediately clears the token and redirects. No confirmation dialog.

---

### P3-005: No Loading Skeleton for Initial Page Loads
```
ID: P3-005
Severity: P3
Category: UX
Location: Multiple pages
```

**Problem:** Pages use simple `animate-pulse` rectangles as loading states. Content-aware skeletons would provide better perceived performance.

---

## Fixed During Audit

_No code changes were made during this audit (reconnaissance-only phase as instructed by the skill)._

---

## Remaining Issues

All findings above remain open.

---

## Tested User Journeys (Code Review)

- [x] Signup (code reviewed — works, missing email verification)
- [x] Login (code reviewed — works)
- [x] Logout (code reviewed — works, no confirmation)
- [ ] Onboarding (no onboarding flow exists)
- [x] Core feature: Create project + Start scan (code reviewed)
- [x] CRUD: Create/Read/Delete projects (code reviewed — update missing)
- [x] Keyword gaps: List, filter, search, generate, export (code reviewed)
- [x] Keyword bank: Save to bank (code reviewed)
- [x] Article generation (code reviewed)
- [x] Website Prompt Generator (code reviewed)
- [x] Gap Page Generator (code reviewed)
- [x] Settings (code reviewed — read-only)
- [ ] Billing (excluded per user request)
- [ ] Error states under network failure (not runtime tested)
- [ ] Mobile (not runtime tested)
- [x] Production build (verified — passes)

## Production Checklist

- [x] Production build succeeds
- [ ] Environment variables documented (no `.env.example` for backend)
- [ ] Secrets protected (P0-001, P0-002, P0-003 — **FAILING**)
- [x] Authentication verified (JWT flow works correctly)
- [x] Authorization verified (all endpoints check `user_id` ownership)
- [x] Database migrations verified (runtime schema migration in `main.py`)
- [ ] Payment flow verified (excluded)
- [ ] Webhooks verified (N/A)
- [x] Background jobs verified (pipeline worker reviewed)
- [ ] Error handling verified (mixed — some endpoints have good error handling, others don't)
- [ ] Logging verified (basic `logging` module, no structured logging)
- [ ] Monitoring verified (no monitoring/APM configured)
- [ ] Rate limiting verified (**FAILING** — none exists)
- [ ] Responsive UI verified (not runtime tested)
- [ ] Accessibility reviewed (not runtime tested)

## Final Recommendation

> **Do NOT ship to paying customers until P0 items are resolved.**

The three P0 issues (hardcoded JWT secret, hardcoded DB credentials in docker-compose, and those same secrets being the default fallback) are **authentication bypass vulnerabilities** that would allow any attacker to impersonate any user.

**Before launch, you MUST:**

1. **Remove the default `SECRET_KEY`** from `config.py` and force it to be set via environment variable
2. **Remove hardcoded credentials** from `docker-compose.yml` and use env var substitution
3. **Add rate limiting** on at least login, register, and AI generation endpoints
4. **Create a backend `.env.example`** documenting all required environment variables
5. **Verify your production Render deployment** has a strong, unique `SECRET_KEY` set

**After those fixes**, the application is functional and the core workflows are solid. The P1 and P2 issues are important to address iteratively but are not launch-blocking for an early-access/beta launch.
