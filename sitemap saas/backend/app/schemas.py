import uuid
from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, field_validator
from urllib.parse import urlparse


# ── Auth ──────────────────────────────────────────────────────
class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("full_name")
    @classmethod
    def clean_full_name(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v else None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: Optional[str]
    plan: str
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ── Projects ──────────────────────────────────────────────────
class ProjectCreate(BaseModel):
    name: str
    domain: str
    own_domain: Optional[str] = None
    scan_frequency: str = "once"
    url_filter_patterns: Optional[List[str]] = None
    target_keywords: Optional[List[str]] = None

    @field_validator("domain")
    @classmethod
    def clean_domain(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not v:
            raise ValueError("Domain is required")
        if not v.startswith(("http://", "https://")):
            v = "https://" + v
        parsed = urlparse(v)
        if not parsed.netloc:
            raise ValueError("Enter a valid domain or URL")
        return v

    @field_validator("own_domain")
    @classmethod
    def clean_own_domain(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        v = v.strip().rstrip("/")
        if not v:
            return None
        if not v.startswith(("http://", "https://")):
            v = "https://" + v
        parsed = urlparse(v)
        if not parsed.netloc:
            raise ValueError("Enter a valid own domain or URL")
        return v

    @field_validator("url_filter_patterns", "target_keywords")
    @classmethod
    def clean_string_list(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return None
        cleaned = [item.strip() for item in v if item and item.strip()]
        return cleaned or None


class ProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    domain: str
    own_domain: Optional[str]
    scan_frequency: str
    url_filter_patterns: Optional[List[str]]
    target_keywords: Optional[List[str]]
    status: str
    urls_found: int
    urls_processed: int
    urls_failed: int
    total_keywords: int
    created_at: datetime
    last_scanned_at: Optional[datetime]

    class Config:
        from_attributes = True


class ProjectStats(BaseModel):
    total_urls: int
    scraped_urls: int
    failed_urls: int
    pending_urls: int
    total_keywords: int
    unique_keyword_types: dict


class ProjectSourceOut(BaseModel):
    source_type: str
    source_domain: Optional[str]
    urls_found: int
    scraped_urls: int
    failed_urls: int
    pending_urls: int


# ── Scan ──────────────────────────────────────────────────────
class ScanJobOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    status: str
    celery_task_id: Optional[str]
    error_message: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class ScanProgress(BaseModel):
    status: str
    urls_found: int
    urls_processed: int
    urls_failed: int
    current_url: Optional[str] = None
    percent: float = 0.0


# ── Keywords ──────────────────────────────────────────────────
class KeywordSourceOut(BaseModel):
    url: str
    source_type: str
    source_domain: Optional[str]


class KeywordOut(BaseModel):
    id: uuid.UUID
    phrase: str
    keyword_type: str
    frequency: int
    search_volume: Optional[int]
    difficulty: Optional[float]
    source_urls: List[str] = Field(default_factory=list)
    sources: List[KeywordSourceOut] = Field(default_factory=list)
    created_at: datetime

    class Config:
        from_attributes = True


class KeywordListResponse(BaseModel):
    items: List[KeywordOut]
    total: int
    page: int
    page_size: int
    pages: int


class SaveKeywordRequest(BaseModel):
    notes: Optional[str] = None


# ── URLs ──────────────────────────────────────────────────────
class UrlOut(BaseModel):
    id: uuid.UUID
    url: str
    source_type: str
    source_domain: Optional[str]
    status: str
    error_reason: Optional[str]
    h1: Optional[str]
    word_count: Optional[int]
    readability_score: Optional[float]
    publish_date: Optional[date]
    scraped_at: Optional[datetime]
    retry_count: int

    class Config:
        from_attributes = True
