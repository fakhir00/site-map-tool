const DEFAULT_API_URL =
  typeof window === 'undefined'
    ? 'http://localhost:8000/api'
    : `${window.location.protocol}//${window.location.hostname}:8000/api`

const API_URL = (import.meta.env.VITE_API_URL || DEFAULT_API_URL).replace(/\/$/, '')

export type User = {
  id: string
  email: string
  full_name: string | null
  plan: string
  created_at: string
}

export type Project = {
  id: string
  name: string
  domain: string
  own_domain: string | null
  scan_frequency: string
  url_filter_patterns: string[] | null
  target_keywords: string[] | null
  status: 'pending' | 'running' | 'paused' | 'complete' | 'error'
  urls_found: number
  urls_processed: number
  urls_failed: number
  total_keywords: number
  created_at: string
  last_scanned_at: string | null
}

export type ProjectStats = {
  total_urls: number
  scraped_urls: number
  failed_urls: number
  pending_urls: number
  total_keywords: number
  unique_keyword_types: Record<string, number>
}

export type ProjectSource = {
  source_type: 'own' | 'competitor' | 'ai'
  source_domain: string | null
  urls_found: number
  scraped_urls: number
  failed_urls: number
  pending_urls: number
}

export type ScanProgress = {
  status: Project['status']
  urls_found: number
  urls_processed: number
  urls_failed: number
  current_url: string | null
  percent: number
}

export type ScanJob = {
  id: string
  project_id: string
  status: string
  celery_task_id: string | null
  error_message: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
}

export type Keyword = {
  id: string
  phrase: string
  keyword_type: 'primary' | 'lsi' | 'entity' | 'heading' | 'long-tail'
  frequency: number
  search_volume: number | null
  difficulty: number | null
  source_urls: string[]
  sources: {
    url: string
    source_type: 'own' | 'competitor' | 'ai'
    source_domain: string | null
  }[]
  created_at: string
}

export type KeywordListResponse = {
  items: Keyword[]
  total: number
  page: number
  page_size: number
  pages: number
}

export type UrlItem = {
  id: string
  url: string
  source_type: 'own' | 'competitor'
  source_domain: string | null
  status: string
  error_reason: string | null
  h1: string | null
  word_count: number | null
  readability_score: number | null
  publish_date: string | null
  scraped_at: string | null
  retry_count: number
}

export type KeywordBankEntry = {
  id: string
  phrase: string
  keyword_type: Keyword['keyword_type']
  frequency: number
  notes: string | null
  saved_at: string
}

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function token() {
  return localStorage.getItem('token')
}

function errorMessage(detail: unknown) {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === 'object' && 'msg' in item) return String(item.msg)
        return String(item)
      })
      .join(', ')
  }
  return 'API request failed'
}

export const auth = {
  hasToken() {
    return Boolean(token())
  },
  setToken(accessToken: string) {
    localStorage.setItem('token', accessToken)
  },
  clear() {
    localStorage.removeItem('token')
  },
}

export const api = {
  async fetch<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const headers = new Headers(options.headers)
    const accessToken = token()

    if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
    if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
      headers.set('Content-Type', 'application/json')
    }

    const response = await fetch(`${API_URL}${endpoint}`, {
      ...options,
      headers,
    })

    if (response.status === 401) {
      auth.clear()
      if (!window.location.pathname.startsWith('/login') && !window.location.pathname.startsWith('/register')) {
        window.location.assign('/login')
      }
    }

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}))
      throw new ApiError(errorMessage(payload.detail), response.status)
    }

    if (response.status === 204) return null as T

    const contentType = response.headers.get('content-type') || ''
    if (contentType.includes('text/csv') || contentType.includes('application/pdf')) {
      return response.blob() as Promise<T>
    }

    return response.json() as Promise<T>
  },

  get<T>(endpoint: string) {
    return this.fetch<T>(endpoint, { method: 'GET' })
  },

  post<T>(endpoint: string, body?: unknown) {
    return this.fetch<T>(endpoint, {
      method: 'POST',
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  },

  delete<T>(endpoint: string) {
    return this.fetch<T>(endpoint, { method: 'DELETE' })
  },
}
