import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BookmarkPlus, ChevronLeft, ChevronRight, Download, ExternalLink, FilePenLine, Network, Search, Sparkles } from 'lucide-react'
import { api, type Keyword, type KeywordListResponse } from '../lib/api'
import { Badge } from './ui/Badge'
import { Button } from './ui/Button'
import { Card } from './ui/Card'
import { Input } from './ui/Input'

function keywordBadge(type: Keyword['keyword_type']) {
  if (type === 'top-pick') return <Badge variant="amber"><Sparkles className="mr-1 inline-block h-3 w-3" /> Top Pick</Badge>
  if (type === 'primary') return <Badge variant="teal">Primary</Badge>
  if (type === 'lsi') return <Badge variant="indigo">LSI</Badge>
  if (type === 'entity') return <Badge variant="amber">Entity</Badge>
  if (type === 'long-tail') return <Badge variant="cyan">Long-tail</Badge>
  return <Badge variant="slate">Heading</Badge>
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

function sourceChipClasses(sourceType: 'own' | 'competitor' | 'ai' | 'provider') {
  // Locked brand mapping: yours/existing -> Site Sky, competitor sitemap gaps -> Signal Amber,
  // AI-recommended -> indigo/violet, Google Autocomplete (provider) -> Built Green
  switch (sourceType) {
    case 'own':
      return 'border-site-sky/30 bg-site-sky/10 text-site-sky'
    case 'competitor':
      return 'border-signal-amber/30 bg-signal-amber/10 text-signal-amber'
    case 'ai':
      return 'border-indigo-400/30 bg-indigo-500/10 text-indigo-300'
    case 'provider':
      return 'border-built-green/30 bg-built-green/10 text-built-green'
  }
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
    return <span className="inline-flex max-w-[150px] truncate items-center rounded-md border border-site-sky/30 bg-site-sky/10 px-2 py-1 text-xs font-medium text-site-sky" title={intent}>{intent}</span>
  }

  return (
    <div><Button
      variant="secondary" 
      size="sm" 
      className="h-6 text-[10px] px-2 py-0"
      disabled={mutation.isPending}
      onClick={() => mutation.mutate()}
    >
      {mutation.isPending ? '...' : 'Intent'}
    </Button>{mutation.isError && <p role="alert" className="mt-1 max-w-48 text-xs text-signal-red">{mutation.error.message}</p>}</div>
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
    return <div className="h-96 animate-pulse rounded-xl border border-line bg-panel/60" />
  }

  const keywords = data?.items || []

  return (
    <Card className="p-0">
      <div className="flex flex-col gap-3 border-b border-line p-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative w-full sm:w-72">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <Input
              className="pl-9"
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
            className="h-10 rounded-lg border border-line bg-raised px-3 text-sm text-text focus:outline-none focus:ring-2 focus:ring-site-sky/40"
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

        <div className="flex flex-wrap items-center gap-2">
          {isSelectionMode ? (
            <>
              <Button
                variant="secondary"
                size="sm"
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
                size="sm"
                disabled={selectedPageIds.length === 0 || bulkSaveMutation.isPending}
                onClick={() => bulkSaveMutation.mutate({ tag: '#tool' })}
              >
                Tool Page
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={selectedPageIds.length === 0 || bulkSaveMutation.isPending}
                onClick={() => bulkSaveMutation.mutate({ tag: '#blog' })}
              >
                Blog
              </Button>
              <Button
                variant="secondary"
                size="sm"
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
                size="sm"
                disabled={selectedPageIds.length === 0 || bulkDeleteMutation.isPending}
                onClick={() => {
                  if (confirm('Are you sure you want to permanently delete these keywords?')) {
                    bulkDeleteMutation.mutate()
                  }
                }}
              >
                Delete
              </Button>
              <Button variant="secondary" size="sm" onClick={() => { setIsSelectionMode(false); setSelectedIds(new Set()) }}>
                Cancel
              </Button>
            </>
          ) : (
            <Button variant="secondary" size="sm" disabled={keywords.length === 0} onClick={() => setIsSelectionMode(true)}>
              Select
            </Button>
          )}

          <Button
            onClick={() => navigate(`/hub-spoke?project_id=${encodeURIComponent(projectId)}`)}
            size="sm"
            variant="secondary"
          >
            <Network className="h-4 w-4" />
            Hub Spoke
          </Button>

          <Button 
            disabled={topPicksMutation.isPending} 
            onClick={() => topPicksMutation.mutate()} 
            size="sm" 
            variant="secondary"
          >
            <Sparkles className="h-4 w-4" />
            {topPicksMutation.isPending ? 'Generating...' : 'Top Picks'}
          </Button>

          <Button onClick={handleExport} size="sm" variant="secondary">
            <Download className="h-4 w-4" />
            Export CSV
          </Button>
        </div>
      </div>

      {exportError && <div className="border-b border-signal-red/30 bg-signal-red/10 px-4 py-2 text-sm text-signal-red">{exportError}</div>}
      {articleError && <div className="border-b border-signal-red/30 bg-signal-red/10 px-4 py-2 text-sm text-signal-red">{articleError}</div>}
      {(loadError || saveMutation.error || topPicksMutation.error || bulkSaveMutation.error || bulkDeleteMutation.error || copyError) && <div role="alert" className="border-b border-signal-red/30 bg-signal-red/10 px-4 py-2 text-sm text-signal-red">
        {loadError ? `Could not load keywords: ${loadError.message}` : saveMutation.error?.message || topPicksMutation.error?.message || bulkSaveMutation.error?.message || bulkDeleteMutation.error?.message || copyError}
        {loadError && <Button size="sm" variant="secondary" className="ml-3" onClick={() => void refetch()}>Retry keywords</Button>}
      </div>}
      {copyMessage && <p role="status" className="px-4 py-2 text-sm text-built-green">{copyMessage}</p>}

      <>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-line bg-panel/60 font-display text-[11px] uppercase tracking-wider text-muted">
                <tr>
                  <th className="px-5 py-3 font-semibold">Keyword gap</th>
                  <th className="px-5 py-3 font-semibold">Intent</th>
                  <th className="px-5 py-3 font-semibold">Type</th>
                  <th className="px-5 py-3 text-right font-semibold">Competitor pages</th>
                  <th className="px-5 py-3 font-semibold">Sources</th>
                  <th className="px-5 py-3 text-right font-semibold">Write</th>
                  <th className="px-5 py-3 text-right font-semibold">Gap Page</th>
                  <th className="px-5 py-3 text-right font-semibold">Save</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line/60">
                {keywords.length === 0 ? (
                  <tr className="bg-panel">
                    <td className="px-5 py-10 text-center text-muted" colSpan={8}>
                      {loadError ? 'Keyword results are temporarily unavailable.' : 'No keyword gaps found yet.'}
                    </td>
                  </tr>
                ) : (
                  keywords.map((keyword) => (
                    <tr className="bg-panel transition-colors hover:bg-raised" key={keyword.id}>
                      <td className="max-w-[360px] px-5 py-4">
                        <div className="flex items-center gap-2">
                          {isSelectionMode && (
                            <input 
                              type="checkbox"
                              className="h-4 w-4 flex-shrink-0 cursor-pointer rounded border-line bg-raised accent-signal-amber"
                              checked={selectedIds.has(keyword.id)}
                              onChange={(e) => {
                                const newSet = new Set(selectedIds)
                                if (e.target.checked) newSet.add(keyword.id)
                                else newSet.delete(keyword.id)
                                setSelectedIds(newSet)
                              }}
                            />
                          )}
                          <a href={`https://www.google.com/search?q=${encodeURIComponent(keyword.phrase)}`} target="_blank" rel="noopener noreferrer" className="truncate font-mono font-semibold text-text hover:text-site-sky hover:underline">
                            {keyword.phrase}
                          </a>
                        </div>
                        {keyword.seo_recommendation && <details className="mt-2 text-xs text-muted">
                          <summary className="cursor-pointer text-site-sky">Why this keyword?</summary>
                          <p className="mt-1 whitespace-pre-wrap">{keyword.seo_recommendation}</p>
                        </details>}
                      </td>
                      <td className="px-5 py-4">
                        <KeywordIntentBadge keywordPhrase={keyword.phrase} />
                      </td>
                      <td className="px-5 py-4">{keywordBadge(keyword.keyword_type)}</td>
                      <td className="px-5 py-4 text-right font-mono text-text">{keyword.competitor_pages ?? keywordSources(keyword).filter(source => source.source_type === 'competitor').length}</td>
                      <td className="px-5 py-4">
                        <div className="flex max-w-[360px] flex-wrap gap-1.5">
                          {sourceDomains(keyword).slice(0, 4).map((source) => (
                            <a
                              className={`inline-flex max-w-[160px] items-center truncate rounded-md border px-2 py-1 text-xs font-medium ${sourceChipClasses(source.sourceType)}`}
                              href={source.href}
                              key={source.label}
                              rel="noopener noreferrer"
                              target="_blank"
                              title={source.href}
                            >
                              {source.label}
                            </a>
                          ))}
                          {sourceDomains(keyword).length > 4 && (
                            <span className="inline-flex rounded-md border border-line bg-raised px-2 py-1 text-xs font-medium text-muted">
                              +{sourceDomains(keyword).length - 4}
                            </span>
                          )}
                        </div>
                          <div className="mt-2 flex gap-1">
                            {keywordSources(keyword).slice(0, 5).map((source) => (
                            <a
                              aria-label={source.url}
                              className="inline-flex h-7 w-7 items-center justify-center rounded-lg border border-line bg-raised text-muted transition-colors hover:border-site-sky/60 hover:text-site-sky"
                              href={source.url}
                              key={source.url}
                              rel="noopener noreferrer"
                              target="_blank"
                              title={source.url}
                            >
                              <ExternalLink className="h-3.5 w-3.5" />
                            </a>
                            ))}
                          </div>
                        </td>
                      <td className="px-5 py-4 text-right">
                        <Button
                          disabled={articleMutation.isPending}
                          onClick={() => articleMutation.mutate(keyword.id)}
                          size="sm"
                          variant="secondary"
                        >
                          <FilePenLine className="h-4 w-4" />
                          {articleMutation.isPending && writingKeywordId === keyword.id ? 'Writing...' : 'Write'}
                        </Button>
                      </td>
                      <td className="px-5 py-4 text-right">
                        <Button
                          aria-label={`Gap page for ${keyword.phrase}`}
                          onClick={() => navigate(`/gap-page-prompts?keyword=${encodeURIComponent(keyword.phrase)}`)}
                          size="sm"
                          variant="secondary"
                        >
                          <Sparkles className="h-4 w-4" />
                          Gap page
                        </Button>
                      </td>
                      <td className="px-5 py-4 text-right">
                        <Button
                          aria-label={`Save ${keyword.phrase}`}
                          disabled={saveMutation.isPending}
                          onClick={() => saveMutation.mutate(keyword.id)}
                          size="sm"
                          variant="ghost"
                        >
                          <BookmarkPlus className="h-4 w-4" />
                          Save
                        </Button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {data && data.pages > 1 && (
            <div className="flex flex-col gap-3 border-t border-line p-4 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-sm text-muted">
                Page {page} of {data.pages} · {data.total.toLocaleString()} keywords
              </p>
              <div className="flex gap-2">
                <Button disabled={page === 1} onClick={() => { setSelectedIds(new Set()); setPage((current) => current - 1) }} size="sm" variant="secondary">
                  <ChevronLeft className="h-4 w-4" />
                  Previous
                </Button>
                <Button disabled={page === data.pages} onClick={() => { setSelectedIds(new Set()); setPage((current) => current + 1) }} size="sm" variant="secondary">
                  Next
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
      </>
    </Card>
  )
}
