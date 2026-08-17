import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BookmarkPlus, ChevronLeft, ChevronRight, Download, ExternalLink, FilePenLine, Search, Sparkles, Network } from 'lucide-react'
import { api, type Keyword, type KeywordListResponse } from '../lib/api'
import { Badge } from './ui/Badge'
import { Button } from './ui/Button'
import { Card } from './ui/Card'
import { Input } from './ui/Input'
import { HubSpokeView } from './HubSpokeView'

function keywordBadge(type: Keyword['keyword_type']) {
  if (type === 'top-pick') return <Badge className="bg-amber-100 text-amber-800 border-amber-300 font-bold px-2 py-0.5" variant="amber"><Sparkles className="mr-1 inline-block h-3 w-3" /> Top Pick</Badge>
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
  const byLabel = new Map<string, { href: string; label: string; sourceType: 'own' | 'competitor' | 'ai' }>()
  keywordSources(keyword).forEach((source) => {
    const href = source.source_domain || source.url
    const label = displayHost(href)
    if (!byLabel.has(label)) {
      byLabel.set(label, { href, label, sourceType: source.source_type })
    }
  })
  return Array.from(byLabel.values())
}

function KeywordIntentBadge({ keywordPhrase }: { keywordPhrase: string }) {
  const [intent, setIntent] = useState<string | null>(null)
  
  const mutation = useMutation({
    mutationFn: () => api.post<{ intent: string, competitors: string[] }>('/website-prompts/analyze-intent', { keyword: keywordPhrase, short_mode: true }),
    onSuccess: (data: { intent: string, competitors: string[] }) => {
      setIntent(data.intent)
    }
  })

  if (intent) {
    return <span className="inline-flex items-center rounded-md bg-purple-50 px-2 py-1 text-xs font-medium text-purple-700 ring-1 ring-inset ring-purple-700/10 dark:bg-purple-900/30 dark:text-purple-300 dark:ring-purple-500/30 truncate max-w-[150px]" title={intent}>{intent}</span>
  }

  return (
    <Button 
      variant="secondary" 
      size="sm" 
      className="h-6 text-[10px] px-2 py-0"
      disabled={mutation.isPending}
      onClick={() => mutation.mutate()}
    >
      {mutation.isPending ? '...' : 'Intent'}
    </Button>
  )
}

export function KeywordsTable({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [type, setType] = useState('')
  const [exportError, setExportError] = useState('')
  const [articleError, setArticleError] = useState('')
  const [writingKeywordId, setWritingKeywordId] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['keywords', projectId, page, search, type],
    queryFn: () => {
      const params = new URLSearchParams({
        page: page.toString(),
        page_size: '20',
      })
      if (search) params.append('search', search)
      if (type) params.append('keyword_type', type)

      return api.get<KeywordListResponse>(`/projects/${projectId}/keywords?${params}`)
    },
    enabled: Boolean(projectId),
    refetchInterval: 7000,
  })

  const saveMutation = useMutation({
    mutationFn: (keywordId: string) => api.post<{ message: string }>(`/projects/${projectId}/keywords/${keywordId}/save`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['keyword-bank'] })
    },
  })

  const topPicksMutation = useMutation({
    mutationFn: () => api.post(`/projects/${projectId}/keywords/top-picks`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['keywords', projectId] })
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })

  const [isSelectionMode, setIsSelectionMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [isHubSpokeMode, setIsHubSpokeMode] = useState(false)

  const bulkSaveMutation = useMutation({
    mutationFn: ({ tag }: { tag: string }) => 
      api.post(`/projects/${projectId}/keywords/bulk-save`, { 
        keyword_ids: Array.from(selectedIds), 
        notes: tag 
      }),
    onSuccess: (data: any) => {
      queryClient.invalidateQueries({ queryKey: ['keyword-bank'] })
      setIsSelectionMode(false)
      setSelectedIds(new Set())
      alert(data.message)
    }
  })

  const bulkDeleteMutation = useMutation({
    mutationFn: () => 
      api.post(`/projects/${projectId}/keywords/bulk-delete`, { 
        keyword_ids: Array.from(selectedIds)
      }),
    onSuccess: (data: any) => {
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
      const blob = await api.get<Blob>(`/projects/${projectId}/keywords/export`)
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
    return <div className="h-96 animate-pulse rounded-lg border border-slate-200 bg-white" />
  }

  const keywords = data?.items || []

  return (
    <Card className="p-0">
      <div className="flex flex-col gap-3 border-b border-slate-200 dark:border-slate-800 p-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative w-full sm:w-72">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400 dark:text-slate-500" />
            <Input
              className="pl-9"
              onChange={(event) => {
                setSearch(event.target.value)
                setPage(1)
              }}
              placeholder="Search gaps"
              value={search}
            />
          </div>

          <select
            className="h-10 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-950 focus:outline-none focus:ring-2 focus:ring-cyan-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-50 dark:focus:ring-cyan-600"
            onChange={(event) => {
              setType(event.target.value)
              setPage(1)
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
                onClick={() => {
                  if (selectedIds.size === keywords.length) {
                    setSelectedIds(new Set())
                  } else {
                    setSelectedIds(new Set(keywords.map(k => k.id)))
                  }
                }}
              >
                {selectedIds.size === keywords.length ? 'Deselect All' : 'Select All'}
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={selectedIds.size === 0 || bulkSaveMutation.isPending}
                onClick={() => bulkSaveMutation.mutate({ tag: '#tool' })}
              >
                Tool Page
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={selectedIds.size === 0 || bulkSaveMutation.isPending}
                onClick={() => bulkSaveMutation.mutate({ tag: '#blog' })}
              >
                Blog
              </Button>
              <Button
                variant="danger"
                size="sm"
                disabled={selectedIds.size === 0 || bulkDeleteMutation.isPending}
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
            <Button variant="secondary" size="sm" onClick={() => setIsSelectionMode(true)}>
              Select
            </Button>
          )}

          <Button 
            onClick={() => setIsHubSpokeMode(!isHubSpokeMode)} 
            size="sm" 
            variant="secondary"
            className={isHubSpokeMode ? "bg-cyan-100 text-cyan-800 border-cyan-300 dark:bg-cyan-900/40 dark:text-cyan-300 dark:border-cyan-700" : ""}
          >
            <Network className="h-4 w-4" />
            {isHubSpokeMode ? 'Table View' : 'Hub Spoke'}
          </Button>
          <Button 
            disabled={topPicksMutation.isPending} 
            onClick={() => topPicksMutation.mutate()} 
            size="sm" 
            variant="secondary"
            className="text-amber-700 bg-amber-50 hover:bg-amber-100 border-amber-200 dark:text-amber-400 dark:bg-amber-900/30 dark:hover:bg-amber-900/50 dark:border-amber-800/50"
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

      {exportError && <div className="border-b border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700 dark:border-rose-800/50 dark:bg-rose-900/30 dark:text-rose-300">{exportError}</div>}
      {articleError && <div className="border-b border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700 dark:border-rose-800/50 dark:bg-rose-900/30 dark:text-rose-300">{articleError}</div>}

      {isHubSpokeMode ? (
        <HubSpokeView projectId={projectId} />
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase text-slate-500 dark:border-slate-800 dark:bg-slate-900/50 dark:text-slate-400">
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
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800/50">
                {keywords.length === 0 ? (
                  <tr>
                    <td className="px-5 py-10 text-center text-slate-500 dark:text-slate-400" colSpan={7}>
                      No keyword gaps found yet.
                    </td>
                  </tr>
                ) : (
                  keywords.map((keyword) => (
                    <tr className="hover:bg-slate-50 dark:hover:bg-slate-800/50" key={keyword.id}>
                      <td className="max-w-[360px] px-5 py-4">
                        <div className="flex items-center gap-2">
                          {isSelectionMode && (
                            <input 
                              type="checkbox"
                              className="h-4 w-4 rounded border-slate-300 text-cyan-600 focus:ring-cyan-600 cursor-pointer flex-shrink-0 dark:border-slate-700 dark:bg-slate-900"
                              checked={selectedIds.has(keyword.id)}
                              onChange={(e) => {
                                const newSet = new Set(selectedIds)
                                if (e.target.checked) newSet.add(keyword.id)
                                else newSet.delete(keyword.id)
                                setSelectedIds(newSet)
                              }}
                            />
                          )}
                          <a href={`https://www.google.com/search?q=${encodeURIComponent(keyword.phrase)}`} target="_blank" rel="noopener noreferrer" className="truncate font-semibold text-slate-950 hover:text-cyan-700 hover:underline dark:text-slate-50 dark:hover:text-cyan-400">
                            {keyword.phrase}
                          </a>
                        </div>
                      </td>
                      <td className="px-5 py-4">
                        <KeywordIntentBadge keywordPhrase={keyword.phrase} />
                      </td>
                      <td className="px-5 py-4">{keywordBadge(keyword.keyword_type)}</td>
                      <td className="px-5 py-4 text-right font-mono text-slate-700 dark:text-slate-300">{keyword.frequency}</td>
                      <td className="px-5 py-4">
                        <div className="flex max-w-[360px] flex-wrap gap-1.5">
                          {sourceDomains(keyword).slice(0, 4).map((source) => (
                            <a
                              className={`inline-flex max-w-[160px] items-center truncate rounded-md border px-2 py-1 text-xs font-medium ${
                                source.sourceType === 'own'
                                  ? 'border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300'
                                  : 'border-indigo-200 bg-indigo-50 text-indigo-700 dark:border-indigo-800/50 dark:bg-indigo-900/30 dark:text-indigo-300'
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
                          {sourceDomains(keyword).length > 4 && (
                            <span className="inline-flex rounded-md border border-slate-200 bg-white px-2 py-1 text-xs font-medium text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400">
                              +{sourceDomains(keyword).length - 4}
                            </span>
                          )}
                        </div>
                          <div className="mt-2 flex gap-1">
                            {keywordSources(keyword).slice(0, 5).map((source) => (
                            <a
                              aria-label={source.url}
                              className="inline-flex h-7 w-7 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 hover:border-cyan-300 hover:text-cyan-800 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400 dark:hover:border-cyan-700 dark:hover:text-cyan-400"
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
                          onClick={() => navigate(`/gap-page-prompts?keyword=${encodeURIComponent(keyword.phrase)}`)}
                          size="sm"
                          variant="secondary"
                        >
                          <Sparkles className="h-4 w-4" />
                        </Button>
                      </td>
                      <td className="px-5 py-4 text-right">
                        <Button disabled={saveMutation.isPending} onClick={() => saveMutation.mutate(keyword.id)} size="sm" variant="ghost">
                          <BookmarkPlus className="h-4 w-4" />
                        </Button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {data && data.pages > 1 && (
            <div className="flex flex-col gap-3 border-t border-slate-200 dark:border-slate-800 p-4 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-sm text-slate-500 dark:text-slate-400">
                Page {page} of {data.pages} · {data.total.toLocaleString()} keywords
              </p>
              <div className="flex gap-2">
                <Button disabled={page === 1} onClick={() => setPage((current) => current - 1)} size="sm" variant="secondary">
                  <ChevronLeft className="h-4 w-4" />
                  Previous
                </Button>
                <Button disabled={page === data.pages} onClick={() => setPage((current) => current + 1)} size="sm" variant="secondary">
                  Next
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </Card>
  )
}
