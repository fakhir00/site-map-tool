import { type FormEvent, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowUpRight, CalendarClock, FileText, Globe2, Loader2, Plus, Search, Trash2, X } from 'lucide-react'
import { api, type Project } from '../lib/api'
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
  const variants: Record<Project['status'], { label: string; variant: 'teal' | 'indigo' | 'slate' | 'red' | 'amber' }> = {
    pending: { label: 'Pending', variant: 'slate' },
    running: { label: 'Running', variant: 'indigo' },
    paused: { label: 'Paused', variant: 'amber' },
    complete: { label: 'Complete', variant: 'teal' },
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

  const { data: projects = [], isLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: () => api.get<Project[]>('/projects'),
  })

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
          <h2 className="text-2xl font-bold text-slate-950 dark:text-slate-50">Dashboard</h2>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Track and manage your keyword gap analyses.</p>
        </div>
        <Button onClick={() => setShowNewModal(true)}>
          <Plus className="h-4 w-4" />
          New Gap Hunter
        </Button>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        <Card>
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-slate-500 dark:text-slate-400">Dashboard</p>
            <Globe2 className="h-4 w-4 text-cyan-800 dark:text-cyan-400" />
          </div>
          <p className="mt-3 text-3xl font-bold">{projects.length}</p>
        </Card>
        <Card>
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-slate-500 dark:text-slate-400">URLs discovered</p>
            <FileText className="h-4 w-4 text-indigo-700 dark:text-indigo-400" />
          </div>
          <p className="mt-3 text-3xl font-bold">{totals.urls.toLocaleString()}</p>
        </Card>
        <Card>
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-slate-500 dark:text-slate-400">Keyword gaps</p>
            <CalendarClock className="h-4 w-4 text-emerald-700 dark:text-emerald-400" />
          </div>
          <p className="mt-3 text-3xl font-bold">{totals.keywords.toLocaleString()}</p>
        </Card>
      </section>

      <section className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative w-full sm:max-w-sm">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400 dark:text-slate-500" />
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
          {totals.running > 0 && <Badge variant="indigo">{totals.running} running</Badge>}
        </div>
      </section>

      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {[1, 2, 3].map((item) => (
            <div className="h-48 animate-pulse rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900" key={item} />
          ))}
        </div>
      ) : filteredProjects.length === 0 ? (
        <Card className="py-12 text-center">
          <Globe2 className="mx-auto mb-4 h-10 w-10 text-slate-400 dark:text-slate-500" />
          <h3 className="text-lg font-semibold text-slate-950 dark:text-slate-50">No projects found</h3>
          <p className="mx-auto mt-2 max-w-md text-sm text-slate-500 dark:text-slate-400">
            Add your website and main keyword to find competitor content gaps.
          </p>
          <Button className="mt-4" onClick={() => setShowNewModal(true)}>
            <Plus className="mr-2 h-4 w-4" />
            New Gap Hunter
          </Button>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {filteredProjects.map((project) => {
            const completed = project.urls_found ? Math.round(((project.urls_processed + project.urls_failed) / project.urls_found) * 100) : 0
            return (
              <Card 
                className={`flex min-h-56 flex-col relative ${isSelectionMode && selectedIds.has(project.id) ? 'ring-2 ring-cyan-500 border-cyan-500' : ''}`} 
                key={project.id}
              >
                {isSelectionMode && (
                  <div className="absolute top-6 left-6 z-10">
                    <input 
                      type="checkbox"
                      className="h-5 w-5 rounded border-slate-300 text-cyan-600 focus:ring-cyan-600 cursor-pointer dark:border-slate-700 dark:bg-slate-900"
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
                    <Link className="block truncate text-lg font-semibold text-slate-950 hover:text-cyan-800 dark:text-slate-50 dark:hover:text-cyan-400" to={`/projects/${project.id}`}>
                      {project.name}
                    </Link>
                    <a
                      className="mt-1 flex items-center gap-1 truncate text-sm text-slate-500 hover:text-slate-950 dark:text-slate-400 dark:hover:text-slate-50"
                      href={project.domain}
                      rel="noopener noreferrer"
                      target="_blank"
                    >
                      <Globe2 className="h-3.5 w-3.5 shrink-0" />
                      <span className="truncate">{displayHost(project.domain)}</span>
                    </a>
                    <p className="mt-2 truncate text-sm font-medium text-slate-700 dark:text-slate-300">{primaryKeyword(project)}</p>
                  </div>
                  {!isSelectionMode && (
                    <button
                      aria-label={`Delete ${project.name}`}
                      className="rounded-lg p-2 text-slate-400 hover:bg-rose-50 hover:text-rose-700 disabled:opacity-50 dark:text-slate-500 dark:hover:bg-rose-900/30 dark:hover:text-rose-400"
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
                    <p className="text-slate-500 dark:text-slate-400">URLs</p>
                    <p className="mt-1 font-semibold text-slate-950 dark:text-slate-50">{project.urls_found.toLocaleString()}</p>
                  </div>
                  <div>
                    <p className="text-slate-500 dark:text-slate-400">Scraped</p>
                    <p className="mt-1 font-semibold text-slate-950 dark:text-slate-50">{project.urls_processed.toLocaleString()}</p>
                  </div>
                  <div>
                    <p className="text-slate-500 dark:text-slate-400">Gaps</p>
                    <p className="mt-1 font-semibold text-slate-950 dark:text-slate-50">{project.total_keywords.toLocaleString()}</p>
                  </div>
                </div>

                <div className="mt-5">
                  <div className="mb-2 flex items-center justify-between">
                    {statusBadge(project.status)}
                    <span className="text-xs font-medium text-slate-500 dark:text-slate-400">{completed}%</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                    <div className="h-full rounded-full bg-cyan-700 transition-all" style={{ width: `${Math.min(completed, 100)}%` }} />
                  </div>
                </div>

                <Link className="mt-auto inline-flex items-center gap-2 pt-5 text-sm font-semibold text-cyan-800 hover:text-cyan-900" to={`/projects/${project.id}`}>
                  Open project
                  <ArrowUpRight className="h-4 w-4" />
                </Link>
              </Card>
            )
          })}
        </div>
      )}

      {showNewModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center overflow-y-auto bg-slate-950/40 dark:bg-slate-950/80 p-4">
          <Card className="w-full max-w-2xl">
            <div className="mb-5 flex items-start justify-between gap-4">
              <div>
                <h3 className="text-xl font-bold text-slate-950 dark:text-slate-50">New Gap Hunter</h3>
                <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Enter your website and the main keyword to compare against competitors.</p>
              </div>
              <button
                aria-label="Close"
                className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
                onClick={() => setShowNewModal(false)}
                type="button"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form className="space-y-4" onSubmit={handleCreate}>
              {createMutation.error && (
                <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:border-rose-800/50 dark:bg-rose-900/30 dark:text-rose-300">
                  {createMutation.error.message}
                </div>
              )}

              <div className="grid gap-4 sm:grid-cols-2">
                <label className="block">
                  <span className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">Your website</span>
                  <Input
                    onChange={(event) => setForm({ ...form, site_url: event.target.value })}
                    placeholder="https://yourcompany.com"
                    required
                    value={form.site_url}
                  />
                </label>
                <label className="block">
                  <span className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">Primary keyword</span>
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
                  <span className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">Competitor search region (Optional)</span>
                  <select
                    className="flex h-10 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-50"
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
