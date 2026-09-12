from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager
from contextlib import suppress
import asyncio
import os
from app.config import settings
from app.database import engine, Base
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

frontend_origins = [
    origin.strip()
    for origin in settings.FRONTEND_URL.split(",")
    if origin.strip()
]


async def _initialize_database() -> None:
    # Auto-create tables on startup if they don't exist
    async with engine.begin() as conn:
        if conn.dialect.name != "sqlite":
            # A previous scan can briefly retain row/schema locks while Render
            # replaces an instance. Never let those locks block app startup.
            await conn.execute(text("SET LOCAL lock_timeout = '5s'"))
            await conn.execute(text("SET LOCAL statement_timeout = '25s'"))
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_runtime_schema(conn)
        if not settings.USE_CELERY:
            await conn.execute(
                text("UPDATE projects SET status = 'paused' WHERE status = 'running'")
            )
            await conn.execute(
                text("UPDATE scan_jobs SET status = 'paused', error_message = 'Interrupted by server restart. Click Resume to continue.' WHERE status IN ('queued', 'running')")
            )


async def _retry_database_initialization(app: FastAPI) -> None:
    while not app.state.database_ready:
        await asyncio.sleep(10)
        try:
            await asyncio.wait_for(_initialize_database(), timeout=30)
            app.state.database_ready = True
            logger.info("Database connection recovered and runtime state initialized")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Database initialization retry failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.database_ready = False
    retry_task: asyncio.Task | None = None
    try:
        await asyncio.wait_for(_initialize_database(), timeout=30)
        app.state.database_ready = True
    except Exception as exc:
        # Keep the API process alive so Render health checks and diagnostics
        # remain reachable while hosted Postgres recovers.
        logger.error("Database unavailable during startup; API will retry in background: %s", exc)
        retry_task = asyncio.create_task(_retry_database_initialization(app))
    if app.state.database_ready:
        logger.info("Database tables ready and interrupted scans marked for resume")
    yield
    if retry_task:
        retry_task.cancel()
        with suppress(asyncio.CancelledError):
            await retry_task
    await engine.dispose()


async def _ensure_runtime_schema(conn):
    """Small compatibility migrations for existing local/Docker databases."""
    dialect = conn.dialect.name
    if dialect == "sqlite":
        result = await conn.execute(text("PRAGMA table_info(projects)"))
        project_columns = {row[1] for row in result.fetchall()}
        if "target_keywords" not in project_columns:
            await conn.execute(text("ALTER TABLE projects ADD COLUMN target_keywords JSON"))
        if "audit_summary" not in project_columns:
            await conn.execute(text("ALTER TABLE projects ADD COLUMN audit_summary TEXT"))
        if "search_locale" not in project_columns:
            await conn.execute(text("ALTER TABLE projects ADD COLUMN search_locale VARCHAR(10) DEFAULT 'us'"))
        result = await conn.execute(text("PRAGMA table_info(urls)"))
        url_columns = {row[1] for row in result.fetchall()}
        if "source_type" not in url_columns:
            await conn.execute(text("ALTER TABLE urls ADD COLUMN source_type VARCHAR(50) DEFAULT 'competitor'"))
        if "source_domain" not in url_columns:
            await conn.execute(text("ALTER TABLE urls ADD COLUMN source_domain VARCHAR(512)"))
        if "scraped_text" not in url_columns:
            await conn.execute(text("ALTER TABLE urls ADD COLUMN scraped_text TEXT"))

        # 4-Tier Classification columns on keywords
        result = await conn.execute(text("PRAGMA table_info(keywords)"))
        kw_columns = {row[1] for row in result.fetchall()}
        for col, col_type in [
            ("tier", "VARCHAR(50)"),
            ("sub_silo_id", "INTEGER"),
            ("cluster_group_id", "VARCHAR(100)"),
            ("article_title", "TEXT"),
            ("h_tags", "JSON"),
            ("merged_from", "JSON"),
            ("seo_recommendation", "TEXT"),
        ]:
            if col not in kw_columns:
                await conn.execute(text(f"ALTER TABLE keywords ADD COLUMN {col} {col_type}"))
        result = await conn.execute(text("PRAGMA table_info(keyword_bank)"))
        bank_columns = {row[1] for row in result.fetchall()}
        if "is_done" not in bank_columns:
            await conn.execute(text("ALTER TABLE keyword_bank ADD COLUMN is_done BOOLEAN NOT NULL DEFAULT 0"))
        if "done_at" not in bank_columns:
            await conn.execute(text("ALTER TABLE keyword_bank ADD COLUMN done_at DATETIME"))
        return

    result = await conn.execute(
        text(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'projects'
            """
        )
    )
    columns = {row[0]: row[1] for row in result.fetchall()}
    if "target_keywords" not in columns:
        await conn.execute(text("ALTER TABLE projects ADD COLUMN target_keywords JSONB"))
    if "audit_summary" not in columns:
        await conn.execute(text("ALTER TABLE projects ADD COLUMN audit_summary TEXT"))
    if "search_locale" not in columns:
        await conn.execute(text("ALTER TABLE projects ADD COLUMN search_locale VARCHAR(10) DEFAULT 'us'"))
    if columns.get("url_filter_patterns") == "ARRAY":
        await conn.execute(
            text(
                """
                ALTER TABLE projects
                ALTER COLUMN url_filter_patterns DROP DEFAULT,
                ALTER COLUMN url_filter_patterns TYPE JSONB USING to_jsonb(url_filter_patterns),
                ALTER COLUMN url_filter_patterns SET DEFAULT '["/blog/", "/news/", "/post/", "/article/"]'::jsonb
                """
            )
        )

    result = await conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'urls'
            """
        )
    )
    url_columns = {row[0] for row in result.fetchall()}
    if "source_type" not in url_columns:
        await conn.execute(text("ALTER TABLE urls ADD COLUMN source_type VARCHAR(50) DEFAULT 'competitor'"))
    if "source_domain" not in url_columns:
        await conn.execute(text("ALTER TABLE urls ADD COLUMN source_domain VARCHAR(512)"))
    if "scraped_text" not in url_columns:
        await conn.execute(text("ALTER TABLE urls ADD COLUMN scraped_text TEXT"))

    # 4-Tier Classification columns on keywords
    result = await conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'keywords'
            """
        )
    )
    kw_columns = {row[0] for row in result.fetchall()}
    for col, col_type in [
        ("tier", "VARCHAR(50)"),
        ("sub_silo_id", "INTEGER"),
        ("cluster_group_id", "VARCHAR(100)"),
        ("article_title", "TEXT"),
        ("h_tags", "JSONB"),
        ("merged_from", "JSONB"),
        ("seo_recommendation", "TEXT"),
    ]:
        if col not in kw_columns:
            await conn.execute(text(f"ALTER TABLE keywords ADD COLUMN {col} {col_type}"))

    result = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'keyword_bank'"))
    bank_columns = {row[0] for row in result.fetchall()}
    if "is_done" not in bank_columns:
        await conn.execute(text("ALTER TABLE keyword_bank ADD COLUMN is_done BOOLEAN NOT NULL DEFAULT FALSE"))
    if "done_at" not in bank_columns:
        await conn.execute(text("ALTER TABLE keyword_bank ADD COLUMN done_at TIMESTAMP WITH TIME ZONE"))


app = FastAPI(
    title="SiteMapSEO API",
    description="Competitor sitemap analysis and SEO keyword intelligence",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

# Keyword lists, scan history, and architecture payloads compress well. Use a
# modest compression level to cut transfer time without costly CPU work.
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        *frontend_origins,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
from app.auth.router import router as auth_router
from app.projects.router import router as projects_router
from app.scan.router import router as scan_router
from app.keywords.router import bank_router as keyword_bank_router
from app.keywords.router import router as keywords_router
from app.content.router import router as content_router
from app.website_prompts.router import router as website_prompts_router
from app.goldhunter.router import router as goldhunter_router
from app.hub_spoke.router import router as hub_spoke_workspace_router
from app.providers.router import router as providers_router

app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(scan_router)
app.include_router(keywords_router)
app.include_router(keyword_bank_router)
app.include_router(content_router)
app.include_router(website_prompts_router)
app.include_router(goldhunter_router, prefix="/api")
app.include_router(hub_spoke_workspace_router)
app.include_router(providers_router)


@app.get("/api/health")
async def health():
    database_ready = bool(getattr(app.state, "database_ready", False))
    return {
        "status": "ok" if database_ready else "degraded",
        "service": "SiteMapSEO API",
        "database": "connected" if database_ready else "reconnecting",
        "revision": os.getenv("RENDER_GIT_COMMIT", "local")[:7],
    }
