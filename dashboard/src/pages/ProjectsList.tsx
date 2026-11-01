import { type FormEvent, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ArrowUpRight, Check, Globe2, Loader2, Network, Plus, RefreshCw, Search, Trash2, X } from 'lucide-react'
import { api, type Project } from '../lib/api'
import { projectsQuery } from '../lib/workspaceQueries'
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

function statusStamp(status: Project['status']) {
  const variants: Record<Project['status'], { label: string; className: string }> = {
    pending: { label: 'Pending', className: 'stamp-muted' },
    running: { label: 'Scanning', className: 'stamp-amber' },
    paused: { label: 'Paused', className: 'stamp-muted' },
    complete: { label: 'Complete', className: 'stamp-green' },
    error: { label: 'Failed', className: 'stamp-red' },
  }
  const item = variants[status] || variants.pending

  return <span className={`stamp ${item.className}`}>{item.label}</span>
}

const fieldLabel = 'mb-1.5 block font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-muted'

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

  const checklist = useMemo(() => {
    const hasProject = projects.length > 0
    const hasScan = projects.some((project) => project.urls_found > 0 || Boolean(project.last_scanned_at))
    const hasGaps = projects.some((project) => project.total_keywords > 0)
    return [
      { label: 'Pin your first site', detail: 'Add a website to the board', done: hasProject },
      { label: 'Run a gap scan', detail: 'Crawl the site and its competitors', done: hasScan },
      { label: 'Review keyword gaps', detail: 'Open a sheet to read the findings', done: hasGaps },
    ]
  }, [projects])
  const checklistComplete = checklist.every((item) => item.done)

  const sheetDate = useMemo(
    () => new Date().toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' }).toUpperCase(),
    [],
  )

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
      {/* Title block header */}
      <header className="border-b border-line pb-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="annotation">Drawing index — every site pinned to the board</p>
            <h2 className="mt-2 font-display text-3xl font-bold tracking-tight text-text">Projects</h2>
          </div>
          <div className="flex items-stretch gap-3">
            <dl className="hidden grid-cols-3 divide-x divide-line border border-line bg-panel sm:grid">
              <div className="px-4 py-2">
                <dt className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">Sheet</dt>
                <dd className="mt-1 font-mono text-xs font-semibold text-text">A-101</dd>
              </div>
              <div className="px-4 py-2">
                <dt className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">Rev</dt>
                <dd className="mt-1 font-mono text-xs font-semibold text-text">P1</dd>
              </div>
              <div className="px-4 py-2">
                <dt className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">Date</dt>
                <dd className="mt-1 font-mono text-xs font-semibold text-text">{sheetDate}</dd>
              </div>
            </dl>
            <Button className="self-center" onClick={() => setShowNewModal(true)} variant="draft">
              <Plus className="h-4 w-4" />
              New Project
            </Button>
          </div>
        </div>
      </header>

      {projectsError && (
        <Card className="border-amber/60 bg-amber/5 p-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex gap-3">
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber" />
              <div>
                <span className="stamp stamp-amber">Signal lost</span>
                <p className="mt-2 text-sm text-text">{projectsError instanceof Error ? projectsError.message : 'The API is temporarily unavailable.'}</p>
                <p className="mt-1 font-mono text-[11px] text-muted">This page retries automatically every 15 seconds.</p>
              </div>
            </div>
            <Button variant="secondary" disabled={isFetching} onClick={() => refetchProjects()}>
              {isFetching ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              Retry now
            </Button>
          </div>
        </Card>
      )}

      {!projectsError && !isLoading && (
        <div>
          <section className="spec-plate" aria-label="Aggregate scan totals">
            <div className="grid grid-cols-3 gap-4 px-5 py-4 sm:px-8">
              <div>
                <p className="spec-label">Projects</p>
                <p className="spec-value">{projects.length}</p>
              </div>
              <div>
                <p className="spec-label">URLs</p>
                <p className="spec-value">{totals.urls.toLocaleString()}</p>
              </div>
              <div>
                <p className="spec-label">Gaps</p>
                <p className="spec-value">{totals.keywords.toLocaleString()}</p>
              </div>
            </div>
          </section>
          {totals.running > 0 && (
            <p className="annotation mt-2">{totals.running} sheet{totals.running === 1 ? '' : 's'} currently in scan</p>
          )}
        </div>
      )}

      {!projectsError && !isLoading && !checklistComplete && (
        <Card className="p-5">
          <div className="flex items-center gap-4">
            <span className="stamp stamp-amber">Setup</span>
            <h3 className="font-display text-base font-bold text-text">First-run checklist</h3>
          </div>
          <ul className="mt-4 space-y-2">
            {checklist.map((item) => (
              <li className="flex items-start gap-3 rounded-lg border border-line bg-ink/60 px-3 py-2.5" key={item.label}>
                <span
                  className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${
                    item.done ? 'border-amber bg-amber text-ink' : 'border-dashed border-line text-muted'
                  }`}
                >
                  {item.done && <Check className="h-3 w-3" />}
                </span>
                <div className="min-w-0">
                  <p className={`text-sm font-medium ${item.done ? 'text-muted line-through' : 'text-text'}`}>{item.label}</p>
                  <p className="font-mono text-[11px] text-muted">{item.detail}</p>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {!projectsError && (
        <section className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div className="w-full sm:max-w-sm">
            <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">▸ Find a sheet</span>
            <div className="relative mt-1.5">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
              <Input className="pl-9" onChange={(event) => { setSearch(event.target.value); setSelectedIds(new Set()) }} placeholder="Search domain, name or keyword" value={search} />
            </div>
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
            {totals.running > 0 && <span className="stamp stamp-amber">{totals.running} scanning</span>}
          </div>
        </section>
      )}

      {!projectsError && (isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {[1, 2, 3].map((item) => (
            <div className="h-56 animate-pulse rounded-xl border border-line bg-panel" key={item} />
          ))}
        </div>
      ) : projects.length === 0 ? (
        <div className="bg-blueprint rounded-xl border border-line p-6 sm:p-12">
          <div className="dashed-amber mx-auto max-w-md rounded-lg bg-ink/80 px-8 py-12 text-center">
            <Network className="mx-auto h-10 w-10 text-amber" />
            <h3 className="mt-4 font-display text-lg font-bold text-text">The board is empty</h3>
            <p className="annotation mx-auto mt-3 max-w-xs">No sheets on the board yet — pin your first site.</p>
            <Button className="mt-5" onClick={() => setShowNewModal(true)} variant="draft">
              <Plus className="h-4 w-4" />
              New Project
            </Button>
          </div>
        </div>
      ) : filteredProjects.length === 0 ? (
        <p className="annotation">No sheets match this search.</p>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {filteredProjects.map((project, index) => {
            const completed = project.urls_found ? Math.round(((project.urls_processed + project.urls_failed) / project.urls_found) * 100) : 0
            const selected = isSelectionMode && selectedIds.has(project.id)
            return (
              <Card
                className={`group relative flex min-h-60 flex-col p-5 pt-6 ${selected ? 'ring-2 ring-amber border-amber' : ''}`}
                key={project.id}
              >
                <span aria-hidden className="absolute left-1/2 top-2.5 h-2.5 w-2.5 -translate-x-1/2 rounded-full bg-amber shadow-[0_2px_5px_rgba(0,0,0,0.55)] ring-2 ring-ink" />

                {isSelectionMode && (
                  <div className="absolute left-5 top-5 z-10">
                    <input
                      type="checkbox"
                      className="h-5 w-5 cursor-pointer rounded border-line bg-ink text-amber focus:ring-amber"
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
                    <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted">
                      Sheet {String(index + 1).padStart(2, '0')} · {project.created_at ? new Date(project.created_at).toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' }).toUpperCase() : '—'}
                    </p>
                    <Link className="mt-1.5 block truncate font-display text-xl font-bold text-text hover:text-amber" to={`/projects/${project.id}`}>
                      {displayHost(project.domain)}
                    </Link>
                    <a
                      className="mt-1 flex items-center gap-1.5 truncate font-mono text-[11px] text-muted hover:text-text"
                      href={project.domain}
                      rel="noopener noreferrer"
                      target="_blank"
                    >
                      <Globe2 className="h-3 w-3 shrink-0" />
                      <span className="truncate">{project.name}</span>
                    </a>
                    <p className="mt-2 truncate font-mono text-xs text-amber">{primaryKeyword(project)}</p>
                  </div>
                  {!isSelectionMode && (
                    <button
                      aria-label={`Delete ${project.name}`}
                      className="rounded-lg p-2 text-muted opacity-100 hover:bg-red/10 hover:text-red disabled:opacity-50 sm:opacity-0 sm:group-hover:opacity-100 sm:focus:opacity-100"
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

                <div className="mt-4 grid grid-cols-3 gap-3 border-y border-line py-3 font-mono">
                  <div>
                    <p className="text-[10px] uppercase tracking-[0.14em] text-muted">URLs</p>
                    <p className="mt-1 text-sm font-semibold text-text">{project.urls_found.toLocaleString()}</p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-[0.14em] text-muted">Scraped</p>
                    <p className="mt-1 text-sm font-semibold text-text">{project.urls_processed.toLocaleString()}</p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-[0.14em] text-muted">Gaps</p>
                    <p className="mt-1 text-sm font-semibold text-text">{project.total_keywords.toLocaleString()}</p>
                  </div>
                </div>

                <div className="mt-4">
                  <div className="mb-2 flex items-center justify-between gap-3">
                    {statusStamp(project.status)}
                    <span className="font-mono text-xs text-muted">{completed}%</span>
                  </div>
                  <div className="rounded border border-dashed border-amber/40 p-1">
                    <div className="h-1.5 overflow-hidden rounded-sm bg-ink">
                      <div className="h-full rounded-sm bg-amber transition-all" style={{ width: `${Math.min(completed, 100)}%` }} />
                    </div>
                  </div>
                </div>

                <Link className="mt-auto inline-flex items-center gap-2 pt-5 font-mono text-xs font-semibold uppercase tracking-[0.14em] text-amber hover:brightness-125" to={`/projects/${project.id}`}>
                  Open sheet
                  <ArrowUpRight className="h-4 w-4" />
                </Link>
              </Card>
            )
          })}
        </div>
      ))}

      {showNewModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center overflow-y-auto bg-ink/70 p-4">
          <Card className="w-full max-w-2xl">
            <div className="mb-5 flex items-start justify-between gap-4">
              <div>
                <p className="annotation">New sheet — pin a site to the board</p>
                <h3 className="mt-2 font-display text-xl font-bold text-text">New Gap Scan</h3>
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
                <div className="rounded-lg border border-red/50 bg-red/10 px-3 py-2 text-sm text-red">
                  {createMutation.error.message}
                </div>
              )}

              <div className="grid gap-4 sm:grid-cols-2">
                <label className="block">
                  <span className={fieldLabel}>Your website</span>
                  <Input
                    onChange={(event) => setForm({ ...form, site_url: event.target.value })}
                    placeholder="https://yourcompany.com"
                    required
                    value={form.site_url}
                  />
                </label>
                <label className="block">
                  <span className={fieldLabel}>Primary keyword</span>
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
                  <span className={fieldLabel}>Competitor search region <span className="font-normal text-muted/70">(optional)</span></span>
                  <select
                    className="flex h-10 w-full rounded-md border border-line bg-ink px-3 py-2 font-mono text-sm text-text placeholder:text-muted/60 focus:border-amber/70 focus:outline-none focus:ring-2 focus:ring-amber/40 disabled:cursor-not-allowed disabled:opacity-50"
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
                <Button disabled={createMutation.isPending} type="submit" variant="draft">
                  {createMutation.isPending ? 'Pinning...' : 'Pin & scan'}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
  )
}
