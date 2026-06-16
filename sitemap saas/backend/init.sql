-- SiteMapSEO Database Schema

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255),
    full_name VARCHAR(255),
    google_id VARCHAR(255),
    plan VARCHAR(50) DEFAULT 'free',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Projects table
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    domain VARCHAR(512) NOT NULL,
    own_domain VARCHAR(512),
    scan_frequency VARCHAR(50) DEFAULT 'once',
    url_filter_patterns JSONB DEFAULT '["/blog/", "/news/", "/post/", "/article/"]'::jsonb,
    target_keywords JSONB,
    status VARCHAR(50) DEFAULT 'pending',
    urls_found INTEGER DEFAULT 0,
    urls_processed INTEGER DEFAULT 0,
    urls_failed INTEGER DEFAULT 0,
    total_keywords INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_scanned_at TIMESTAMPTZ,
    next_scan_at TIMESTAMPTZ
);

-- Scan jobs table
CREATE TABLE IF NOT EXISTS scan_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    status VARCHAR(50) DEFAULT 'queued',
    celery_task_id VARCHAR(255),
    error_message TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- URLs table
CREATE TABLE IF NOT EXISTS urls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    scan_job_id UUID REFERENCES scan_jobs(id),
    url TEXT NOT NULL,
    source_type VARCHAR(50) DEFAULT 'competitor',
    source_domain VARCHAR(512),
    status VARCHAR(50) DEFAULT 'pending',
    error_reason TEXT,
    h1 TEXT,
    word_count INTEGER,
    readability_score FLOAT,
    publish_date DATE,
    scraped_at TIMESTAMPTZ,
    retry_count INTEGER DEFAULT 0,
    UNIQUE(project_id, url)
);

-- Keywords table
CREATE TABLE IF NOT EXISTS keywords (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    phrase TEXT NOT NULL,
    keyword_type VARCHAR(50) DEFAULT 'primary',
    frequency INTEGER DEFAULT 1,
    search_volume INTEGER,
    difficulty FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(project_id, phrase)
);

-- Keyword-URL junction table
CREATE TABLE IF NOT EXISTS keyword_urls (
    keyword_id UUID NOT NULL REFERENCES keywords(id) ON DELETE CASCADE,
    url_id UUID NOT NULL REFERENCES urls(id) ON DELETE CASCADE,
    PRIMARY KEY (keyword_id, url_id)
);

-- Keyword bank (user-saved keywords)
CREATE TABLE IF NOT EXISTS keyword_bank (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    keyword_id UUID NOT NULL REFERENCES keywords(id) ON DELETE CASCADE,
    notes TEXT,
    saved_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, keyword_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id);
CREATE INDEX IF NOT EXISTS idx_urls_project_id ON urls(project_id);
CREATE INDEX IF NOT EXISTS idx_urls_status ON urls(status);
CREATE INDEX IF NOT EXISTS idx_keywords_project_id ON keywords(project_id);
CREATE INDEX IF NOT EXISTS idx_keywords_frequency ON keywords(project_id, frequency DESC);
CREATE INDEX IF NOT EXISTS idx_scan_jobs_project_id ON scan_jobs(project_id);
