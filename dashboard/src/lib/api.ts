import { DemoApiError, demoFetch } from './demoBackend'

const configuredApiUrl = import.meta.env.VITE_API_URL?.trim()
const isBrowser = typeof window !== 'undefined'
const isLocalHost =
  isBrowser && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
const DEFAULT_API_URL =
  !isBrowser || isLocalHost ? 'http://localhost:8000/api' : '/api'
const API_URL = (configuredApiUrl || DEFAULT_API_URL).replace(/\/$/, '')
const REQUEST_TIMEOUT_MS = 20_000
const ARTICLE_REQUEST_TIMEOUT_MS = 300_000
const needsProductionApiUrl = isBrowser && !isLocalHost && !configuredApiUrl
export const DEMO_BACKEND_ENABLED =
  import.meta.env.VITE_ENABLE_DEMO_BACKEND === 'true' || needsProductionApiUrl

type ApiRequestInit = RequestInit & {
  timeoutMs?: number
}

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

export type ArticleDraft = {
  id: string
  project_id: string
  keyword_id: string
  keyword_phrase: string
  status: 'passed' | 'needs_revision' | 'generating' | 'error'
  title: string | null
  content_markdown: string | null
  audit_score: number | null
  generation_attempts: number
  research_summary: {
    brief?: {
      content_gaps?: string[]
      competitor_takeaways?: string[]
      must_include_terms?: string[]
      recommended_title?: string
      meta_description?: string
    }
    master_prompt?: string
    competitor_pages?: Array<{
      url: string
      domain: string | null
      title: string | null
    }>
    own_pages?: Array<{
      url: string
      domain: string | null
      title: string | null
    }>
  } | null
  audit_feedback: {
    score?: number
    passed?: boolean
    strengths?: string[]
    issues?: string[]
    revision_notes?: string[]
  } | null
  created_at: string
  updated_at: string
}

export type ArticleListResponse = {
  items: ArticleDraft[]
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
  if (detail && typeof detail === 'object') {
    const message =
      ('message' in detail && typeof detail.message === 'string' && detail.message) ||
      ('error' in detail && typeof detail.error === 'string' && detail.error)

    if (message) return message

    const serialized = JSON.stringify(detail)
    if (serialized !== '{}' && serialized !== '[]') return serialized
  }
  return 'API request failed'
}

function apiConnectionMessage(reason: 'timeout' | 'network' | 'html') {
  if (needsProductionApiUrl) {
    return 'Could not reach the API. Add VITE_API_URL in Vercel with your deployed backend URL ending in /api, then redeploy the dashboard.'
  }

  if (reason === 'timeout') {
    return `The API request timed out. Make sure the backend is reachable at ${API_URL}.`
  }

  if (reason === 'html') {
    return `Expected an API response but received the frontend app. Check that ${API_URL} points to the deployed backend.`
  }

  return `Could not reach the API at ${API_URL}. Make sure the backend is running and CORS allows this dashboard URL.`
}

async function parseErrorResponse(response: Response) {
  const contentType = response.headers.get('content-type') || ''

  if (contentType.includes('application/json')) {
    const payload = (await response.json().catch(() => null)) as
      | { detail?: unknown; message?: unknown; error?: unknown }
      | null

    if (payload) {
      if ('detail' in payload && payload.detail !== undefined) {
        return errorMessage(payload.detail)
      }
      if ('message' in payload && payload.message !== undefined) {
        return errorMessage(payload.message)
      }
      if ('error' in payload && payload.error !== undefined) {
        return errorMessage(payload.error)
      }

      const serialized = JSON.stringify(payload)
      if (serialized !== '{}' && serialized !== '[]') {
        return serialized
      }
    }
  }

  const text = (await response.text().catch(() => '')).trim()

  if (contentType.includes('text/html') || /^<!doctype html/i.test(text) || /^<html/i.test(text)) {
    return apiConnectionMessage('html')
  }

  if (text) {
    return text
  }

  if (response.status === 404 && needsProductionApiUrl) {
    return apiConnectionMessage('network')
  }

  return `${response.status} ${response.statusText || 'API request failed'}`
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
  async fetch<T>(endpoint: string, options: ApiRequestInit = {}): Promise<T> {
    const { timeoutMs = REQUEST_TIMEOUT_MS, ...requestOptions } = options
    const headers = new Headers(options.headers)
    const accessToken = token()

    if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
    if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
      headers.set('Content-Type', 'application/json')
    }

    if (DEMO_BACKEND_ENABLED) {
      try {
        return await demoFetch<T>(endpoint, {
          ...requestOptions,
          headers,
        })
      } catch (err) {
        if (err instanceof DemoApiError) {
          throw new ApiError(err.message, err.status)
        }
        throw new ApiError(err instanceof Error ? err.message : 'Demo backend failed', 0)
      }
    }

    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs)

    if (options.signal) {
      if (options.signal.aborted) {
        controller.abort()
      } else {
        options.signal.addEventListener('abort', () => controller.abort(), { once: true })
      }
    }

    let response: Response

    try {
      response = await fetch(`${API_URL}${endpoint}`, {
        ...requestOptions,
        headers,
        signal: controller.signal,
      })
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        throw new ApiError(apiConnectionMessage('timeout'), 0)
      }

      throw new ApiError(apiConnectionMessage('network'), 0)
    } finally {
      clearTimeout(timeoutId)
    }

    if (response.status === 401) {
      auth.clear()
      if (!window.location.pathname.startsWith('/login') && !window.location.pathname.startsWith('/register')) {
        window.location.assign('/login')
      }
    }

    if (!response.ok) {
      throw new ApiError(await parseErrorResponse(response), response.status)
    }

    if (response.status === 204) return null as T

    const contentType = response.headers.get('content-type') || ''
    if (contentType.includes('text/csv') || contentType.includes('application/pdf')) {
      return response.blob() as Promise<T>
    }

    if (contentType.includes('application/json')) {
      return response.json() as Promise<T>
    }

    throw new ApiError(apiConnectionMessage('html'), response.status)
  },

  get<T>(endpoint: string, options: ApiRequestInit = {}) {
    return this.fetch<T>(endpoint, { ...options, method: 'GET' })
  },

  post<T>(endpoint: string, body?: unknown, options: ApiRequestInit = {}) {
    return this.fetch<T>(endpoint, {
      ...options,
      method: 'POST',
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  },

  delete<T>(endpoint: string, options: ApiRequestInit = {}) {
    return this.fetch<T>(endpoint, { ...options, method: 'DELETE' })
  },

  postArticle<T>(endpoint: string, body?: unknown) {
    return this.post<T>(endpoint, body, { timeoutMs: ARTICLE_REQUEST_TIMEOUT_MS })
  },
}
