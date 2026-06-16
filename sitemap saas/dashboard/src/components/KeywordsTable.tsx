import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BookmarkPlus, ChevronLeft, ChevronRight, Download, ExternalLink, Search, Sparkles } from 'lucide-react'
import { api, type Keyword, type KeywordListResponse } from '../lib/api'
import { Badge } from './ui/Badge'
import { Button } from './ui/Button'
import { Card } from './ui/Card'
import { Input } from './ui/Input'

function keywordBadge(type: Keyword['keyword_type']) {
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

export function KeywordsTable({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [type, setType] = useState('')
  const [exportError, setExportError] = useState('')

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

  const generateMutation = useMutation({
    mutationFn: () => api.post<{ message: string, generated: number }>(`/projects/${projectId}/keywords/generate`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['keywords', projectId] })
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
      <div className="flex flex-col gap-3 border-b border-slate-200 p-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative w-full sm:w-72">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
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
            className="h-10 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-950 focus:outline-none focus:ring-2 focus:ring-cyan-500"
            onChange={(event) => {
              setType(event.target.value)
              setPage(1)
            }}
            value={type}
          >
            <option value="">All types</option>
            <option value="primary">Primary</option>
            <option value="lsi">LSI</option>
            <option value="long-tail">Long-tail</option>
            <option value="entity">Entity</option>
            <option value="heading">Heading</option>
          </select>
        </div>

        <div className="flex items-center gap-2">
          <Button 
            disabled={generateMutation.isPending} 
            onClick={() => generateMutation.mutate()} 
            size="sm" 
            variant="secondary"
            className="text-cyan-700 bg-cyan-50 hover:bg-cyan-100 border-cyan-200"
          >
            <Sparkles className="h-4 w-4" />
            {generateMutation.isPending ? 'Generating...' : 'Generate AI Keywords'}
          </Button>
          <Button onClick={handleExport} size="sm" variant="secondary">
            <Download className="h-4 w-4" />
            Export CSV
          </Button>
        </div>
      </div>

      {exportError && <div className="border-b border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">{exportError}</div>}

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-5 py-3 font-semibold">Keyword gap</th>
              <th className="px-5 py-3 font-semibold">Type</th>
              <th className="px-5 py-3 text-right font-semibold">Competitor pages</th>
              <th className="px-5 py-3 font-semibold">Sources</th>
              <th className="px-5 py-3 text-right font-semibold">Save</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {keywords.length === 0 ? (
              <tr>
                <td className="px-5 py-10 text-center text-slate-500" colSpan={5}>
                  No keyword gaps found yet.
                </td>
              </tr>
            ) : (
              keywords.map((keyword) => (
                <tr className="hover:bg-slate-50" key={keyword.id}>
                  <td className="max-w-[360px] px-5 py-4">
                    <p className="truncate font-semibold text-slate-950">{keyword.phrase}</p>
                  </td>
                  <td className="px-5 py-4">{keywordBadge(keyword.keyword_type)}</td>
                  <td className="px-5 py-4 text-right font-mono text-slate-700">{keyword.frequency}</td>
                  <td className="px-5 py-4">
                    <div className="flex max-w-[360px] flex-wrap gap-1.5">
                      {sourceDomains(keyword).slice(0, 4).map((source) => (
                        <a
                          className={`inline-flex max-w-[160px] items-center truncate rounded-md border px-2 py-1 text-xs font-medium ${
                            source.sourceType === 'own'
                              ? 'border-slate-200 bg-slate-50 text-slate-700'
                              : 'border-indigo-200 bg-indigo-50 text-indigo-700'
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
                        <span className="inline-flex rounded-md border border-slate-200 bg-white px-2 py-1 text-xs font-medium text-slate-500">
                          +{sourceDomains(keyword).length - 4}
                        </span>
                      )}
                    </div>
                    <div className="mt-2 flex gap-1">
                      {keywordSources(keyword).slice(0, 5).map((source) => (
                        <a
                          aria-label={source.url}
                          className="inline-flex h-7 w-7 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 hover:border-cyan-300 hover:text-cyan-800"
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
        <div className="flex flex-col gap-3 border-t border-slate-200 p-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-slate-500">
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
    </Card>
  )
}
