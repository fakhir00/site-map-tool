import uuid
from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import (
    String, Boolean, Integer, Float, Text, DateTime, Date,
    ForeignKey, JSON, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255))
    full_name: Mapped[Optional[str]] = mapped_column(String(255))
    google_id: Mapped[Optional[str]] = mapped_column(String(255))
    plan: Mapped[str] = mapped_column(String(50), default="free")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    projects: Mapped[List["Project"]] = relationship("Project", back_populates="user", cascade="all, delete-orphan")
    keyword_bank: Mapped[List["KeywordBank"]] = relationship("KeywordBank", back_populates="user", cascade="all, delete-orphan")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(512), nullable=False)
    own_domain: Mapped[Optional[str]] = mapped_column(String(512))
    scan_frequency: Mapped[str] = mapped_column(String(50), default="once")
    url_filter_patterns: Mapped[Optional[List[str]]] = mapped_column(JSON, default=lambda: ["/blog/", "/news/", "/post/", "/article/"])
    target_keywords: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    urls_found: Mapped[int] = mapped_column(Integer, default=0)
    urls_processed: Mapped[int] = mapped_column(Integer, default=0)
    urls_failed: Mapped[int] = mapped_column(Integer, default=0)
    total_keywords: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    last_scanned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    next_scan_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship("User", back_populates="projects")
    scan_jobs: Mapped[List["ScanJob"]] = relationship("ScanJob", back_populates="project", cascade="all, delete-orphan")
    urls: Mapped[List["Url"]] = relationship("Url", back_populates="project", cascade="all, delete-orphan")
    keywords: Mapped[List["Keyword"]] = relationship("Keyword", back_populates="project", cascade="all, delete-orphan")


class ScanJob(Base):
    __tablename__ = "scan_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="queued")
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(255))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    project: Mapped["Project"] = relationship("Project", back_populates="scan_jobs")


class Url(Base):
    __tablename__ = "urls"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    scan_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("scan_jobs.id"))
    url: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), default="competitor")
    source_domain: Mapped[Optional[str]] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(50), default="pending")
    error_reason: Mapped[Optional[str]] = mapped_column(Text)
    h1: Mapped[Optional[str]] = mapped_column(Text)
    word_count: Mapped[Optional[int]] = mapped_column(Integer)
    readability_score: Mapped[Optional[float]] = mapped_column(Float)
    publish_date: Mapped[Optional[date]] = mapped_column(Date)
    scraped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    project: Mapped["Project"] = relationship("Project", back_populates="urls")
    keyword_urls: Mapped[List["KeywordUrl"]] = relationship("KeywordUrl", back_populates="url", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("project_id", "url", name="uq_project_url"),)


class Keyword(Base):
    __tablename__ = "keywords"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    phrase: Mapped[str] = mapped_column(Text, nullable=False)
    keyword_type: Mapped[str] = mapped_column(String(50), default="primary")
    frequency: Mapped[int] = mapped_column(Integer, default=1)
    search_volume: Mapped[Optional[int]] = mapped_column(Integer)
    difficulty: Mapped[Optional[float]] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    project: Mapped["Project"] = relationship("Project", back_populates="keywords")
    keyword_urls: Mapped[List["KeywordUrl"]] = relationship("KeywordUrl", back_populates="keyword", cascade="all, delete-orphan")
    bank_entries: Mapped[List["KeywordBank"]] = relationship("KeywordBank", back_populates="keyword", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("project_id", "phrase", name="uq_project_phrase"),)


class KeywordUrl(Base):
    __tablename__ = "keyword_urls"

    keyword_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("keywords.id", ondelete="CASCADE"), primary_key=True)
    url_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("urls.id", ondelete="CASCADE"), primary_key=True)

    keyword: Mapped["Keyword"] = relationship("Keyword", back_populates="keyword_urls")
    url: Mapped["Url"] = relationship("Url", back_populates="keyword_urls")


class KeywordBank(Base):
    __tablename__ = "keyword_bank"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    keyword_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("keywords.id", ondelete="CASCADE"), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="keyword_bank")
    keyword: Mapped["Keyword"] = relationship("Keyword", back_populates="bank_entries")

    __table_args__ = (UniqueConstraint("user_id", "keyword_id", name="uq_user_keyword"),)
