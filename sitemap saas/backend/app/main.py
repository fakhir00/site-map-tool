from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.config import settings
from app.database import engine, Base
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Auto-create tables on startup if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_runtime_schema(conn)
    logger.info("Database tables ready")
    yield
    await engine.dispose()


async def _ensure_runtime_schema(conn):
    """Small compatibility migrations for existing local/Docker databases."""
    dialect = conn.dialect.name
    if dialect == "sqlite":
        result = await conn.execute(text("PRAGMA table_info(projects)"))
        project_columns = {row[1] for row in result.fetchall()}
        if "target_keywords" not in project_columns:
            await conn.execute(text("ALTER TABLE projects ADD COLUMN target_keywords JSON"))
        result = await conn.execute(text("PRAGMA table_info(urls)"))
        url_columns = {row[1] for row in result.fetchall()}
        if "source_type" not in url_columns:
            await conn.execute(text("ALTER TABLE urls ADD COLUMN source_type VARCHAR(50) DEFAULT 'competitor'"))
        if "source_domain" not in url_columns:
            await conn.execute(text("ALTER TABLE urls ADD COLUMN source_domain VARCHAR(512)"))
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


app = FastAPI(
    title="SiteMapSEO API",
    description="Competitor sitemap analysis and SEO keyword intelligence",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_URL,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
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

app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(scan_router)
app.include_router(keywords_router)
app.include_router(keyword_bank_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "SiteMapSEO API"}
