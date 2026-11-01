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
import { CountUp } from '../components/CountUp'

const CompetitorGraph = lazy(() => import('../components/CompetitorGraph').then((module) => ({ default: module.CompetitorGraph })))

function statusBadge(status: Project['status'] | string) {
  if (status === 'complete') return <Badge variant="green">Complete</Badge>
  if (status === 'running') return <Badge variant="indigo">Running</Badge>
  if (status === 'paused') return <Badge variant="amber">Paused</Badge>
  if (status === 'error') return <Badge variant="red">Error</Badge>
  if (status === 'scraped') return <Badge variant="green">Analyzed</Badge>
  if (status === 'discovered') return <Badge variant="slate">URL found</Badge>
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
    return (
      <div className="space-y-6 animate-fade-up">
        <div className="animate-shimmer h-28 rounded-2xl" />
        <div className="grid gap-4 md:grid-cols-3">
          {[0, 1, 2].map(i => <div key={i} className="animate-shimmer h-32 rounded-2xl" />)}
        </div>
        <div className="animate-shimmer h-96 rounded-2xl" />
      </div>
    )
  }

  if (!project) {
    return (
      <Card className="p-10 text-center">
        <p className="font-display text-xl font-bold text-ink">Project not found</p>
        <p className="mt-2 text-sm text-muted">This project may have been deleted.</p>
        <Link className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-soft-violet hover:text-ink" to="/">
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

  return (
    <div className="space-y-8 animate-fade-up">
      <section className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <Link className="mb-3 inline-flex items-center gap-2 text-sm font-semibold text-muted transition-colors hover:text-ink" to="/">
            <ArrowLeft className="h-4 w-4" />
            Dashboard
          </Link>
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="font-display text-3xl font-bold tracking-tight text-ink">{project.name}</h2>
            {statusBadge(status)}
          </div>
          <a className="mt-2.5 inline-flex items-center gap-2 text-sm text-muted transition-colors hover:text-ink" href={project.domain} rel="noopener noreferrer" target="_blank">
            <Globe2 className="h-4 w-4" />
            {displayHost(project.domain)}
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
          <p className="mt-2 flex items-center gap-2 text-xs text-muted">
            <Timer className="h-3.5 w-3.5" />
            Last scanned {shortDate(project.last_scanned_at)}
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          {!isRunning && !isPaused && (
            <Button variant="glow" size="lg" disabled={startScanMutation.isPending} onClick={() => startScanMutation.mutate()}>
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
            <Button variant="glow" size="lg" disabled={resumeScanMutation.isPending} onClick={() => resumeScanMutation.mutate()}>
              <Play className="h-4 w-4" />
              Resume
            </Button>
          )}
        </div>
      </section>

      {actionError && (
        <div className="rounded-2xl border border-warm-red/30 bg-warm-red/[0.07] px-5 py-4 text-sm text-warm-red">{actionError.message}</div>
      )}

      {(isRunning || isPaused) && (
        <Card lift={false} className="border-glow-amber/25 bg-glow-amber/[0.03]">
          <div className="flex flex-col gap-5 md:flex-row md:items-center">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-glow-amber/15 text-glow-amber">
              <RefreshCw className={`h-5 w-5 ${isRunning ? 'animate-spin' : ''}`} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="mb-2.5 flex items-center justify-between gap-3">
                <p className="font-display font-bold text-ink">{isPaused ? 'Gap Scan paused' : 'Gap Scan in progress'}</p>
                <span className="font-mono text-sm font-semibold text-glow-amber">{percent}%</span>
              </div>
              <div className="h-2.5 overflow-hidden rounded-full bg-white/5">
                <div className="h-full rounded-full bg-glow-amber shadow-[0_0_16px_rgba(245,165,36,0.6)] transition-all duration-500" style={{ width: `${Math.min(percent, 100)}%` }} />
              </div>
              <p className="mt-2.5 truncate text-sm text-muted">{scanStatus?.current_url || 'Finding top Google competitors and crawling sitemaps'}</p>
            </div>
            <div className="grid grid-cols-3 gap-6 text-right text-sm">
              {[
                ['Analyzed', scanStatus?.urls_processed || 0],
                ['Failed', scanStatus?.urls_failed || 0],
                ['Found', scanStatus?.urls_found || 0],
              ].map(([name, value]) => (
                <div key={name}>
                  <p className="font-mono font-semibold text-ink">{Number(value).toLocaleString()}</p>
                  <p className="text-xs text-muted">{name}</p>
                </div>
              ))}
            </div>
          </div>
        </Card>
      )}

      {latestJobError && (
        <div className={`relative flex items-start gap-3 rounded-2xl border px-5 py-4 pr-12 text-sm ${isCompletionNote ? 'border-line bg-raised text-muted' : isCompletionWarning ? 'border-glow-amber/30 bg-glow-amber/[0.06] text-ink' : 'border-warm-red/30 bg-warm-red/[0.07] text-warm-red'}`}>
          {isCompletionNote ? <Info className="mt-0.5 h-4 w-4 shrink-0" /> : <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />}
          <p>{latestJobError}</p>
          <button
            type="button"
            aria-label="Dismiss scan message"
            onClick={() => setDismissedError(latestJobError)}
            className="absolute right-4 top-4 text-current opacity-70 hover:opacity-100"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Stat strip — three calm focal points */}
      <section className="grid gap-4 md:grid-cols-3">
        <Card className="animate-fade-up stagger-1">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium uppercase tracking-wider text-muted">Keyword gaps</p>
            <Globe2 className="h-4 w-4 text-glow-amber" />
          </div>
          <p className="mt-2 font-display text-4xl font-bold tracking-tight text-ink"><CountUp value={stats?.total_keywords || 0} /></p>
          <p className="mt-1 text-xs text-muted">Opportunities competitors rank for</p>
        </Card>
        <Card className="animate-fade-up stagger-2">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium uppercase tracking-wider text-muted">Pages analyzed</p>
            <RefreshCw className="h-4 w-4 text-soft-violet" />
          </div>
          <p className="mt-2 font-display text-4xl font-bold tracking-tight text-ink"><CountUp value={stats?.scraped_urls || 0} /></p>
          <p className="mt-1 text-xs text-muted">Crawled competitor pages</p>
        </Card>
        <Card className="animate-fade-up stagger-3">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium uppercase tracking-wider text-muted">URLs discovered</p>
            <FileText className="h-4 w-4 text-alive-green" />
          </div>
          <p className="mt-2 font-display text-4xl font-bold tracking-tight text-ink"><CountUp value={stats?.total_urls || 0} /></p>
          <p className="mt-1 text-xs text-muted">Across all sources</p>
        </Card>
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="flex min-w-0 flex-col gap-5">
          <Suspense fallback={<div className="animate-shimmer h-96 rounded-2xl" />}>
            <CompetitorGraph sources={sources} isActive={isRunning} />
          </Suspense>
          <SemanticMetrics isActive={isRunning} />
        </div>

        <div className="min-w-0 space-y-5">
          <LiveSignals isActive={isRunning} progress={scanStatus} error={latestJobError} />

          <details className="rounded-2xl border border-line bg-surface p-5" open={sources.length > 0 && sources.length <= 8}>
            <summary className="cursor-pointer list-none text-sm font-semibold text-ink [&::-webkit-details-marker]:hidden">
              Crawled sources <span className="ml-2 font-mono text-xs font-normal text-muted">{sources.length}</span>
            </summary>
            <div className="disclosure"><div>
            <div className="mt-3 max-h-72 divide-y divide-white/5 overflow-y-auto">
              {sources.length === 0 ? (
                <p className="py-6 text-center text-sm text-muted">No sources have been queued yet.</p>
              ) : (
                sources.map((source) => {
                  const isAi = source.source_type === 'ai'
                  const isProvider = source.source_type === 'provider'
                  const href = isAi || isProvider ? undefined : (source.source_domain || project.domain)
                  const label = isAi || isProvider ? (source.source_domain || (isProvider ? 'Keyword provider' : 'AI Recommendations')) : displayHost(href!)
                  const sourceLabel = source.source_type === 'own' ? 'Your site' : isAi ? 'AI' : isProvider ? 'Provider' : 'Competitor'
                  return (
                    <div className="flex items-center justify-between gap-4 py-3.5" key={`${source.source_type}-${source.source_domain || 'unknown'}`}>
                      <div className="min-w-0">
                        {href ? (
                          <a className="flex items-center gap-2 truncate text-sm font-semibold text-ink transition-colors hover:text-glow-amber" href={href} rel="noopener noreferrer" target="_blank">
                            {label}
                            <ExternalLink className="h-3.5 w-3.5 shrink-0" />
                          </a>
                        ) : (
                          <span className="flex items-center gap-2 truncate text-sm font-semibold text-ink">{label}</span>
                        )}
                        <p className="mt-1 font-mono text-xs text-muted">
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
            </div></div>
          </details>

          <details className="rounded-2xl border border-line bg-surface p-5">
            <summary className="cursor-pointer list-none text-sm font-semibold text-ink [&::-webkit-details-marker]:hidden">
              Gap Scan history <span className="ml-2 font-mono text-xs font-normal text-muted">{jobs.length}</span>
            </summary>
            <div className="disclosure"><div>
            <div className="mt-3 divide-y divide-white/5">
              {jobs.length === 0 ? (
                <p className="py-6 text-center text-sm text-muted">No Gap Scan jobs yet.</p>
              ) : (
                jobs.slice(0, 6).map((job) => (
                  <div className="flex items-center justify-between gap-4 py-3.5" key={job.id}>
                    <div className="min-w-0">
                      <p className="truncate font-mono text-xs text-muted">{job.id}</p>
                      <p className="mt-0.5 text-xs text-muted">{shortDate(job.created_at)}</p>
                    </div>
                    {statusBadge(job.status)}
                  </div>
                ))
              )}
            </div>
            </div></div>
          </details>
        </div>
      </section>

      <section>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="font-display text-xl font-bold tracking-tight text-ink">Keyword gaps</h3>
        </div>
        <KeywordsTable projectId={projectId} isActive={projectIsActive} />
      </section>

      <section>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="font-display text-xl font-bold tracking-tight text-ink">Latest article</h3>
        </div>
        <GeneratedArticlePanel projectId={projectId} />
      </section>
    </div>
  )
}
