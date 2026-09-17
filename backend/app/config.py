from pydantic import model_validator
from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    DATABASE_URL: str = f"sqlite+aiosqlite:///{BACKEND_DIR / 'sitemapseo.db'}"
    SYNC_DATABASE_URL: str = ""
    REDIS_URL: str = "redis://localhost:6379/0"
    USE_CELERY: bool = False
    SECRET_KEY: str = "super-secret-jwt-key-change-in-production-32chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    FRONTEND_URL: str = "http://localhost:3000"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "openai/gpt-4o-mini"
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_MODEL: str = "deepseek-chat"
    APIFY_API_TOKEN: str = ""
    APIFY_API_KEY: str = ""
    APIFY_TOKEN: str = ""
    APIFY_KEYWORD_ACTOR_ID: str = "qt4rCkNegFVRVWugm"
    APIFY_COMPETITOR_ACTOR_ID: str = "563JCPLOqM1kMmbbP"
    APIFY_KEYWORD_RESULT_LIMIT: int = 100
    APIFY_KEYWORD_MIN_VOLUME: int = 10
    APIFY_KEYWORD_LANGUAGE: str = "en"
    DATAFORSEO_LOGIN: str = ""
    DATAFORSEO_PASSWORD: str = ""
    DATAFORSEO_API_LOGIN: str = ""
    DATAFORSEO_API_PASSWORD: str = ""
    DATAFORSEO_DEFAULT_LOCATION: str = "United States"
    DATAFORSEO_DEFAULT_LANGUAGE: str = "English"
    DATAFORSEO_LOCATION_CODE: int = 0
    DATAFORSEO_LANGUAGE_CODE: str = ""
    DATAFORSEO_RESULT_LIMIT: int = 150
    DATAFORSEO_MAX_COST_PER_SCAN: float = 0.10
    DATAFORSEO_CACHE_DAYS: int = 30
    TOKENROUTER_API_KEY: str = ""
    TOKENROUTER_MODEL: str = "moonshotai/kimi-k3-free"
    TOKENROUTER_WRITING_MODEL: str = "moonshotai/kimi-k3-free"

    # Scraping
    MAX_URLS_PER_SCAN: int = 200
    MAX_COMPETITOR_DOMAINS: int = 30
    GOOGLE_SERP_RESULT_LIMIT: int = 30
    MAX_CONTENT_URLS_PER_DOMAIN: int = 12
    MAX_COMPETITOR_JUDGE_CANDIDATES: int = 90
    AI_KEYWORD_GAP_CANDIDATE_LIMIT: int = 250
    AI_KEYWORD_GAP_RESULT_LIMIT: int = 150
    MIN_KEYWORDS_PER_SCAN: int = 100
    AI_KEYWORD_GENERATION_BATCH_SIZE: int = 60
    AI_KEYWORD_GENERATION_MAX_BATCHES: int = 5
    ARTICLE_RESEARCH_SOURCE_LIMIT: int = 5
    ARTICLE_GENERATION_MAX_ATTEMPTS: int = 5
    SCRAPE_DELAY_MIN: float = 0.05
    SCRAPE_DELAY_MAX: float = 0.2
    REQUEST_TIMEOUT: int = 5
    MAX_RETRIES: int = 1
    ENABLE_KEYBERT: bool = False
    ENABLE_SPACY: bool = False
    AI_REQUEST_TIMEOUT: float = 60.0
    SCAN_MAX_SECONDS: int = 1800
    SCRAPE_CONCURRENCY: int = 1
    MAX_SCRAPED_TEXT_LENGTH: int = 8000

    class Config:
        env_file = (BACKEND_DIR.parent / ".env", BACKEND_DIR / ".env")

    @model_validator(mode="after")
    def normalize_database_urls(self):
        # Accept the common Render variable names while keeping one canonical
        # setting inside the application.
        self.APIFY_API_TOKEN = (
            self.APIFY_API_TOKEN.strip()
            or self.APIFY_API_KEY.strip()
            or self.APIFY_TOKEN.strip()
        )
        database_url = self.DATABASE_URL.strip()
        sync_database_url = self.SYNC_DATABASE_URL.strip()

        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        if not sync_database_url:
            if database_url.startswith("postgresql+asyncpg://"):
                sync_database_url = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
            elif database_url.startswith("sqlite+aiosqlite:///"):
                sync_database_url = database_url.replace("sqlite+aiosqlite:///", "sqlite:///", 1)
            else:
                sync_database_url = database_url
        elif sync_database_url.startswith("postgres://"):
            sync_database_url = sync_database_url.replace("postgres://", "postgresql://", 1)
        elif sync_database_url.startswith("postgresql+asyncpg://"):
            sync_database_url = sync_database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        elif sync_database_url.startswith("sqlite+aiosqlite:///"):
            sync_database_url = sync_database_url.replace("sqlite+aiosqlite:///", "sqlite:///", 1)

        self.DATABASE_URL = database_url
        self.SYNC_DATABASE_URL = sync_database_url
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

get_settings.cache_clear()
settings = get_settings()
