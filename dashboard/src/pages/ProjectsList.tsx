import { type FormEvent, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ArrowUpRight, Globe2, Loader2, Plus, RefreshCw, Search, Trash2, X } from 'lucide-react'
import { api, type Project } from '../lib/api'
import { projectsQuery } from '../lib/workspaceQueries'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Input } from '../components/ui/Input'
import { CountUp } from '../components/CountUp'

type ProjectForm = {
  site_url: string
  primary_keyword: string
  search_locale: string
}

type ProjectCreate = {
  name: string
  domain: string
  own_domain: string
  scan_frequency: string
  target_keywords: string[]
  search_locale: string
}

const initialProject: ProjectForm = {
  site_url: '',
  primary_keyword: '',
  search_locale: 'us',
}

function displayHost(value: string) {
  try {
    const withScheme = value.startsWith('http://') || value.startsWith('https://') ? value : `https://${value}`
    return new URL(withScheme).hostname.replace(/^www\./, '')
  } catch {
    return value.replace(/^https?:\/\//, '')
  }
}

function primaryKeyword(project: Project) {
  return project.target_keywords?.[0] || 'No keyword'
}

function statusBadge(status: Project['status']) {
  const variants: Record<Project['status'], { label: string; variant: 'teal' | 'indigo' | 'slate' | 'red' | 'amber' }> = {
    pending: { label: 'Pending', variant: 'slate' },
    running: { label: 'Scanning', variant: 'indigo' },
    paused: { label: 'Paused', variant: 'amber' },
    complete: { label: 'Complete', variant: 'teal' },
    error: { label: 'Needs attention', variant: 'red' },
  }
  const item = variants[status] || variants.pending

  return <Badge variant={item.variant}>{item.label}</Badge>
}

function EmptyIllustration() {
  return (
    <svg aria-hidden="true" className="mx-auto h-28 w-28" viewBox="0 0 112 112" fill="none">
      <circle cx="56" cy="56" r="52" fill="#F5A524" opacity="0.08" />
      <circle cx="56" cy="46" r="16" fill="#F5A524" opacity="0.28" />
      <circle cx="56" cy="46" r="9" fill="#F5A524" opacity="0.55" />
      <path d="M20 84c10-8 22-8 36-8s26 0 36 8" stroke="#34D399" strokeWidth="4" strokeLinecap="round" opacity="0.7" />
      <path d="M28 92c8-5 16-5 28-5s20 0 28 5" stroke="#A78BFA" strokeWidth="3" strokeLinecap="round" opacity="0.45" />
    </svg>
  )
}

export function ProjectsList() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const queryClient = useQueryClient()
  const [showNewModal, setShowNewModal] = useState(Boolean(searchParams.get('new_keyword')))
  const [search, setSearch] = useState('')
  const [form, setForm] = useState<ProjectForm>(() => ({ ...initialProject, primary_keyword: searchParams.get('new_keyword') || '', site_url: searchParams.get('site_url') || '' }))

  const { data: projects = [], isLoading, isFetching, error: projectsError, refetch: refetchProjects } = useQuery(projectsQuery)

  const filteredProjects = useMemo(() => {
    const normalized = search.trim().toLowerCase()
    if (!normalized) return projects
    return projects.filter((project) => {
      return (
        project.name.toLowerCase().includes(normalized) ||
        project.domain.toLowerCase().includes(normalized) ||
        primaryKeyword(project).toLowerCase().includes(normalized)
      )
    })
  }, [projects, search])

  const totals = useMemo(() => {
    return projects.reduce(
      (acc, project) => {
        acc.urls += project.urls_found
        acc.keywords += project.total_keywords
        if (project.status === 'running') acc.running += 1
        return acc
      },
      { urls: 0, keywords: 0, running: 0 },
    )
  }, [projects])

  const createMutation = useMutation({
    mutationFn: (payload: ProjectCreate) => api.post<Project>('/projects', payload),
    onSuccess: async (project: Project) => {
      try {
        await api.post(`/projects/${project.id}/scan/start`)
      } catch (err) {
        console.error('Failed to auto-start scan', err)
      }
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      setShowNewModal(false)
      setForm(initialProject)
      navigate(`/projects/${project.id}`)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (projectId: string) => api.delete<null>(`/projects/${projectId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
    onError: (error) => {
      alert(error instanceof Error ? error.message : 'Could not delete the project.')
    },
  })

  const [isSelectionMode, setIsSelectionMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [isDeletingBulk, setIsDeletingBulk] = useState(false)
  const visibleProjectIds = new Set(filteredProjects.map((project) => project.id))
  const selectedVisibleIds = Array.from(selectedIds).filter((id) => visibleProjectIds.has(id))

  const handleBulkDelete = async () => {
    if (selectedVisibleIds.length === 0) return
    if (!window.confirm(`Permanently delete ${selectedVisibleIds.length} project${selectedVisibleIds.length === 1 ? '' : 's'}?`)) return

    setIsDeletingBulk(true)
    try {
      const ids = selectedVisibleIds
      const results = await Promise.allSettled(ids.map(id => api.delete(`/projects/${id}`)))
      const failedIds = ids.filter((_id, index) => results[index].status === 'rejected')
      await queryClient.invalidateQueries({ queryKey: ['projects'] })
      setSelectedIds(new Set(failedIds))
      if (failedIds.length > 0) {
        alert(`${ids.length - failedIds.length} projects deleted. ${failedIds.length} could not be deleted and remain selected.`)
        return
      }
      setIsSelectionMode(false)
    } finally {
      setIsDeletingBulk(false)
    }
  }

  const handleCreate = (event: FormEvent) => {
    event.preventDefault()
    const siteUrl = form.site_url.trim()
    const keyword = form.primary_keyword.trim()

    createMutation.mutate({
      name: `${keyword} gaps for ${displayHost(siteUrl)}`,
      domain: siteUrl,
      own_domain: siteUrl,
      scan_frequency: 'once',
      target_keywords: [keyword],
      search_locale: form.search_locale,
    })
  }

  return (
    <div className="page-shell space-y-10">
      {/* Hero */}
      <section className="warm-glow-bg glow-drift animate-fade-up relative flex flex-col gap-6 overflow-hidden rounded-3xl border border-line bg-surface px-6 py-8 sm:flex-row sm:items-center sm:justify-between sm:px-10 sm:py-10">
        <div className="max-w-xl">
          <p className="text-sm font-medium text-glow-amber">Welcome back</p>
          <h1 className="font-display mt-2 text-3xl font-bold text-ink sm:text-4xl">Let's map your next site.</h1>
          <p className="mt-3 text-muted">
            {projects.length === 0
              ? 'Create your first project to map a site\u2019s topical authority.'
              : totals.running > 0
                ? `${projects.length} project${projects.length === 1 ? '' : 's'} live — ${totals.running} still scanning.`
                : `${projects.length} project${projects.length === 1 ? '' : 's'} on the board. Ready for the next one?`}
          </p>
        </div>
        <Button className="shrink-0" onClick={() => setShowNewModal(true)} size="lg" variant="glow">
          <Plus className="h-5 w-5" />
          New project
        </Button>
      </section>

      {projectsError && (
        <Card className="border-glow-amber/40 bg-glow-amber/5 p-6" lift={false}>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex gap-3">
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-glow-amber" />
              <div>
                <h3 className="font-bold text-ink">Backend is reconnecting</h3>
                <p className="mt-1 text-sm text-muted">{projectsError instanceof Error ? projectsError.message : 'The API is temporarily unavailable.'}</p>
                <p className="mt-1 text-xs text-muted">This page retries automatically every 15 seconds.</p>
              </div>
            </div>
            <Button variant="ghost" disabled={isFetching} onClick={() => refetchProjects()}>
              {isFetching ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              Retry now
            </Button>
          </div>
        </Card>
      )}

      {!projectsError && !isLoading && filteredProjects.length > 0 && (
        <section className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative w-full sm:max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <Input className="pl-9" onChange={(event) => { setSearch(event.target.value); setSelectedIds(new Set()) }} placeholder="Search projects" value={search} />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {isSelectionMode ? (
              <>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={filteredProjects.length === 0}
                  onClick={() => {
                    if (selectedVisibleIds.length === filteredProjects.length) {
                      setSelectedIds(new Set())
                    } else {
                      setSelectedIds(new Set(filteredProjects.map(p => p.id)))
                    }
                  }}
                >
                  {selectedVisibleIds.length === filteredProjects.length ? 'Deselect all' : 'Select all'}
                </Button>
                <Button
                  variant="danger"
                  size="sm"
                  disabled={selectedVisibleIds.length === 0 || isDeletingBulk}
                  onClick={handleBulkDelete}
                >
                  {isDeletingBulk ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Trash2 className="h-4 w-4 mr-2" />}
                  Delete ({selectedVisibleIds.length})
                </Button>
                <Button variant="ghost" size="sm" onClick={() => { setIsSelectionMode(false); setSelectedIds(new Set()) }}>
                  Cancel
                </Button>
              </>
            ) : (
              <Button variant="ghost" size="sm" disabled={filteredProjects.length === 0} onClick={() => setIsSelectionMode(true)}>
                Select
              </Button>
            )}
            {totals.running > 0 && <Badge variant="indigo">{totals.running} scanning</Badge>}
          </div>
        </section>
      )}

      {!projectsError && (isLoading ? (
        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
          {[1, 2, 3].map((item) => (
            <div className="animate-shimmer h-56 rounded-2xl border border-line bg-surface" key={item} />
          ))}
        </div>
      ) : filteredProjects.length === 0 ? (
        <Card className="animate-fade-up px-6 py-16 text-center" lift={false}>
          <EmptyIllustration />
          <h2 className="font-display mt-6 text-2xl font-bold text-ink">
            {search ? 'Nothing matches that search' : 'Start your first project'}
          </h2>
          <p className="mx-auto mt-3 max-w-md text-muted">
            {search
              ? 'Try a different name, domain or keyword.'
              : 'Create your first project to map a site’s topical authority — pick a website, add your keyword, and we’ll find the gaps your competitors are covering.'}
          </p>
          {!search && (
            <Button className="mt-8" onClick={() => setShowNewModal(true)} size="lg" variant="glow">
              <Plus className="h-5 w-5" />
              Create your first project
            </Button>
          )}
        </Card>
      ) : (
        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
          {filteredProjects.map((project, pi) => {
            const completed = project.urls_found ? Math.round(((project.urls_processed + project.urls_failed) / project.urls_found) * 100) : 0
            const selected = isSelectionMode && selectedIds.has(project.id)
            return (
              <Card
                className={`animate-fade-up relative flex min-h-56 flex-col stagger-${Math.min(pi + 1, 8)} ${selected ? 'ring-2 ring-glow-amber border-glow-amber/60' : ''}`}
                key={project.id}
              >
                {isSelectionMode && (
                  <div className="absolute left-5 top-5 z-10">
                    <input
                      type="checkbox"
                      className="h-5 w-5 cursor-pointer rounded border-line bg-raised accent-[#F5A524]"
                      checked={selected}
                      onChange={(e) => {
                        const newSet = new Set(selectedIds)
                        if (e.target.checked) newSet.add(project.id)
                        else newSet.delete(project.id)
                        setSelectedIds(newSet)
                      }}
                    />
                  </div>
                )}

                <div className={`flex items-start justify-between gap-3 ${isSelectionMode ? 'pl-8' : ''}`}>
                  <div className="min-w-0">
                    <Link className="font-display block truncate text-xl font-bold text-ink transition-colors hover:text-glow-amber" to={`/projects/${project.id}`}>
                      {project.name}
                    </Link>
                    <a
                      className="mt-1.5 flex items-center gap-1.5 truncate text-sm text-muted transition-colors hover:text-ink"
                      href={project.domain}
                      rel="noopener noreferrer"
                      target="_blank"
                    >
                      <Globe2 className="h-3.5 w-3.5 shrink-0" />
                      <span className="truncate">{displayHost(project.domain)}</span>
                    </a>
                  </div>
                  {!isSelectionMode && (
                    <button
                      aria-label={`Delete ${project.name}`}
                      className="rounded-lg p-2 text-muted transition-colors hover:bg-warm-red/10 hover:text-warm-red disabled:opacity-50"
                      disabled={deleteMutation.isPending}
                      onClick={(e) => {
                        e.preventDefault()
                        e.stopPropagation()
                        if (window.confirm(`Delete ${project.name}?`)) {
                          deleteMutation.mutate(project.id)
                        }
                      }}
                      type="button"
                    >
                      {deleteMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                    </button>
                  )}
                </div>

                <p className="mt-3 truncate text-sm text-muted">
                  <span className="text-ink/80">{primaryKeyword(project)}</span>
                </p>

                <div className="mt-4 flex items-center gap-5">
                  <div>
                    <p className="font-mono text-[11px] uppercase tracking-wide text-muted">URLs</p>
                    <p className="mt-1 font-semibold text-ink"><CountUp value={project.urls_found} /></p>
                  </div>
                  <div>
                    <p className="font-mono text-[11px] uppercase tracking-wide text-muted">Gaps</p>
                    <p className="mt-1 font-semibold text-glow-amber"><CountUp value={project.total_keywords} /></p>
                  </div>
                  <div className="ml-auto">
                    {statusBadge(project.status)}
                  </div>
                </div>

                <div className="mt-4">
                  <div className="h-1.5 overflow-hidden rounded-full bg-raised">
                    <div className="h-full rounded-full bg-glow-amber transition-all" style={{ width: `${Math.min(completed, 100)}%` }} />
                  </div>
                  <p className="mt-1.5 font-mono text-[11px] text-muted">{completed}% mapped</p>
                </div>

                <Link className="mt-auto inline-flex items-center gap-1.5 pt-5 text-sm font-semibold text-glow-amber transition-opacity hover:opacity-80" to={`/projects/${project.id}`}>
                  Open project
                  <ArrowUpRight className="h-4 w-4" />
                </Link>
              </Card>
            )
          })}
        </div>
      ))}

      {showNewModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center overflow-y-auto bg-abyss/80 p-4">
          <Card className="w-full max-w-lg" lift={false}>
            <div className="mb-6 flex items-start justify-between gap-4">
              <div>
                <h3 className="font-display text-2xl font-bold text-ink">New project</h3>
                <p className="mt-1 text-sm text-muted">Add your website and main keyword — we'll find the gaps worth covering.</p>
              </div>
              <button
                aria-label="Close"
                className="rounded-lg p-2 text-muted transition-colors hover:bg-overlay/5 hover:text-ink"
                onClick={() => setShowNewModal(false)}
                type="button"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form className="space-y-5" onSubmit={handleCreate}>
              {createMutation.error && (
                <div className="rounded-lg border border-warm-red/40 bg-warm-red/10 px-3 py-2 text-sm text-warm-red">
                  {createMutation.error.message}
                </div>
              )}

              <label className="block">
                <span className="mb-1.5 block text-sm font-medium text-ink">Your website</span>
                <Input
                  onChange={(event) => setForm({ ...form, site_url: event.target.value })}
                  placeholder="https://yourcompany.com"
                  required
                  value={form.site_url}
                />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-sm font-medium text-ink">Primary keyword</span>
                <Input
                  onChange={(event) => setForm({ ...form, primary_keyword: event.target.value })}
                  placeholder="sitemap generator"
                  required
                  value={form.primary_keyword}
                />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-sm font-medium text-ink">Competitor search region</span>
                <select
                  className="flex h-10 w-full rounded-md border border-line bg-raised px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-glow-amber focus:outline-none focus:ring-1 focus:ring-glow-amber disabled:cursor-not-allowed disabled:opacity-50"
                  onChange={(event) => setForm({ ...form, search_locale: event.target.value })}
                  value={form.search_locale}
                >
                  <option value="us">United States (Default)</option>
                  <option value="gb">United Kingdom</option>
                  <option value="ca">Canada</option>
                  <option value="au">Australia</option>
                  <option value="in">India</option>
                  <option value="de">Germany</option>
                  <option value="fr">France</option>
                </select>
              </label>

              <div className="flex flex-col-reverse gap-3 pt-2 sm:flex-row sm:justify-end">
                <Button disabled={createMutation.isPending} onClick={() => setShowNewModal(false)} type="button" variant="ghost">
                  Cancel
                </Button>
                <Button disabled={createMutation.isPending} type="submit" variant="glow">
                  {createMutation.isPending ? 'Creating...' : 'Start gap scan'}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
  )
}
