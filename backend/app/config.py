from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./sitemapseo.db"
    SYNC_DATABASE_URL: str = "sqlite:///./sitemapseo.db"
    REDIS_URL: str = "redis://localhost:6379/0"
    USE_CELERY: bool = False
    SECRET_KEY: str = "super-secret-jwt-key-change-in-production-32chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    FRONTEND_URL: str = "http://localhost:3000"
    OPENROUTER_API_KEY: str = ""

    # Scraping
    MAX_URLS_PER_SCAN: int = 500
    MAX_COMPETITOR_DOMAINS: int = 10
    GOOGLE_SERP_RESULT_LIMIT: int = 10
    AI_KEYWORD_GAP_CANDIDATE_LIMIT: int = 80
    AI_KEYWORD_GAP_RESULT_LIMIT: int = 60
    SCRAPE_DELAY_MIN: float = 1.0
    SCRAPE_DELAY_MAX: float = 3.0
    REQUEST_TIMEOUT: int = 15
    MAX_RETRIES: int = 3
    ENABLE_KEYBERT: bool = False
    ENABLE_SPACY: bool = True

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
