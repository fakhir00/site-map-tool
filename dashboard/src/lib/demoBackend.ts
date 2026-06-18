import type {
  Keyword,
  KeywordBankEntry,
  KeywordListResponse,
  Project,
  ProjectSource,
  ProjectStats,
  ScanJob,
  ScanProgress,
  UrlItem,
  User,
} from './api'

type DemoUserRecord = User & {
  password: string
}

type DemoKeywordBankRecord = KeywordBankEntry & {
  user_id: string
  keyword_id: string
}

type DemoProjectRecord = Project & {
  user_id: string
  urls: UrlItem[]
  keywords: Keyword[]
  keywordBankIds: string[]
  jobs: ScanJob[]
  scan_status: ScanProgress
}

type DemoState = {
  users: DemoUserRecord[]
  projects: DemoProjectRecord[]
  keywordBank: DemoKeywordBankRecord[]
}

type DemoKeywordSource = Keyword['sources'][number]

const STORAGE_KEY = 'sitemapseo-demo-state-v1'
const DEMO_DELAY_MS = 140
const AI_SOURCE_URL = 'https://openrouter.ai/generated'

const defaultState: DemoState = {
  users: [],
  projects: [],
  keywordBank: [],
}

export class DemoApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'DemoApiError'
    this.status = status
  }
}

function delay() {
  return new Promise((resolve) => window.setTimeout(resolve, DEMO_DELAY_MS))
}

function loadState() {
  const raw = localStorage.getItem(STORAGE_KEY)
  if (!raw) return structuredClone(defaultState)

  try {
    const parsed = JSON.parse(raw) as Partial<DemoState>
    return {
      users: parsed.users || [],
      projects: parsed.projects || [],
      keywordBank: parsed.keywordBank || [],
    } satisfies DemoState
  } catch {
    return structuredClone(defaultState)
  }
}

function saveState(state: DemoState) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
}

function jsonBody(options: RequestInit) {
  if (!options.body || typeof options.body !== 'string') return {}
  try {
    return JSON.parse(options.body) as Record<string, unknown>
  } catch {
    return {}
  }
}

function bearerToken(options: RequestInit) {
  const headers = new Headers(options.headers)
  const authHeader = headers.get('Authorization') || ''
  return authHeader.startsWith('Bearer ') ? authHeader.slice(7) : ''
}

function currentUser(state: DemoState, options: RequestInit) {
  const token = bearerToken(options)
  if (!token) {
    throw new DemoApiError('Invalid or missing authentication token', 401)
  }

  const user = state.users.find((item) => item.id === token)
  if (!user) {
    throw new DemoApiError('Invalid or missing authentication token', 401)
  }

  return user
}

function stripPassword(user: DemoUserRecord): User {
  const { password: _password, ...safeUser } = user
  return safeUser
}

function isoNow() {
  return new Date().toISOString()
}

function slugify(value: string) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

function keywordTitle(value: string) {
  return value
    .split(/\s+/)
    .filter(Boolean)
    .map((item) => item.charAt(0).toUpperCase() + item.slice(1))
    .join(' ')
}

function domainHost(value: string) {
  try {
    const normalized = value.startsWith('http://') || value.startsWith('https://') ? value : `https://${value}`
    return new URL(normalized).hostname.replace(/^www\./, '')
  } catch {
    return value.replace(/^https?:\/\//, '').replace(/^www\./, '')
  }
}

function ensureOrigin(value: string) {
  try {
    const normalized = value.startsWith('http://') || value.startsWith('https://') ? value : `https://${value}`
    const url = new URL(normalized)
    return `${url.protocol}//${url.host}`
  } catch {
    return `https://${domainHost(value)}`
  }
}

function ownSourceDomain(project: DemoProjectRecord) {
  return ensureOrigin(project.own_domain || project.domain)
}

function competitorDomains(host: string) {
  const base = host.split('.')[0] || 'competitor'
  return [
    `https://${base}labs.io`,
    `https://${base}hq.co`,
    `https://${base}guide.com`,
  ]
}

function sourceLabel(source: DemoKeywordSource) {
  return source.source_domain || source.url
}

function projectSources(urls: UrlItem[]): ProjectSource[] {
  const grouped = new Map<string, ProjectSource>()

  urls.forEach((url) => {
    const sourceDomain = url.source_domain || ensureOrigin(url.url)
    const key = `${url.source_type}:${sourceDomain}`
    const existing = grouped.get(key) || {
      source_type: url.source_type,
      source_domain: sourceDomain,
      urls_found: 0,
      scraped_urls: 0,
      failed_urls: 0,
      pending_urls: 0,
    }

    existing.urls_found += 1
    if (url.status === 'scraped') existing.scraped_urls += 1
    if (url.status === 'failed') existing.failed_urls += 1
    if (url.status === 'pending') existing.pending_urls += 1

    grouped.set(key, existing)
  })

  return Array.from(grouped.values()).sort((left, right) => {
    if (left.source_type === right.source_type) {
      return (left.source_domain || '').localeCompare(right.source_domain || '')
    }
    return left.source_type === 'own' ? -1 : 1
  })
}

function projectStats(project: DemoProjectRecord): ProjectStats {
  const unique_keyword_types = project.keywords.reduce<Record<string, number>>((acc, keyword) => {
    acc[keyword.keyword_type] = (acc[keyword.keyword_type] || 0) + 1
    return acc
  }, {})

  return {
    total_urls: project.urls.length,
    scraped_urls: project.urls.filter((item) => item.status === 'scraped').length,
    failed_urls: project.urls.filter((item) => item.status === 'failed').length,
    pending_urls: project.urls.filter((item) => item.status === 'pending').length,
    total_keywords: project.keywords.length,
    unique_keyword_types,
  }
}

function scanStatus(project: DemoProjectRecord): ScanProgress {
  return {
    status: project.status,
    urls_found: project.urls_found,
    urls_processed: project.urls_processed,
    urls_failed: project.urls_failed,
    current_url: project.status === 'complete' ? null : 'Scanning sitemap pages',
    percent: project.status === 'complete' ? 100 : 0,
  }
}

function makeUrl(sourceType: 'own' | 'competitor', sourceDomain: string, path: string, status: UrlItem['status']) {
  const timestamp = isoNow()
  return {
    id: crypto.randomUUID(),
    url: `${sourceDomain}${path}`,
    source_type: sourceType,
    source_domain: sourceDomain,
    status,
    error_reason: status === 'failed' ? 'Robots rule blocked body extraction' : null,
    h1: status === 'failed' ? null : keywordTitle(path.split('/').pop()?.replace(/-/g, ' ') || 'Untitled'),
    word_count: status === 'failed' ? null : 900 + path.length * 7,
    readability_score: status === 'failed' ? null : 61,
    publish_date: timestamp,
    scraped_at: status === 'failed' ? null : timestamp,
    retry_count: status === 'failed' ? 1 : 0,
  } satisfies UrlItem
}

function selectSources(urls: UrlItem[], count: number) {
  return urls.slice(0, count).map((url) => ({
    url: url.url,
    source_type: url.source_type,
    source_domain: url.source_domain,
  })) satisfies DemoKeywordSource[]
}

function keywordRecord(phrase: string, keywordType: Keyword['keyword_type'], sources: DemoKeywordSource[]) {
  return {
    id: crypto.randomUUID(),
    phrase,
    keyword_type: keywordType,
    frequency: sources.length,
    search_volume: null,
    difficulty: null,
    source_urls: sources.map((source) => source.url),
    sources,
    created_at: isoNow(),
  } satisfies Keyword
}

function buildScanData(project: DemoProjectRecord) {
  const primaryKeyword = project.target_keywords?.[0] || 'seo discovery'
  const keywordSlug = slugify(primaryKeyword)
  const ownDomain = ownSourceDomain(project)
  const [compA, compB, compC] = competitorDomains(domainHost(project.domain))

  const urls = [
    makeUrl('own', ownDomain, `/blog/${keywordSlug}-playbook`, 'scraped'),
    makeUrl('own', ownDomain, `/resources/${keywordSlug}-checklist`, 'scraped'),
    makeUrl('competitor', compA, `/blog/${keywordSlug}-examples`, 'scraped'),
    makeUrl('competitor', compA, `/guides/${keywordSlug}-strategy`, 'scraped'),
    makeUrl('competitor', compB, `/insights/${keywordSlug}-template`, 'scraped'),
    makeUrl('competitor', compB, `/blog/${keywordSlug}-mistakes`, 'scraped'),
    makeUrl('competitor', compC, `/resources/${keywordSlug}-metrics`, 'scraped'),
    makeUrl('competitor', compC, `/blog/${keywordSlug}-audit`, 'failed'),
  ]

  const sourceSet = {
    own: selectSources(urls.filter((url) => url.source_type === 'own'), 2),
    mixA: selectSources(urls.filter((url) => url.source_type !== 'own'), 3),
    mixB: selectSources(urls.filter((url) => url.source_type !== 'own').slice(2), 3),
    mixC: selectSources(urls.filter((url) => url.source_type !== 'own').slice(1), 2),
  }

  const phrases: Array<[string, Keyword['keyword_type'], DemoKeywordSource[]]> = [
    [`${primaryKeyword} strategy`, 'primary', sourceSet.mixA],
    [`${primaryKeyword} examples`, 'lsi', sourceSet.mixB],
    [`${primaryKeyword} template`, 'heading', sourceSet.mixA],
    [`${primaryKeyword} checklist`, 'heading', [...sourceSet.own, ...sourceSet.mixC].slice(0, 3)],
    [`best ${primaryKeyword} tools`, 'entity', sourceSet.mixB],
    [`how to improve ${primaryKeyword}`, 'long-tail', sourceSet.mixA],
    [`${primaryKeyword} metrics`, 'entity', sourceSet.mixC],
    [`${primaryKeyword} audit`, 'lsi', sourceSet.mixB],
    [`${primaryKeyword} content brief`, 'long-tail', sourceSet.mixA],
    [`${primaryKeyword} workflow`, 'primary', [...sourceSet.own, ...sourceSet.mixC].slice(0, 2)],
    [`${primaryKeyword} competitor analysis`, 'long-tail', sourceSet.mixB],
    [`${primaryKeyword} reporting`, 'heading', sourceSet.mixC],
  ]

  const keywords = phrases.map(([phrase, type, sources]) => keywordRecord(phrase, type, sources))

  return {
    urls,
    keywords,
  }
}

function ensureProjectOwner(project: DemoProjectRecord | undefined, userId: string) {
  if (!project || project.user_id !== userId) {
    throw new DemoApiError('Project not found', 404)
  }
  return project
}

function createProjectRecord(userId: string, payload: Record<string, unknown>) {
  const now = isoNow()
  return {
    id: crypto.randomUUID(),
    user_id: userId,
    name: String(payload.name || 'New scan'),
    domain: String(payload.domain || ''),
    own_domain: String(payload.own_domain || payload.domain || ''),
    scan_frequency: String(payload.scan_frequency || 'once'),
    url_filter_patterns: null,
    target_keywords: Array.isArray(payload.target_keywords)
      ? payload.target_keywords.map((item) => String(item)).filter(Boolean)
      : null,
    status: 'pending',
    urls_found: 0,
    urls_processed: 0,
    urls_failed: 0,
    total_keywords: 0,
    created_at: now,
    last_scanned_at: null,
    urls: [],
    keywords: [],
    keywordBankIds: [],
    jobs: [],
    scan_status: {
      status: 'pending',
      urls_found: 0,
      urls_processed: 0,
      urls_failed: 0,
      current_url: null,
      percent: 0,
    },
  } satisfies DemoProjectRecord
}

function startProjectScan(project: DemoProjectRecord) {
  const now = isoNow()
  const { urls, keywords } = buildScanData(project)
  const scrapedUrls = urls.filter((url) => url.status === 'scraped').length
  const failedUrls = urls.filter((url) => url.status === 'failed').length

  project.urls = urls
  project.keywords = keywords
  project.status = 'complete'
  project.urls_found = urls.length
  project.urls_processed = scrapedUrls
  project.urls_failed = failedUrls
  project.total_keywords = keywords.length
  project.last_scanned_at = now
  project.scan_status = scanStatus(project)

  const job = {
    id: crypto.randomUUID(),
    project_id: project.id,
    status: 'complete',
    celery_task_id: 'demo-scan',
    error_message: null,
    started_at: now,
    finished_at: now,
    created_at: now,
  } satisfies ScanJob

  project.jobs = [job, ...project.jobs].slice(0, 20)
  return job
}

function saveKeywordToBank(state: DemoState, user: User, project: DemoProjectRecord, keywordId: string) {
  const keyword = project.keywords.find((item) => item.id === keywordId)
  if (!keyword) {
    throw new DemoApiError('Keyword not found', 404)
  }

  const existing = state.keywordBank.find((entry) => entry.user_id === user.id && entry.keyword_id === keywordId)
  if (existing) {
    return { message: 'Already saved' }
  }

  const entry = {
    id: crypto.randomUUID(),
    user_id: user.id,
    keyword_id: keyword.id,
    phrase: keyword.phrase,
    keyword_type: keyword.keyword_type,
    frequency: keyword.frequency,
    notes: null,
    saved_at: isoNow(),
  } satisfies DemoKeywordBankRecord

  state.keywordBank.unshift(entry)
  project.keywordBankIds.push(entry.id)
  return { message: 'Keyword saved to bank' }
}

function generateAiKeywords(project: DemoProjectRecord) {
  const primaryKeyword = project.target_keywords?.[0] || 'seo discovery'
  const aiPhrases = [
    `${primaryKeyword} dashboard ideas`,
    `${primaryKeyword} launch sequence`,
    `${primaryKeyword} prioritization matrix`,
    `${primaryKeyword} growth experiments`,
    `${primaryKeyword} content moat`,
  ]

  const aiSource: DemoKeywordSource = {
    url: AI_SOURCE_URL,
    source_type: 'ai',
    source_domain: 'OpenRouter AI',
  }

  let added = 0
  aiPhrases.forEach((phrase, index) => {
    if (project.keywords.some((keyword) => keyword.phrase === phrase)) return
      project.keywords.unshift(
      keywordRecord(phrase, index % 2 === 0 ? 'long-tail' : 'entity', [aiSource]),
    )
    added += 1
  })

  project.total_keywords = project.keywords.length
  return { message: `Generated ${added} new keywords`, generated: aiPhrases.length }
}

function keywordPage(project: DemoProjectRecord, url: URL) {
  const page = Number(url.searchParams.get('page') || '1')
  const pageSize = Number(url.searchParams.get('page_size') || '20')
  const search = (url.searchParams.get('search') || '').trim().toLowerCase()
  const keywordType = (url.searchParams.get('keyword_type') || '').trim()

  let items = [...project.keywords]

  if (keywordType) {
    items = items.filter((keyword) => keyword.keyword_type === keywordType)
  }

  if (search) {
    items = items.filter((keyword) => keyword.phrase.toLowerCase().includes(search))
  }

  items.sort((left, right) => right.frequency - left.frequency || left.phrase.localeCompare(right.phrase))

  const total = items.length
  const start = Math.max(0, (page - 1) * pageSize)
  const paged = items.slice(start, start + pageSize)

  return {
    items: paged,
    total,
    page,
    page_size: pageSize,
    pages: Math.max(1, Math.ceil(total / pageSize)),
  } satisfies KeywordListResponse
}

function exportKeywords(project: DemoProjectRecord) {
  const rows = [
    ['Keyword Gap', 'Type', 'Competitor Pages', 'Source Domains', 'Source URLs', 'Search Volume', 'Difficulty'],
    ...project.keywords.map((keyword) => [
      keyword.phrase,
      keyword.keyword_type,
      String(keyword.frequency),
      Array.from(new Set(keyword.sources.map(sourceLabel))).join('; '),
      keyword.source_urls.join('; '),
      keyword.search_volume ? String(keyword.search_volume) : '',
      keyword.difficulty ? String(keyword.difficulty) : '',
    ]),
  ]

  const csv = rows
    .map((row) =>
      row
        .map((cell) => `"${String(cell).replace(/"/g, '""')}"`)
        .join(','),
    )
    .join('\n')

  return new Blob([csv], { type: 'text/csv;charset=utf-8' })
}

function projectUrls(project: DemoProjectRecord, url: URL) {
  const page = Number(url.searchParams.get('page') || '1')
  const pageSize = Number(url.searchParams.get('page_size') || '50')
  const statusFilter = url.searchParams.get('status_filter') || ''

  let items = [...project.urls]
  if (statusFilter) {
    items = items.filter((item) => item.status === statusFilter)
  }

  const start = Math.max(0, (page - 1) * pageSize)
  return items.slice(start, start + pageSize)
}

function projectById(state: DemoState, id: string) {
  return state.projects.find((project) => project.id === id)
}

function keywordBank(state: DemoState, userId: string) {
  return state.keywordBank
    .filter((entry) => entry.user_id === userId)
    .sort((left, right) => right.saved_at.localeCompare(left.saved_at))
    .map(({ user_id: _userId, keyword_id: _keywordId, ...entry }) => entry)
}

export async function demoFetch<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  await delay()

  const url = new URL(endpoint, 'https://demo.local')
  const state = loadState()
  const method = (options.method || 'GET').toUpperCase()
  const path = url.pathname

  if (path === '/auth/register' && method === 'POST') {
    const body = jsonBody(options)
    const email = String(body.email || '').trim().toLowerCase()
    const password = String(body.password || '')
    const fullName = String(body.full_name || '').trim()

    if (!email || !password) {
      throw new DemoApiError('Email and password are required', 422)
    }

    if (password.length < 8) {
      throw new DemoApiError('Password must be at least 8 characters', 422)
    }

    if (state.users.some((user) => user.email === email)) {
      throw new DemoApiError('Email already registered', 400)
    }

    const user = {
      id: crypto.randomUUID(),
      email,
      password,
      full_name: fullName || null,
      plan: 'free',
      created_at: isoNow(),
    } satisfies DemoUserRecord

    state.users.push(user)
    saveState(state)

    return {
      access_token: user.id,
      token_type: 'bearer',
      user: stripPassword(user),
    } as T
  }

  if (path === '/auth/login' && method === 'POST') {
    const body = jsonBody(options)
    const email = String(body.email || '').trim().toLowerCase()
    const password = String(body.password || '')
    const user = state.users.find((item) => item.email === email)

    if (!user || user.password !== password) {
      throw new DemoApiError('Invalid email or password', 401)
    }

    return {
      access_token: user.id,
      token_type: 'bearer',
      user: stripPassword(user),
    } as T
  }

  const user = currentUser(state, options)

  if (path === '/auth/me' && method === 'GET') {
    return stripPassword(user) as T
  }

  if (path === '/projects' && method === 'GET') {
    return state.projects
      .filter((project) => project.user_id === user.id)
      .sort((left, right) => right.created_at.localeCompare(left.created_at)) as T
  }

  if (path === '/projects' && method === 'POST') {
    const payload = jsonBody(options)
    const targetKeywords = Array.isArray(payload.target_keywords) ? payload.target_keywords : []

    if (!targetKeywords.length || !String(targetKeywords[0] || '').trim()) {
      throw new DemoApiError('Primary keyword is required', 422)
    }

    const project = createProjectRecord(user.id, payload)
    state.projects.unshift(project)
    saveState(state)
    return project as T
  }

  if (path === '/keyword-bank' && method === 'GET') {
    return keywordBank(state, user.id) as T
  }

  const projectMatch = path.match(/^\/projects\/([^/]+)(?:\/(.*))?$/)
  if (!projectMatch) {
    throw new DemoApiError('Endpoint not found', 404)
  }

  const [, projectId, suffix = ''] = projectMatch
  const project = ensureProjectOwner(projectById(state, projectId), user.id)

  if (!suffix && method === 'GET') {
    return project as T
  }

  if (!suffix && method === 'DELETE') {
    state.projects = state.projects.filter((item) => item.id !== project.id)
    state.keywordBank = state.keywordBank.filter((entry) => entry.user_id !== user.id || !project.keywords.some((keyword) => keyword.id === entry.keyword_id))
    saveState(state)
    return null as T
  }

  if (suffix === 'stats' && method === 'GET') {
    return projectStats(project) as T
  }

  if (suffix === 'urls' && method === 'GET') {
    return projectUrls(project, url) as T
  }

  if (suffix === 'sources' && method === 'GET') {
    return projectSources(project.urls) as T
  }

  if (suffix === 'scan/status' && method === 'GET') {
    return scanStatus(project) as T
  }

  if (suffix === 'scan/jobs' && method === 'GET') {
    return project.jobs as T
  }

  if (suffix === 'scan/start' && method === 'POST') {
    if (project.status === 'running') {
      throw new DemoApiError('Scan already running for this project', 409)
    }

    const job = startProjectScan(project)
    saveState(state)
    return job as T
  }

  if (suffix === 'scan/pause' && method === 'POST') {
    if (project.status !== 'running') {
      throw new DemoApiError('Only a running scan can be paused', 409)
    }
    project.status = 'paused'
    project.scan_status = scanStatus(project)
    saveState(state)
    return { message: 'Scan paused' } as T
  }

  if (suffix === 'scan/resume' && method === 'POST') {
    if (project.status !== 'paused') {
      throw new DemoApiError('Only a paused scan can be resumed', 409)
    }
    const job = startProjectScan(project)
    saveState(state)
    return job as T
  }

  if (suffix === 'keywords' && method === 'GET') {
    return keywordPage(project, url) as T
  }

  if (suffix === 'keywords/generate' && method === 'POST') {
    const result = generateAiKeywords(project)
    saveState(state)
    return result as T
  }

  if (suffix === 'keywords/export' && method === 'GET') {
    return exportKeywords(project) as T
  }

  const saveMatch = suffix.match(/^keywords\/([^/]+)\/save$/)
  if (saveMatch && method === 'POST') {
    const [, keywordId] = saveMatch
    const result = saveKeywordToBank(state, user, project, keywordId)
    saveState(state)
    return result as T
  }

  throw new DemoApiError('Endpoint not found', 404)
}
