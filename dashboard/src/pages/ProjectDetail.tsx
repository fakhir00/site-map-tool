import { lazy, Suspense, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ArrowLeft, ExternalLink, FileText, Globe2, Info, Pause, Play, RefreshCw, Timer, X } from 'lucide-react'
import { api, type Project, type ProjectSource, type ProjectStats, type ScanJob, type ScanProgress } from '../lib/api'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { GeneratedArticlePanel } from '../components/GeneratedArticlePanel'
import { KeywordsTable } from '../components/KeywordsTable'
import { SemanticMetrics } from '../components/SemanticMetrics'
import { LiveSignals } from '../components/LiveSignals'

const CompetitorGraph = lazy(() => import('../components/CompetitorGraph').then((module) => ({ default: module.CompetitorGraph })))

function statusBadge(status: Project['status'] | string) {
  if (status === 'complete') return <Badge variant="green">Complete</Badge>
  if (status === 'running') return <Badge variant="cyan">Scanning</Badge>
  if (status === 'paused') return <Badge variant="amber">Paused</Badge>
  if (status === 'error') return <Badge variant="red">Error</Badge>
  if (status === 'scraped') return <Badge variant="green">Analyzed</Badge>
  if (status === 'discovered') return <Badge variant="slate">URL found</Badge>
  if (status === 'failed') return <Badge variant="red">Failed</Badge>
  return <Badge variant="slate">Pending</Badge>
}

function sourceLegendChip(sourceType: 'competitor' | 'ai' | 'provider', label: string) {
  // Locked brand mapping: competitor sitemap gaps -> Signal Amber,
  // AI-recommended -> indigo, Google Autocomplete (provider) -> Built Green
  const classes =
    sourceType === 'competitor'
      ? 'border-signal-amber/30 bg-signal-amber/10 text-signal-amber'
      : sourceType === 'ai'
        ? 'border-indigo-400/30 bg-indigo-500/10 text-indigo-300'
        : 'border-built-green/30 bg-built-green/10 text-built-green'
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${classes}`}>
      {label}
    </span>
  )
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
  const [dismissedError, setDismissedError] = useState<string | null>(null)

  const invalidateProject = () => {
    queryClient.invalidateQueries({ queryKey: ['projects'] })
    queryClient.invalidateQueries({ queryKey: ['project', projectId] })
    queryClient.invalidateQueries({ queryKey: ['project-stats', projectId] })
    queryClient.invalidateQueries({ queryKey: ['scan-status', projectId] })
    queryClient.invalidateQueries({ queryKey: ['scan-jobs', projectId] })
    queryClient.invalidateQueries({ queryKey: ['project-urls', projectId] })
    queryClient.invalidateQueries({ queryKey: ['project-sources', projectId] })
    queryClient.invalidateQueries({ queryKey: ['keywords'] })
    queryClient.invalidateQueries({ queryKey: ['project-articles', projectId] })
  }

  const { data: project, isLoading: loadingProject } = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => api.get<Project>(`/projects/${projectId}`),
    enabled: Boolean(projectId),
    refetchInterval: (query) => ['pending', 'running'].includes(query.state.data?.status || '') ? 5000 : false,
  })
  const projectIsActive = project?.status === 'pending' || project?.status === 'running'

  const { data: stats } = useQuery({
    queryKey: ['project-stats', projectId],
    queryFn: () => api.get<ProjectStats>(`/projects/${projectId}/stats`),
    enabled: Boolean(projectId),
    refetchInterval: projectIsActive ? 5000 : false,
  })

  const { data: scanStatus } = useQuery({
    queryKey: ['scan-status', projectId],
    queryFn: () => api.get<ScanProgress>(`/projects/${projectId}/scan/status`),
    enabled: Boolean(projectId),
    refetchInterval: projectIsActive ? 3000 : false,
  })

  const { data: jobs = [] } = useQuery({
    queryKey: ['scan-jobs', projectId],
    queryFn: () => api.get<ScanJob[]>(`/projects/${projectId}/scan/jobs`),
    enabled: Boolean(projectId),
    refetchInterval: projectIsActive ? 5000 : false,
  })



  const { data: sources = [] } = useQuery({
    queryKey: ['project-sources', projectId],
    queryFn: () => api.get<ProjectSource[]>(`/projects/${projectId}/sources`),
    enabled: Boolean(projectId),
    refetchInterval: projectIsActive ? 7000 : false,
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
    return <div className="h-96 animate-pulse rounded-2xl border border-line bg-panel" />
  }

  if (!project) {
    return (
      <Card>
        <p className="font-display font-semibold text-text">Project not found</p>
        <Link className="mt-3 inline-flex items-center gap-2 text-sm font-semibold text-site-sky hover:underline" to="/">
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
  const activeJobError = jobs[0]?.error_message
  const visibleJobError = activeJobError
  const latestJobError = visibleJobError && visibleJobError !== dismissedError ? visibleJobError : null
  const isCompletionWarning = status === 'complete' && Boolean(latestJobError)
  const isCompletionNote = isCompletionWarning && latestJobError?.startsWith('Scan completed:')
  const actionError = startScanMutation.error || pauseScanMutation.error || resumeScanMutation.error

  // Signature Gap Scan arithmetic — all numbers from existing queries, never hardcoded.
  // N = total keyword gaps (missing pages). X/Y/Z = pages analyzed per source type
  // from the project-sources query (competitor sitemaps, AI, Google Autocomplete).
  const gapTotal = stats?.total_keywords ?? project.total_keywords ?? 0
  const scrapedByType = (sourceType: ProjectSource['source_type']) =>
    sources.filter((source) => source.source_type === sourceType).reduce((sum, source) => sum + source.scraped_urls, 0)
  const competitorPages = scrapedByType('competitor')
  const aiPages = scrapedByType('ai')
  const providerPages = scrapedByType('provider')

  return (
    <div className="space-y-6">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <Link className="mb-3 inline-flex items-center gap-2 text-sm font-semibold text-muted hover:text-text" to="/">
            <ArrowLeft className="h-4 w-4" />
            Dashboard
          </Link>
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="font-display text-2xl font-bold text-text">{project.name}</h2>
            {statusBadge(status)}
          </div>
          <a className="mt-2 inline-flex items-center gap-2 text-sm text-muted hover:text-text" href={project.domain} rel="noopener noreferrer" target="_blank">
            <Globe2 className="h-4 w-4" />
            {displayHost(project.domain)}
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
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
        <div className="rounded-lg border border-signal-red/30 bg-signal-red/10 px-4 py-3 text-sm text-signal-red">{actionError.message}</div>
      )}

      {(isRunning || isPaused) && (
        <Card>
          <div className="flex flex-col gap-4 md:flex-row md:items-center">
            <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-site-sky/10 text-site-sky">
              <RefreshCw className={`h-5 w-5 ${isRunning ? 'animate-spin' : ''}`} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="mb-2 flex items-center justify-between gap-3">
                <p className="font-display font-semibold text-text">{isPaused ? 'Gap Scan paused' : 'Gap Scan in progress'}</p>
                <span className="font-mono text-sm font-semibold text-site-sky">{percent}%</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-raised">
                <div className="h-full rounded-full bg-site-sky transition-all" style={{ width: `${Math.min(percent, 100)}%` }} />
              </div>
              <p className="mt-2 truncate text-sm text-muted">{scanStatus?.current_url || 'Finding top Google competitors and crawling sitemaps'}</p>
            </div>
            <div className="grid grid-cols-3 gap-4 text-right text-sm">
              <div>
                <p className="font-mono font-semibold text-text">{scanStatus?.urls_processed || 0}</p>
                <p className="text-muted">Analyzed</p>
              </div>
              <div>
                <p className="font-mono font-semibold text-text">{scanStatus?.urls_failed || 0}</p>
                <p className="text-muted">Failed</p>
              </div>
              <div>
                <p className="font-mono font-semibold text-text">{scanStatus?.urls_found || 0}</p>
                <p className="text-muted">Found</p>
              </div>
            </div>
          </div>
        </Card>
      )}

      {latestJobError && (
        <div className={`relative flex items-start gap-3 rounded-lg px-4 py-3 pr-10 text-sm ${isCompletionNote ? 'border border-line bg-raised text-muted' : isCompletionWarning ? 'border border-signal-amber/30 bg-signal-amber/10 text-signal-amber' : 'border border-signal-red/30 bg-signal-red/10 text-signal-red'}`}>
          {isCompletionNote ? <Info className="mt-0.5 h-4 w-4 shrink-0" /> : <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />}
          <p>{latestJobError}</p>
          <button
            type="button"
            aria-label="Dismiss scan message"
            onClick={() => setDismissedError(latestJobError)}
            className="absolute right-3 top-3 text-current opacity-70 hover:opacity-100"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Card>
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-muted">URLs found</p>
            <FileText className="h-4 w-4 text-site-sky" />
          </div>
          <p className="mt-3 font-mono text-3xl font-bold text-text">{stats?.total_urls.toLocaleString() || 0}</p>
        </Card>
        <Card>
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-muted">Analyzed</p>
            <RefreshCw className="h-4 w-4 text-site-sky" />
          </div>
          <p className="mt-3 font-mono text-3xl font-bold text-text">{stats?.scraped_urls.toLocaleString() || 0}</p>
        </Card>
        <Card>
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-muted">Keyword gaps</p>
            <Globe2 className="h-4 w-4 text-signal-amber" />
          </div>
          <p className="mt-3 font-mono text-3xl font-bold text-signal-amber">{stats?.total_keywords.toLocaleString() || 0}</p>
        </Card>
        <Card>
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-muted">Last scanned</p>
            <Timer className="h-4 w-4 text-muted" />
          </div>
          <p className="mt-3 font-mono text-xl font-bold text-text">{shortDate(project.last_scanned_at)}</p>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="flex flex-col gap-4">
          <Suspense fallback={<div className="h-80 animate-pulse rounded-2xl border border-line bg-panel/60" />}>
            <CompetitorGraph sources={sources} isActive={isRunning} />
          </Suspense>
          <SemanticMetrics isActive={isRunning} />
        </div>

        <div className="space-y-4">
          <LiveSignals isActive={isRunning} progress={scanStatus} error={latestJobError} />

          <Card className="p-0 flex flex-col">
            <div className="border-b border-line px-5 py-4 shrink-0">
              <h3 className="font-display font-semibold text-text">Crawled sources</h3>
            </div>
            <div className="divide-y divide-line/60 max-h-[405px] overflow-y-auto">
              {sources.length === 0 ? (
                <p className="px-5 py-8 text-sm text-muted">No sources have been queued yet.</p>
              ) : (
                sources.map((source) => {
                  const isAi = source.source_type === 'ai'
                  const isProvider = source.source_type === 'provider'
                  const href = isAi || isProvider ? undefined : (source.source_domain || project.domain)
                  const label = isAi || isProvider ? (source.source_domain || (isProvider ? 'Keyword provider' : 'AI Recommendations')) : displayHost(href!)
                  const sourceLabel = source.source_type === 'own' ? 'Your site' : isAi ? 'AI' : isProvider ? 'Provider' : 'Competitor'
                  return (
                    <div className="flex items-center justify-between gap-4 px-5 py-4" key={`${source.source_type}-${source.source_domain || 'unknown'}`}>
                      <div className="min-w-0">
                        {href ? (
                          <a className="flex items-center gap-2 truncate text-sm font-semibold text-text hover:text-site-sky" href={href} rel="noopener noreferrer" target="_blank">
                            {label}
                            <ExternalLink className="h-3.5 w-3.5 shrink-0" />
                          </a>
                        ) : (
                          <span className="flex items-center gap-2 truncate text-sm font-semibold text-text">
                            {label}
                          </span>
                        )}
                        <p className="mt-1 font-mono text-xs text-muted">
                          {source.scraped_urls.toLocaleString()} analyzed / {source.urls_found.toLocaleString()} found
                        </p>
                      </div>
                      <Badge variant={source.source_type === 'own' ? 'slate' : source.source_type === 'competitor' ? 'amber' : source.source_type === 'ai' ? 'indigo' : 'green'}>
                        {sourceLabel}
                      </Badge>
                    </div>
                  )
                })
              )}
            </div>
          </Card>

          <Card className="p-0">
            <div className="border-b border-line px-5 py-4">
              <h3 className="font-display font-semibold text-text">Gap Scan history</h3>
            </div>
            <div className="divide-y divide-line/60">
              {jobs.length === 0 ? (
                <p className="px-5 py-8 text-sm text-muted">No Gap Scan jobs yet.</p>
              ) : (
                jobs.slice(0, 6).map((job) => (
                  <div className="flex items-center justify-between gap-4 px-5 py-4" key={job.id}>
                    <div className="min-w-0">
                      <p className="truncate font-mono text-sm font-semibold text-text">{job.id}</p>
                      <p className="text-xs text-muted">{shortDate(job.created_at)}</p>
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
          <h3 className="font-display text-xl font-bold text-text">Keyword gaps</h3>
        </div>
        <div className="mb-4 rounded-2xl border border-line bg-raised/50 px-5 py-4">
          <p className="font-display text-lg leading-relaxed text-text">
            <span className="font-semibold text-site-sky">{displayHost(project.domain)}</span>
            <span className="text-muted">: </span>
            <span className="font-mono font-bold text-signal-amber">{gapTotal.toLocaleString()}</span>
            <span className="text-muted"> missing pages — </span>
            <span className="font-mono font-semibold text-muted">{competitorPages.toLocaleString()}</span>
            <span className="text-muted"> from competitor sitemaps, </span>
            <span className="font-mono font-semibold text-muted">{aiPages.toLocaleString()}</span>
            <span className="text-muted"> AI-recommended, </span>
            <span className="font-mono font-semibold text-muted">{providerPages.toLocaleString()}</span>
            <span className="text-muted"> from Google Autocomplete</span>
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {sourceLegendChip('competitor', 'Sitemap gap')}
            {sourceLegendChip('ai', 'AI-recommended')}
            {sourceLegendChip('provider', 'Autocomplete')}
          </div>
        </div>
        <KeywordsTable projectId={projectId} isActive={projectIsActive} />
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="font-display text-xl font-bold text-text">Latest article</h3>
        </div>
        <GeneratedArticlePanel projectId={projectId} />
      </section>
    </div>
  )
}
