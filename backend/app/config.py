from pydantic import model_validator
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./sitemapseo.db"
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
    APIFY_API_TOKEN: str = ""
    TOKENROUTER_API_KEY: str = ""
    TOKENROUTER_MODEL: str = "moonshotai/kimi-k3-free"
    TOKENROUTER_WRITING_MODEL: str = "moonshotai/kimi-k3-free"

    # Scraping
    MAX_URLS_PER_SCAN: int = 500
    MAX_COMPETITOR_DOMAINS: int = 10
    GOOGLE_SERP_RESULT_LIMIT: int = 10
    MAX_CONTENT_URLS_PER_DOMAIN: int = 8
    MAX_COMPETITOR_JUDGE_CANDIDATES: int = 12
    AI_KEYWORD_GAP_CANDIDATE_LIMIT: int = 80
    AI_KEYWORD_GAP_RESULT_LIMIT: int = 60
    ARTICLE_RESEARCH_SOURCE_LIMIT: int = 5
    ARTICLE_GENERATION_MAX_ATTEMPTS: int = 5
    SCRAPE_DELAY_MIN: float = 1.0
    SCRAPE_DELAY_MAX: float = 3.0
    REQUEST_TIMEOUT: int = 5
    MAX_RETRIES: int = 3
    ENABLE_KEYBERT: bool = False
    ENABLE_SPACY: bool = True

    class Config:
        env_file = ".env"

    @model_validator(mode="after")
    def normalize_database_urls(self):
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
    from dotenv import load_dotenv
    load_dotenv(override=True)
    return Settings()

get_settings.cache_clear()
settings = get_settings()
