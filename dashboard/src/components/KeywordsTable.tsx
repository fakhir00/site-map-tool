import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BookmarkPlus, ChevronLeft, ChevronRight, Download, ExternalLink, FilePenLine, Network, Search, Sparkles, ZoomIn, ZoomOut } from 'lucide-react'
import { api, type Keyword, type KeywordListResponse } from '../lib/api'
import { Badge } from './ui/Badge'
import { Button } from './ui/Button'
import { Card } from './ui/Card'
import { Input } from './ui/Input'

function keywordBadge(type: Keyword['keyword_type']) {
  if (type === 'top-pick') return <Badge variant="amber" className="text-[10px] px-1.5 py-0.5"><Sparkles className="mr-1 inline-block h-2.5 w-2.5" /> Top pick</Badge>
  if (type === 'primary') return <Badge variant="green" className="text-[10px] px-1.5 py-0.5">Primary</Badge>
  if (type === 'lsi') return <Badge variant="indigo" className="text-[10px] px-1.5 py-0.5">LSI</Badge>
  if (type === 'entity') return <Badge variant="amber" className="text-[10px] px-1.5 py-0.5">Entity</Badge>
  if (type === 'long-tail') return <Badge variant="cyan" className="text-[10px] px-1.5 py-0.5">Long-tail</Badge>
  return <Badge variant="slate" className="text-[10px] px-1.5 py-0.5">Heading</Badge>
}

function displayHost(value: string) {
  try {
    const withScheme = value.startsWith('http://') || value.startsWith('https://') ? value : `https://${value}`
    return new URL(withScheme).hostname.replace(/^www\./, '')
  } catch {
    return value.replace(/^https?:\/\//, '')
  }
}

function keywordSources(keyword: Keyword) {
  if (keyword.sources?.length) return keyword.sources
  return keyword.source_urls.map((url) => ({
    url,
    source_type: 'competitor' as const,
    source_domain: null,
  }))
}

function sourceDomains(keyword: Keyword) {
  const byLabel = new Map<string, { href: string; label: string; sourceType: 'own' | 'competitor' | 'ai' | 'provider' }>()
  keywordSources(keyword).forEach((source) => {
    const href = source.url
    const label = source.source_domain || displayHost(href)
    if (!byLabel.has(label)) {
      byLabel.set(label, { href, label, sourceType: source.source_type })
    }
  })
  return Array.from(byLabel.values())
}

function getCompetitorCount(keyword: Keyword): number {
  const sources = keywordSources(keyword)
  const compPages = sources.filter((s) => s.source_type === 'competitor').length
  const hasAi = sources.some((s) => s.source_type === 'ai')
  const hasProvider = sources.some((s) => s.source_type === 'provider')

  let count = compPages
  if (hasAi) count += 1
  if (hasProvider) count += 1

  if (count > 0) return count
  if (typeof keyword.competitor_pages === 'number' && keyword.competitor_pages > 0) {
    return keyword.competitor_pages
  }
  return 0
}

function getSourceTier(keyword: Keyword): number {
  const sources = keywordSources(keyword)
  if (sources.some((s) => s.source_type === 'competitor')) return 1
  if (sources.some((s) => s.source_type === 'provider')) return 2
  if (sources.some((s) => s.source_type === 'ai')) return 3
  return 4
}

function KeywordIntentBadge({ keywordPhrase }: { keywordPhrase: string }) {
  const [intent, setIntent] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () => api.postAI<{ intent: string, competitors: string[] }>('/website-prompts/analyze-intent', { keyword: keywordPhrase, short_mode: true }),
    onSuccess: (data: { intent: string, competitors: string[] }) => {
      setIntent(data.intent)
    }
  })

  if (intent) {
    return <span className="inline-flex max-w-[100px] truncate items-center rounded-md border border-soft-violet/30 bg-soft-violet/10 px-1.5 py-0.5 text-[10px] font-medium text-soft-violet" title={intent}>{intent}</span>
  }

  return (
    <div><Button
      variant="secondary"
      size="xs"
      className="h-5 px-1.5 py-0 text-[10px] font-medium"
      disabled={mutation.isPending}
      onClick={() => mutation.mutate()}
    >
      {mutation.isPending ? '...' : 'Intent'}
    </Button>{mutation.isError && <p role="alert" className="mt-0.5 max-w-36 text-[10px] text-warm-red">{mutation.error.message}</p>}</div>
  )
}

function TableSkeleton() {
  return (
    <div className="space-y-2 p-3">
      {[0, 1, 2, 3, 4].map(i => (
        <div key={i} className="flex items-center gap-3">
          <div className="animate-shimmer h-4 w-1/3 rounded-lg" />
          <div className="animate-shimmer h-4 w-12 rounded-lg" />
          <div className="animate-shimmer h-4 w-16 rounded-lg" />
          <div className="animate-shimmer ml-auto h-6 w-16 rounded-lg" />
        </div>
      ))}
    </div>
  )
}

export function KeywordsTable({ projectId, isActive = false }: { projectId: string; isActive?: boolean }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [type, setType] = useState('')
  const [exportError, setExportError] = useState('')
  const [articleError, setArticleError] = useState('')
  const [writingKeywordId, setWritingKeywordId] = useState<string | null>(null)
  const [copyMessage, setCopyMessage] = useState('')
  const [copyError, setCopyError] = useState('')

  const [zoomPercent, setZoomPercent] = useState<number>(() => {
    try {
      const saved = localStorage.getItem('gapcrawl_keywords_zoom')
      if (!saved || saved === '90') return 100
      return parseInt(saved, 10)
    } catch {
      return 100
    }
  })

  const handleZoomChange = (delta: number) => {
    setZoomPercent((prev) => {
      const next = Math.min(110, Math.max(70, prev + delta))
      try {
        localStorage.setItem('gapcrawl_keywords_zoom', next.toString())
      } catch {
        // ignore
      }
      return next
    })
  }

  const handleSetZoom = (value: number) => {
    setZoomPercent(value)
    try {
      localStorage.setItem('gapcrawl_keywords_zoom', value.toString())
    } catch {
      // ignore
    }
  }

  useEffect(() => {
    const timeout = window.setTimeout(() => setSearchQuery(search.trim()), 300)
    return () => window.clearTimeout(timeout)
  }, [search])

  const { data, isLoading, error: loadError, refetch } = useQuery({
    queryKey: ['keywords', projectId, page, searchQuery, type],
    queryFn: () => {
      const params = new URLSearchParams({
        page: page.toString(),
        page_size: '20',
      })
      if (searchQuery) params.append('search', searchQuery)
      if (type) params.append('keyword_type', type)
      params.append('sort_by', 'created_at')

      return api.get<KeywordListResponse>(`/projects/${projectId}/keywords?${params}`)
    },
    enabled: Boolean(projectId),
    retry: false,
    placeholderData: keepPreviousData,
    refetchInterval: isActive ? 7000 : false,
  })

  const saveMutation = useMutation({
    mutationFn: (keywordId: string) => api.post<{ message: string }>(`/projects/${projectId}/keywords/${keywordId}/save`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['keyword-bank'] })
    },
  })

  const topPicksMutation = useMutation({
    mutationFn: () => api.postAI(`/projects/${projectId}/keywords/top-picks`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['keywords', projectId] })
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })

  const [isSelectionMode, setIsSelectionMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const pageKeywordIds = new Set((data?.items || []).map((keyword) => keyword.id))
  const selectedPageIds = Array.from(selectedIds).filter((id) => pageKeywordIds.has(id))

  const bulkSaveMutation = useMutation({
    mutationFn: ({ tag }: { tag: string }) =>
      api.post<{ message: string }>(`/projects/${projectId}/keywords/bulk-save`, {
        keyword_ids: selectedPageIds,
        notes: tag
      }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['keyword-bank'] })
      setIsSelectionMode(false)
      setSelectedIds(new Set())
      alert(data.message)
    }
  })

  const bulkDeleteMutation = useMutation({
    mutationFn: () =>
      api.post<{ message: string }>(`/projects/${projectId}/keywords/bulk-delete`, {
        keyword_ids: selectedPageIds
      }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['keywords', projectId] })
      queryClient.invalidateQueries({ queryKey: ['projects', projectId] })
      queryClient.invalidateQueries({ queryKey: ['hub-spoke', projectId] })
      setIsSelectionMode(false)
      setSelectedIds(new Set())
      alert(data.message)
    }
  })

  const articleMutation = useMutation({
    mutationFn: (keywordId: string) => api.postArticle(`/projects/${projectId}/keywords/${keywordId}/article/generate`, {}),
    onMutate: (keywordId) => {
      setWritingKeywordId(keywordId)
      setArticleError('')
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project-articles', projectId] })
    },
    onError: (err) => {
      setArticleError(err instanceof Error ? err.message : 'Article generation failed')
    },
    onSettled: () => {
      setWritingKeywordId(null)
    },
  })

  const handleExport = async () => {
    setExportError('')
    try {
      const blob = await api.get<Blob>(`/projects/${projectId}/keywords/export`, { timeoutMs: 60_000 })
      const url = window.URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `keywords-${projectId}.csv`
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      window.URL.revokeObjectURL(url)
    } catch (err) {
      setExportError(err instanceof Error ? err.message : 'Export failed')
    }
  }

  if (isLoading && !data) {
    return <Card className="p-0" lift={false}><TableSkeleton /></Card>
  }

  const rawKeywords = data?.items || []
  const keywords = [...rawKeywords].sort((a, b) => {
    const tierA = getSourceTier(a)
    const tierB = getSourceTier(b)
    if (tierA !== tierB) return tierA - tierB
    return 0
  })

  return (
    <Card className="overflow-hidden p-0" lift={false}>
      <div className="flex flex-col gap-2.5 border-b border-line p-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative w-full sm:w-56">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" />
            <Input
              className="h-8 pl-8 text-xs"
              onChange={(event) => {
                setSearch(event.target.value)
                setPage(1)
                setSelectedIds(new Set())
              }}
              placeholder="Search gaps"
              value={search}
            />
          </div>

          <select
            aria-label="Filter by keyword type"
            className="h-8 cursor-pointer rounded-lg border border-line bg-raised px-2.5 text-xs text-ink outline-none transition-colors focus:border-glow-amber/60"
            onChange={(event) => {
              setType(event.target.value)
              setPage(1)
              setSelectedIds(new Set())
            }}
            value={type}
          >
            <option value="">All types</option>
            <option value="top-pick">Top Picks</option>
            <option value="primary">Primary</option>
            <option value="lsi">LSI</option>
            <option value="long-tail">Long-tail</option>
            <option value="entity">Entity</option>
            <option value="heading">Heading</option>
          </select>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {/* Zoom controls */}
          <div className="flex items-center gap-1 rounded-lg border border-line bg-raised/80 px-1.5 py-0.5 text-xs mr-1">
            <button
              type="button"
              aria-label="Zoom out"
              onClick={() => handleZoomChange(-5)}
              disabled={zoomPercent <= 70}
              className="h-6 w-6 rounded flex items-center justify-center text-muted hover:text-ink hover:bg-surface disabled:opacity-30 cursor-pointer transition-colors"
              title="Zoom out table"
            >
              <ZoomOut className="h-3.5 w-3.5" />
            </button>
            <span className="font-mono text-[11px] font-semibold text-muted px-1 min-w-[34px] text-center select-none" title="Current zoom level">
              {zoomPercent}%
            </span>
            <button
              type="button"
              aria-label="Zoom in"
              onClick={() => handleZoomChange(5)}
              disabled={zoomPercent >= 110}
              className="h-6 w-6 rounded flex items-center justify-center text-muted hover:text-ink hover:bg-surface disabled:opacity-30 cursor-pointer transition-colors"
              title="Zoom in table"
            >
              <ZoomIn className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={() => handleSetZoom(100)}
              className="text-[10px] text-muted hover:text-ink px-1 font-mono transition-colors cursor-pointer"
              title="Reset to 100% default zoom"
            >
              Reset
            </button>
          </div>

          {isSelectionMode ? (
            <>
              <Button
                variant="secondary"
                size="xs"
                disabled={keywords.length === 0}
                onClick={() => {
                  if (selectedPageIds.length === keywords.length) {
                    setSelectedIds(new Set())
                  } else {
                    setSelectedIds(new Set(keywords.map(k => k.id)))
                  }
                }}
              >
                {keywords.length > 0 && selectedPageIds.length === keywords.length ? 'Deselect All' : 'Select All'}
              </Button>
              <Button
                variant="secondary"
                size="xs"
                disabled={selectedPageIds.length === 0 || bulkSaveMutation.isPending}
                onClick={() => bulkSaveMutation.mutate({ tag: '#tool' })}
              >
                Tool Page
              </Button>
              <Button
                variant="secondary"
                size="xs"
                disabled={selectedPageIds.length === 0 || bulkSaveMutation.isPending}
                onClick={() => bulkSaveMutation.mutate({ tag: '#blog' })}
              >
                Blog
              </Button>
              <Button
                variant="secondary"
                size="xs"
                disabled={selectedPageIds.length === 0}
                onClick={async () => {
                  const selectedKeywords = keywords.filter(k => selectedIds.has(k.id)).map(k => k.phrase).join('\n')
                  setCopyError('')
                  setCopyMessage('')
                  try {
                    await navigator.clipboard.writeText(selectedKeywords)
                    setCopyMessage('Selected keywords copied.')
                  } catch {
                    setCopyError('Could not copy keywords. Allow clipboard access or use Export CSV.')
                  }
                }}
              >
                Copy
              </Button>
              <Button
                variant="danger"
                size="xs"
                disabled={selectedPageIds.length === 0 || bulkDeleteMutation.isPending}
                onClick={() => {
                  if (confirm('Are you sure you want to permanently delete these keywords?')) {
                    bulkDeleteMutation.mutate()
                  }
                }}
              >
                Delete
              </Button>
              <Button variant="secondary" size="xs" onClick={() => { setIsSelectionMode(false); setSelectedIds(new Set()) }}>
                Cancel
              </Button>
            </>
          ) : (
            <Button variant="secondary" size="xs" disabled={keywords.length === 0} onClick={() => setIsSelectionMode(true)}>
              Select
            </Button>
          )}

          <Button
            onClick={() => navigate(`/hub-spoke?project_id=${encodeURIComponent(projectId)}`)}
            size="xs"
            variant="secondary"
            className="border-glow-amber/40 bg-glow-amber/10 text-glow-amber hover:bg-glow-amber/20 hover:border-glow-amber/60"
          >
            <Network className="h-3.5 w-3.5" />
            Hub Spoke
          </Button>

          <Button
            disabled={topPicksMutation.isPending}
            onClick={() => topPicksMutation.mutate()}
            size="xs"
            variant="secondary"
            className="border-soft-violet/30 bg-soft-violet/10 text-soft-violet hover:bg-soft-violet/20 hover:border-soft-violet/50"
          >
            <Sparkles className="h-3.5 w-3.5" />
            {topPicksMutation.isPending ? 'Generating...' : 'Top Picks'}
          </Button>

          <Button onClick={handleExport} size="xs" variant="secondary">
            <Download className="h-3.5 w-3.5" />
            Export CSV
          </Button>
        </div>
      </div>

      {exportError && <div className="border-b border-warm-red/30 bg-warm-red/[0.07] px-3 py-2 text-xs text-warm-red">{exportError}</div>}
      {articleError && <div className="border-b border-warm-red/30 bg-warm-red/[0.07] px-3 py-2 text-xs text-warm-red">{articleError}</div>}
      {(loadError || saveMutation.error || topPicksMutation.error || bulkSaveMutation.error || bulkDeleteMutation.error || copyError) && <div role="alert" className="border-b border-warm-red/30 bg-warm-red/[0.07] px-3 py-2 text-xs text-warm-red">
        {loadError ? `Could not load keywords: ${loadError.message}` : saveMutation.error?.message || topPicksMutation.error?.message || bulkSaveMutation.error?.message || bulkDeleteMutation.error?.message || copyError}
        {loadError && <Button size="xs" variant="secondary" className="ml-2" onClick={() => void refetch()}>Retry keywords</Button>}
      </div>}
      {copyMessage && <p role="status" className="px-3 py-2 text-xs text-alive-green">{copyMessage}</p>}

      <div className="overflow-x-auto" style={{ zoom: `${zoomPercent}%` }}>
        <table className="w-full text-left text-xs">
          <thead className="border-b border-line text-[10px] font-semibold uppercase tracking-wider text-muted bg-raised/30">
            <tr>
              <th className="px-3 py-2 font-medium">Keyword gap</th>
              <th className="px-2.5 py-2 font-medium">Intent</th>
              <th className="px-2.5 py-2 font-medium">Type</th>
              <th className="px-2.5 py-2 font-medium text-right whitespace-nowrap" title="Competitor pages">Competitors</th>
              <th className="px-3 py-2 font-medium">Sources</th>
              <th className="px-2 py-2 font-medium text-right">Write</th>
              <th className="px-2 py-2 font-medium text-center whitespace-nowrap">Gap Page</th>
              <th className="px-2 py-2 font-medium text-center">Save</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-overlay/5">
            {keywords.length === 0 ? (
              <tr>
                <td className="px-3 py-10 text-center" colSpan={8}>
                  <div className="mx-auto max-w-sm">
                    <Sparkles className="mx-auto h-7 w-7 text-glow-amber/50" />
                    <p className="mt-2 text-xs font-semibold text-ink">{loadError ? 'Keyword results are temporarily unavailable.' : 'No keyword gaps found yet.'}</p>
                    {!loadError && <p className="mt-1 text-[11px] text-muted">Run a Gap Scan on this project and the gaps will appear here.</p>}
                  </div>
                </td>
              </tr>
            ) : (
              keywords.map((keyword) => (
                <tr className="transition-colors hover:bg-overlay/[0.03]" key={keyword.id}>
                  <td className="max-w-[260px] xl:max-w-[340px] px-3 py-2 align-middle">
                    <div className="flex items-center gap-1.5">
                      {isSelectionMode && (
                        <input
                          type="checkbox"
                          className="h-3.5 w-3.5 shrink-0 cursor-pointer rounded border-line bg-raised text-glow-amber focus:ring-glow-amber/50"
                          checked={selectedIds.has(keyword.id)}
                          onChange={(e) => {
                            const newSet = new Set(selectedIds)
                            if (e.target.checked) newSet.add(keyword.id)
                            else newSet.delete(keyword.id)
                            setSelectedIds(newSet)
                          }}
                        />
                      )}
                      <a
                        href={`https://www.google.com/search?q=${encodeURIComponent(keyword.phrase)}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="truncate font-semibold text-ink text-xs transition-colors hover:text-glow-amber hover:underline"
                        title={keyword.phrase}
                      >
                        {keyword.phrase}
                      </a>
                    </div>
                    {keyword.seo_recommendation && (
                      <details className="mt-1 text-[11px] text-muted">
                        <summary className="cursor-pointer text-soft-violet hover:text-ink text-[10px]">Why this keyword?</summary>
                        <p className="mt-1 whitespace-pre-wrap leading-relaxed text-[11px]">{keyword.seo_recommendation}</p>
                      </details>
                    )}
                  </td>
                  <td className="px-2.5 py-2 whitespace-nowrap align-middle">
                    <KeywordIntentBadge keywordPhrase={keyword.phrase} />
                  </td>
                  <td className="px-2.5 py-2 whitespace-nowrap align-middle">{keywordBadge(keyword.keyword_type)}</td>
                  <td className="px-2.5 py-2 text-right font-mono text-xs text-ink whitespace-nowrap align-middle">
                    {getCompetitorCount(keyword)}
                  </td>
                  <td className="px-3 py-2 align-middle">
                    <div className="flex max-w-[220px] flex-wrap items-center gap-1">
                      {sourceDomains(keyword).slice(0, 2).map((source) => (
                        <a
                          className={`inline-flex max-w-[120px] items-center truncate rounded border px-1.5 py-0.5 text-[10px] font-medium transition-colors ${
                            source.sourceType === 'own'
                              ? 'border-line bg-overlay/5 text-muted hover:text-ink'
                              : 'border-soft-violet/30 bg-soft-violet/10 text-soft-violet hover:text-ink'
                          }`}
                          href={source.href}
                          key={source.label}
                          rel="noopener noreferrer"
                          target="_blank"
                          title={source.href}
                        >
                          {source.label}
                        </a>
                      ))}
                      {sourceDomains(keyword).length > 2 && (
                        <span
                          className="inline-flex rounded border border-line bg-overlay/5 px-1 py-0.5 text-[9px] font-medium text-muted"
                          title={sourceDomains(keyword).slice(2).map(s => s.label).join(', ')}
                        >
                          +{sourceDomains(keyword).length - 2}
                        </span>
                      )}
                      <div className="flex items-center gap-0.5 ml-0.5">
                        {keywordSources(keyword).slice(0, 3).map((source) => (
                          <a
                            aria-label={source.url}
                            className="inline-flex h-5 w-5 items-center justify-center rounded border border-line bg-raised text-muted transition-colors hover:border-glow-amber/50 hover:text-glow-amber"
                            href={source.url}
                            key={source.url}
                            rel="noopener noreferrer"
                            target="_blank"
                            title={source.url}
                          >
                            <ExternalLink className="h-2.5 w-2.5" />
                          </a>
                        ))}
                      </div>
                    </div>
                  </td>
                  <td className="px-2 py-2 text-right whitespace-nowrap align-middle">
                    <Button
                      disabled={articleMutation.isPending}
                      onClick={() => articleMutation.mutate(keyword.id)}
                      size="xs"
                      variant="secondary"
                      className="h-6 px-2 text-[11px] gap-1"
                    >
                      <FilePenLine className="h-3 w-3" />
                      {articleMutation.isPending && writingKeywordId === keyword.id ? 'Writing…' : 'Write'}
                    </Button>
                  </td>
                  <td className="px-2 py-2 text-center whitespace-nowrap align-middle">
                    <Button
                      onClick={() => navigate(`/gap-page-prompts?keyword=${encodeURIComponent(keyword.phrase)}`)}
                      size="xs"
                      variant="secondary"
                      className="h-6 w-6 p-0 inline-flex items-center justify-center rounded-lg"
                      title="Generate Gap Page prompt"
                    >
                      <Sparkles className="h-3 w-3" />
                    </Button>
                  </td>
                  <td className="px-2 py-2 text-center whitespace-nowrap align-middle">
                    <Button
                      disabled={saveMutation.isPending}
                      onClick={() => saveMutation.mutate(keyword.id)}
                      size="xs"
                      variant="ghost"
                      className="h-6 w-6 p-0 inline-flex items-center justify-center rounded-lg"
                      title="Save to Keyword Bank"
                    >
                      <BookmarkPlus className="h-3.5 w-3.5" />
                    </Button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {data && data.pages > 1 && (
        <div className="flex flex-col gap-2 border-t border-line p-3 sm:flex-row sm:items-center sm:justify-between text-xs">
          <p className="text-xs text-muted">
            Page {page} of {data.pages} · {data.total.toLocaleString()} keywords
          </p>
          <div className="flex gap-1.5">
            <Button disabled={page === 1} onClick={() => { setSelectedIds(new Set()); setPage((current) => current - 1) }} size="xs" variant="secondary">
              <ChevronLeft className="h-3.5 w-3.5" />
              Previous
            </Button>
            <Button disabled={page === data.pages} onClick={() => { setSelectedIds(new Set()); setPage((current) => current + 1) }} size="xs" variant="secondary">
              Next
              <ChevronRight className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      )}
    </Card>
  )
}
