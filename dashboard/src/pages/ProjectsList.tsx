import { type FormEvent, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ArrowUpRight, CalendarClock, FileText, Globe2, Loader2, Plus, RefreshCw, Search, Trash2, X } from 'lucide-react'
import { api, type Project } from '../lib/api'
import { projectsQuery } from '../lib/workspaceQueries'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Input } from '../components/ui/Input'

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
  const variants: Record<Project['status'], { label: string; variant: 'teal' | 'indigo' | 'slate' | 'red' | 'amber' | 'green' | 'cyan' }> = {
    pending: { label: 'Pending', variant: 'slate' },
    running: { label: 'Running', variant: 'cyan' },
    paused: { label: 'Paused', variant: 'amber' },
    complete: { label: 'Complete', variant: 'green' },
    error: { label: 'Error', variant: 'red' },
  }
  const item = variants[status] || variants.pending

  return <Badge variant={item.variant}>{item.label}</Badge>
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
    <div className="space-y-6">
      <section className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="font-display text-2xl font-bold text-text">Projects</h2>
          <p className="mt-1 text-sm text-muted">Track and manage your keyword gap analyses.</p>
        </div>
        <Button onClick={() => setShowNewModal(true)}>
          <Plus className="h-4 w-4" />
          New Gap Scan
        </Button>
      </section>

      {projectsError && (
        <Card className="border-signal-red/30 bg-signal-red/10 p-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex gap-3">
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-signal-red" />
              <div>
                <h3 className="font-display font-bold text-text">Backend is reconnecting</h3>
                <p className="mt-1 text-sm text-muted">{projectsError instanceof Error ? projectsError.message : 'The API is temporarily unavailable.'}</p>
                <p className="mt-1 text-xs text-muted/80">This page retries automatically every 15 seconds.</p>
              </div>
            </div>
            <Button variant="secondary" disabled={isFetching} onClick={() => refetchProjects()}>
              {isFetching ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              Retry now
            </Button>
          </div>
        </Card>
      )}

      {!projectsError && !isLoading && <section className="grid gap-4 md:grid-cols-3">
        <Card className="border-line bg-panel">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-muted">Dashboard</p>
            <Globe2 className="h-4 w-4 text-site-sky" />
          </div>
          <p className="mt-3 font-mono text-3xl font-semibold text-text">{projects.length}</p>
        </Card>
        <Card className="border-line bg-panel">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-muted">URLs discovered</p>
            <FileText className="h-4 w-4 text-site-sky" />
          </div>
          <p className="mt-3 font-mono text-3xl font-semibold text-text">{totals.urls.toLocaleString()}</p>
        </Card>
        <Card className="border-line bg-panel">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-muted">Keyword gaps</p>
            <CalendarClock className="h-4 w-4 text-built-green" />
          </div>
          <p className="mt-3 font-mono text-3xl font-semibold text-text">{totals.keywords.toLocaleString()}</p>
        </Card>
      </section>}

      {!projectsError && <section className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative w-full sm:max-w-sm">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <Input className="pl-9" onChange={(event) => { setSearch(event.target.value); setSelectedIds(new Set()) }} placeholder="Search projects" value={search} />
        </div>
        
        <div className="flex flex-wrap items-center gap-3">
          {isSelectionMode ? (
            <>
              <Button
                variant="secondary"
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
                {selectedVisibleIds.length === filteredProjects.length ? 'Deselect All' : 'Select All'}
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
              <Button variant="secondary" size="sm" onClick={() => { setIsSelectionMode(false); setSelectedIds(new Set()) }}>
                Cancel
              </Button>
            </>
          ) : (
            <Button variant="secondary" size="sm" disabled={filteredProjects.length === 0} onClick={() => setIsSelectionMode(true)}>
              Select
            </Button>
          )}
          {totals.running > 0 && <Badge variant="cyan">{totals.running} running</Badge>}
        </div>
      </section>}

      {!projectsError && (isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {[1, 2, 3].map((item) => (
            <div className="h-48 animate-pulse rounded-2xl border border-line bg-panel" key={item} />
          ))}
        </div>
      ) : filteredProjects.length === 0 ? (
        <Card className="border-line bg-panel py-12 text-center">
          <svg className="mx-auto mb-4 h-16 w-16" viewBox="0 0 64 64" fill="none" aria-hidden="true">
            <rect x="22" y="8" width="20" height="10" rx="3" className="fill-raised stroke-line" strokeWidth="1.5" />
            <path d="M32 18v6M32 24L12 38M32 24l20 14" className="stroke-site-sky" strokeWidth="1.5" strokeLinecap="round" />
            <rect x="4" y="38" width="16" height="10" rx="3" className="fill-raised stroke-line" strokeWidth="1.5" />
            <rect x="24" y="38" width="16" height="10" rx="3" className="fill-raised stroke-line" strokeWidth="1.5" />
            <rect x="44" y="38" width="16" height="10" rx="3" className="fill-signal-amber/20 stroke-signal-amber/50" strokeWidth="1.5" strokeDasharray="3 2" />
            <circle cx="12" cy="43" r="1.5" className="fill-built-green" />
            <circle cx="32" cy="43" r="1.5" className="fill-built-green" />
            <circle cx="52" cy="43" r="1.5" className="fill-signal-amber" />
          </svg>
          <h3 className="font-display text-lg font-semibold text-text">No projects found</h3>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted">
            Add your website and main keyword to find competitor content gaps.
          </p>
          <Button className="mt-4" onClick={() => setShowNewModal(true)}>
            <Plus className="mr-2 h-4 w-4" />
            New Gap Scan
          </Button>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {filteredProjects.map((project) => {
            const completed = project.urls_found ? Math.round(((project.urls_processed + project.urls_failed) / project.urls_found) * 100) : 0
            return (
              <Card 
                className={`relative flex min-h-56 flex-col border-line bg-panel ${isSelectionMode && selectedIds.has(project.id) ? 'ring-2 ring-site-sky' : ''}`} 
                key={project.id}
              >
                {isSelectionMode && (
                  <div className="absolute top-6 left-6 z-10">
                    <input 
                      type="checkbox"
                      className="h-5 w-5 cursor-pointer rounded border-line bg-raised accent-site-sky focus:ring-site-sky"
                      checked={selectedIds.has(project.id)}
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
                    <a
                      className="block truncate font-display text-lg font-semibold text-text hover:text-site-sky"
                      href={project.domain}
                      rel="noopener noreferrer"
                      target="_blank"
                    >
                      {displayHost(project.domain)}
                    </a>
                    <Link className="mt-1 flex items-center gap-1 truncate text-sm text-muted hover:text-text" to={`/projects/${project.id}`}>
                      <Globe2 className="h-3.5 w-3.5 shrink-0" />
                      <span className="truncate">{project.name}</span>
                    </Link>
                    <p className="mt-2 truncate text-sm font-medium text-muted">{primaryKeyword(project)}</p>
                  </div>
                  {!isSelectionMode && (
                    <button
                      aria-label={`Delete ${project.name}`}
                      className="rounded-lg p-2 text-muted hover:bg-signal-red/10 hover:text-signal-red disabled:opacity-50"
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

                <div className="mt-5 grid grid-cols-3 gap-3 text-sm">
                  <div>
                    <p className="text-muted">URLs</p>
                    <p className="mt-1 font-mono font-semibold text-text">{project.urls_found.toLocaleString()}</p>
                  </div>
                  <div>
                    <p className="text-muted">Scraped</p>
                    <p className="mt-1 font-mono font-semibold text-text">{project.urls_processed.toLocaleString()}</p>
                  </div>
                  <div>
                    <p className="text-muted">Gaps</p>
                    <p className="mt-1 font-mono font-semibold text-text">{project.total_keywords.toLocaleString()}</p>
                  </div>
                </div>

                <div className="mt-5">
                  <div className="mb-2 flex items-center justify-between">
                    {statusBadge(project.status)}
                    <span className="font-mono text-xs font-medium text-muted">{completed}%</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-raised">
                    <div className="h-full rounded-full bg-site-sky transition-all" style={{ width: `${Math.min(completed, 100)}%` }} />
                  </div>
                </div>

                <Link className="mt-auto inline-flex items-center gap-2 pt-5 text-sm font-semibold text-site-sky hover:text-text" to={`/projects/${project.id}`}>
                  Open project
                  <ArrowUpRight className="h-4 w-4" />
                </Link>
              </Card>
            )
          })}
        </div>
      ))}

      {showNewModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center overflow-y-auto bg-blueprint-deep/80 p-4">
          <Card className="w-full max-w-2xl border-line bg-panel">
            <div className="mb-5 flex items-start justify-between gap-4">
              <div>
                <h3 className="font-display text-xl font-bold text-text">New Gap Scan</h3>
                <p className="mt-1 text-sm text-muted">Enter your website and the main keyword to compare against competitors.</p>
              </div>
              <button
                aria-label="Close"
                className="rounded-lg p-2 text-muted hover:bg-raised hover:text-text"
                onClick={() => setShowNewModal(false)}
                type="button"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form className="space-y-4" onSubmit={handleCreate}>
              {createMutation.error && (
                <div className="rounded-lg border border-signal-red/30 bg-signal-red/10 px-3 py-2 text-sm text-signal-red">
                  {createMutation.error.message}
                </div>
              )}

              <div className="grid gap-4 sm:grid-cols-2">
                <label className="block">
                  <span className="mb-1 block text-sm font-medium text-text">Your website</span>
                  <Input
                    onChange={(event) => setForm({ ...form, site_url: event.target.value })}
                    placeholder="https://yourcompany.com"
                    required
                    value={form.site_url}
                  />
                </label>
                <label className="block">
                  <span className="mb-1 block text-sm font-medium text-text">Primary keyword</span>
                  <Input
                    onChange={(event) => setForm({ ...form, primary_keyword: event.target.value })}
                    placeholder="sitemap generator"
                    required
                    value={form.primary_keyword}
                  />
                </label>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <label className="block">
                  <span className="mb-1 block text-sm font-medium text-text">Competitor search region (Optional)</span>
                  <select
                    className="flex h-10 w-full rounded-lg border border-line bg-raised px-3 py-2 text-sm text-text placeholder:text-muted focus:border-site-sky focus:outline-none focus:ring-1 focus:ring-site-sky disabled:cursor-not-allowed disabled:opacity-50"
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
              </div>

              <div className="flex flex-col-reverse gap-3 pt-2 sm:flex-row sm:justify-end">
                <Button disabled={createMutation.isPending} onClick={() => setShowNewModal(false)} type="button" variant="secondary">
                  Cancel
                </Button>
                <Button disabled={createMutation.isPending} type="submit">
                  {createMutation.isPending ? 'Creating...' : 'Find gaps'}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
  )
}
