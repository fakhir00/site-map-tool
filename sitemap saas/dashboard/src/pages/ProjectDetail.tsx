import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ArrowLeft, ExternalLink, FileText, Globe2, Pause, Play, RefreshCw, Timer } from 'lucide-react'
import { api, type Project, type ProjectSource, type ProjectStats, type ScanJob, type ScanProgress, type UrlItem } from '../lib/api'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { KeywordsTable } from '../components/KeywordsTable'

function statusBadge(status: Project['status'] | string) {
  if (status === 'complete') return <Badge variant="teal">Complete</Badge>
  if (status === 'running') return <Badge variant="indigo">Running</Badge>
  if (status === 'paused') return <Badge variant="amber">Paused</Badge>
  if (status === 'error') return <Badge variant="red">Error</Badge>
  if (status === 'scraped') return <Badge variant="teal">Analyzed</Badge>
  if (status === 'failed') return <Badge variant="red">Failed</Badge>
  return <Badge variant="slate">Pending</Badge>
}

function shortDate(value: string | null) {
  if (!value) return 'Not scanned'
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function displayHost(value: string) {
  try {
    const withScheme = value.startsWith('http://') || value.startsWith('https://') ? value : `https://${value}`
    return new URL(withScheme).hostname.replace(/^www\./, '')
  } catch {
    return value.replace(/^https?:\/\//, '')
  }
}

export function ProjectDetail() {
  const { projectId = '' } = useParams<{ projectId: string }>()
  const queryClient = useQueryClient()

  const invalidateProject = () => {
    queryClient.invalidateQueries({ queryKey: ['projects'] })
    queryClient.invalidateQueries({ queryKey: ['project', projectId] })
    queryClient.invalidateQueries({ queryKey: ['project-stats', projectId] })
    queryClient.invalidateQueries({ queryKey: ['scan-status', projectId] })
    queryClient.invalidateQueries({ queryKey: ['scan-jobs', projectId] })
    queryClient.invalidateQueries({ queryKey: ['project-urls', projectId] })
    queryClient.invalidateQueries({ queryKey: ['project-sources', projectId] })
    queryClient.invalidateQueries({ queryKey: ['keywords'] })
  }

  const { data: project, isLoading: loadingProject } = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => api.get<Project>(`/projects/${projectId}`),
    enabled: Boolean(projectId),
    refetchInterval: 5000,
  })

  const { data: stats } = useQuery({
    queryKey: ['project-stats', projectId],
    queryFn: () => api.get<ProjectStats>(`/projects/${projectId}/stats`),
    enabled: Boolean(projectId),
    refetchInterval: 5000,
  })

  const { data: scanStatus } = useQuery({
    queryKey: ['scan-status', projectId],
    queryFn: () => api.get<ScanProgress>(`/projects/${projectId}/scan/status`),
    enabled: Boolean(projectId),
    refetchInterval: 3000,
  })

  const { data: jobs = [] } = useQuery({
    queryKey: ['scan-jobs', projectId],
    queryFn: () => api.get<ScanJob[]>(`/projects/${projectId}/scan/jobs`),
    enabled: Boolean(projectId),
    refetchInterval: 5000,
  })

  const { data: urls = [] } = useQuery({
    queryKey: ['project-urls', projectId],
    queryFn: () => api.get<UrlItem[]>(`/projects/${projectId}/urls?page_size=8`),
    enabled: Boolean(projectId),
    refetchInterval: 7000,
  })

  const { data: sources = [] } = useQuery({
    queryKey: ['project-sources', projectId],
    queryFn: () => api.get<ProjectSource[]>(`/projects/${projectId}/sources`),
    enabled: Boolean(projectId),
    refetchInterval: 7000,
  })

  const startScanMutation = useMutation({
    mutationFn: () => api.post<ScanJob>(`/projects/${projectId}/scan/start`),
    onSuccess: invalidateProject,
  })

  const pauseScanMutation = useMutation({
    mutationFn: () => api.post<{ message: string }>(`/projects/${projectId}/scan/pause`),
    onSuccess: invalidateProject,
  })

  const resumeScanMutation = useMutation({
    mutationFn: () => api.post<ScanJob>(`/projects/${projectId}/scan/resume`),
    onSuccess: invalidateProject,
  })

  if (loadingProject && !project) {
    return <div className="h-96 animate-pulse rounded-lg border border-slate-200 bg-white" />
  }

  if (!project) {
    return (
      <Card>
        <p className="font-semibold text-slate-950">Project not found</p>
        <Link className="mt-3 inline-flex items-center gap-2 text-sm font-semibold text-cyan-800" to="/">
          <ArrowLeft className="h-4 w-4" />
          Back to projects
        </Link>
      </Card>
    )
  }

  const status = scanStatus?.status || project.status
  const isRunning = status === 'running'
  const isPaused = status === 'paused'
  const percent = scanStatus?.percent ?? 0
  const latestJobError = jobs.find((job) => job.error_message)?.error_message
  const actionError = startScanMutation.error || pauseScanMutation.error || resumeScanMutation.error
  const keyword = project.target_keywords?.[0]

  return (
    <div className="space-y-6">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <Link className="mb-3 inline-flex items-center gap-2 text-sm font-semibold text-slate-500 hover:text-slate-950" to="/">
            <ArrowLeft className="h-4 w-4" />
            Projects
          </Link>
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="text-2xl font-bold text-slate-950">{project.name}</h2>
            {statusBadge(status)}
          </div>
          <a className="mt-2 inline-flex items-center gap-2 text-sm text-slate-500 hover:text-slate-950" href={project.domain} rel="noopener noreferrer" target="_blank">
            <Globe2 className="h-4 w-4" />
            {displayHost(project.domain)}
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
          {keyword && <p className="mt-2 text-sm font-medium text-slate-700">Primary keyword: {keyword}</p>}
        </div>

        <div className="flex flex-wrap gap-2">
          {!isRunning && !isPaused && (
            <Button disabled={startScanMutation.isPending} onClick={() => startScanMutation.mutate()}>
              <Play className="h-4 w-4" />
              {project.total_keywords ? 'Run again' : 'Find gaps'}
            </Button>
          )}
          {isRunning && (
            <Button disabled={pauseScanMutation.isPending} onClick={() => pauseScanMutation.mutate()} variant="secondary">
              <Pause className="h-4 w-4" />
              Pause
            </Button>
          )}
          {isPaused && (
            <Button disabled={resumeScanMutation.isPending} onClick={() => resumeScanMutation.mutate()}>
              <Play className="h-4 w-4" />
              Resume
            </Button>
          )}
        </div>
      </section>

      {actionError && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{actionError.message}</div>
      )}

      {(isRunning || isPaused || percent > 0) && (
        <Card>
          <div className="flex flex-col gap-4 md:flex-row md:items-center">
            <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-indigo-50 text-indigo-700">
              <RefreshCw className={`h-5 w-5 ${isRunning ? 'animate-spin' : ''}`} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="mb-2 flex items-center justify-between gap-3">
                <p className="font-semibold text-slate-950">{isPaused ? 'Scan paused' : status === 'complete' ? 'Latest scan complete' : 'Scan in progress'}</p>
                <span className="text-sm font-semibold text-indigo-700">{percent}%</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                <div className="h-full rounded-full bg-indigo-600 transition-all" style={{ width: `${Math.min(percent, 100)}%` }} />
              </div>
              <p className="mt-2 truncate text-sm text-slate-500">{scanStatus?.current_url || 'Finding top Google competitors and crawling sitemaps'}</p>
            </div>
            <div className="grid grid-cols-3 gap-4 text-right text-sm">
              <div>
                <p className="font-semibold text-slate-950">{scanStatus?.urls_processed || 0}</p>
                <p className="text-slate-500">Analyzed</p>
              </div>
              <div>
                <p className="font-semibold text-slate-950">{scanStatus?.urls_failed || 0}</p>
                <p className="text-slate-500">Failed</p>
              </div>
              <div>
                <p className="font-semibold text-slate-950">{scanStatus?.urls_found || 0}</p>
                <p className="text-slate-500">Found</p>
              </div>
            </div>
          </div>
        </Card>
      )}

      {latestJobError && (
        <div className="flex items-start gap-3 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          {latestJobError}
        </div>
      )}

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Card>
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-slate-500">URLs found</p>
            <FileText className="h-4 w-4 text-cyan-800" />
          </div>
          <p className="mt-3 text-3xl font-bold">{stats?.total_urls.toLocaleString() || 0}</p>
        </Card>
        <Card>
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-slate-500">Analyzed</p>
            <RefreshCw className="h-4 w-4 text-indigo-700" />
          </div>
          <p className="mt-3 text-3xl font-bold">{stats?.scraped_urls.toLocaleString() || 0}</p>
        </Card>
        <Card>
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-slate-500">Keyword gaps</p>
            <Globe2 className="h-4 w-4 text-emerald-700" />
          </div>
          <p className="mt-3 text-3xl font-bold">{stats?.total_keywords.toLocaleString() || 0}</p>
        </Card>
        <Card>
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-slate-500">Last scanned</p>
            <Timer className="h-4 w-4 text-amber-700" />
          </div>
          <p className="mt-3 text-xl font-bold">{shortDate(project.last_scanned_at)}</p>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <Card className="p-0">
          <div className="border-b border-slate-200 px-5 py-4">
            <h3 className="font-semibold text-slate-950">Sitemap URLs</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-5 py-3 font-semibold">URL</th>
                  <th className="px-5 py-3 font-semibold">Source</th>
                  <th className="px-5 py-3 font-semibold">Status</th>
                  <th className="px-5 py-3 font-semibold text-right">Words</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {urls.length === 0 ? (
                  <tr>
                    <td className="px-5 py-8 text-center text-slate-500" colSpan={4}>
                      No URLs have been queued yet.
                    </td>
                  </tr>
                ) : (
                  urls.map((url) => (
                    <tr className="hover:bg-slate-50" key={url.id}>
                      <td className="max-w-[420px] px-5 py-3">
                        <a className="block truncate font-medium text-slate-800 hover:text-cyan-800" href={url.url} rel="noopener noreferrer" target="_blank">
                          {url.h1 || url.url}
                        </a>
                        <p className="truncate text-xs text-slate-500">{url.url}</p>
                      </td>
                      <td className="px-5 py-3">
                        <Badge variant={url.source_type === 'own' ? 'slate' : 'indigo'}>
                          {url.source_type === 'own' ? 'Your site' : displayHost(url.source_domain || url.url)}
                        </Badge>
                      </td>
                      <td className="px-5 py-3">{statusBadge(url.status)}</td>
                      <td className="px-5 py-3 text-right font-mono text-slate-700">{url.word_count?.toLocaleString() || '-'}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Card>

        <div className="space-y-4">
          <Card className="p-0">
            <div className="border-b border-slate-200 px-5 py-4">
              <h3 className="font-semibold text-slate-950">Crawled sources</h3>
            </div>
            <div className="divide-y divide-slate-100">
              {sources.length === 0 ? (
                <p className="px-5 py-8 text-sm text-slate-500">No sources have been queued yet.</p>
              ) : (
                sources.map((source) => {
                  const href = source.source_domain || project.domain
                  const sourceLabel = source.source_type === 'own' ? 'Your site' : source.source_type === 'ai' ? 'AI' : 'Competitor'
                  return (
                    <div className="flex items-center justify-between gap-4 px-5 py-4" key={`${source.source_type}-${source.source_domain || 'unknown'}`}>
                      <div className="min-w-0">
                        <a className="flex items-center gap-2 truncate text-sm font-semibold text-slate-950 hover:text-cyan-800" href={href} rel="noopener noreferrer" target="_blank">
                          {displayHost(href)}
                          <ExternalLink className="h-3.5 w-3.5 shrink-0" />
                        </a>
                        <p className="mt-1 text-xs text-slate-500">
                          {source.scraped_urls.toLocaleString()} analyzed / {source.urls_found.toLocaleString()} found
                        </p>
                      </div>
                      <Badge variant={source.source_type === 'own' ? 'slate' : 'indigo'}>
                        {sourceLabel}
                      </Badge>
                    </div>
                  )
                })
              )}
            </div>
          </Card>

          <Card className="p-0">
            <div className="border-b border-slate-200 px-5 py-4">
              <h3 className="font-semibold text-slate-950">Scan history</h3>
            </div>
            <div className="divide-y divide-slate-100">
              {jobs.length === 0 ? (
                <p className="px-5 py-8 text-sm text-slate-500">No scan jobs yet.</p>
              ) : (
                jobs.slice(0, 6).map((job) => (
                  <div className="flex items-center justify-between gap-4 px-5 py-4" key={job.id}>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-slate-950">{job.id}</p>
                      <p className="text-xs text-slate-500">{shortDate(job.created_at)}</p>
                    </div>
                    {statusBadge(job.status)}
                  </div>
                ))
              )}
            </div>
          </Card>
        </div>
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-xl font-bold text-slate-950">Keyword gaps</h3>
        </div>
        <KeywordsTable projectId={projectId} />
      </section>
    </div>
  )
}
