import { type FormEvent, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowUpRight, CalendarClock, FileText, Globe2, Plus, Search, Trash2, X } from 'lucide-react'
import { api, type Project } from '../lib/api'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Input } from '../components/ui/Input'

type ProjectForm = {
  site_url: string
  primary_keyword: string
}

type ProjectCreate = {
  name: string
  domain: string
  own_domain: string
  scan_frequency: string
  target_keywords: string[]
}

const initialProject: ProjectForm = {
  site_url: '',
  primary_keyword: '',
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
  const queryClient = useQueryClient()
  const [showNewModal, setShowNewModal] = useState(false)
  const [search, setSearch] = useState('')
  const [form, setForm] = useState<ProjectForm>(initialProject)

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
    onSuccess: (project) => {
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
  })

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
    })
  }

  return (
    <div className="space-y-6">
      <section className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-950">Projects</h2>
          <p className="mt-1 text-sm text-slate-500">Find competitor sitemap gaps from one website and one main keyword.</p>
        </div>
        <Button onClick={() => setShowNewModal(true)}>
          <Plus className="h-4 w-4" />
          New scan
        </Button>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        <Card>
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-slate-500">Projects</p>
            <Globe2 className="h-4 w-4 text-cyan-800" />
          </div>
          <p className="mt-3 text-3xl font-bold">{projects.length}</p>
        </Card>
        <Card>
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-slate-500">URLs discovered</p>
            <FileText className="h-4 w-4 text-indigo-700" />
          </div>
          <p className="mt-3 text-3xl font-bold">{totals.urls.toLocaleString()}</p>
        </Card>
        <Card>
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-slate-500">Keyword gaps</p>
            <CalendarClock className="h-4 w-4 text-emerald-700" />
          </div>
          <p className="mt-3 text-3xl font-bold">{totals.keywords.toLocaleString()}</p>
        </Card>
      </section>

      <section className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative w-full sm:max-w-sm">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input className="pl-9" onChange={(event) => setSearch(event.target.value)} placeholder="Search projects" value={search} />
        </div>
        {totals.running > 0 && <Badge variant="indigo">{totals.running} running</Badge>}
      </section>

      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {[1, 2, 3].map((item) => (
            <div className="h-48 animate-pulse rounded-lg border border-slate-200 bg-white" key={item} />
          ))}
        </div>
      ) : filteredProjects.length === 0 ? (
        <Card className="py-12 text-center">
          <Globe2 className="mx-auto mb-4 h-10 w-10 text-slate-400" />
          <h3 className="text-lg font-semibold text-slate-950">No projects found</h3>
          <p className="mx-auto mt-2 max-w-md text-sm text-slate-500">
            Add your website and main keyword to find competitor content gaps.
          </p>
          <Button className="mt-6" onClick={() => setShowNewModal(true)}>
            <Plus className="h-4 w-4" />
            New scan
          </Button>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {filteredProjects.map((project) => {
            const completed = project.urls_found ? Math.round(((project.urls_processed + project.urls_failed) / project.urls_found) * 100) : 0
            return (
              <Card className="flex min-h-56 flex-col" key={project.id}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <Link className="block truncate text-lg font-semibold text-slate-950 hover:text-cyan-800" to={`/projects/${project.id}`}>
                      {project.name}
                    </Link>
                    <a
                      className="mt-1 flex items-center gap-1 truncate text-sm text-slate-500 hover:text-slate-950"
                      href={project.domain}
                      rel="noopener noreferrer"
                      target="_blank"
                    >
                      <Globe2 className="h-3.5 w-3.5 shrink-0" />
                      <span className="truncate">{displayHost(project.domain)}</span>
                    </a>
                    <p className="mt-2 truncate text-sm font-medium text-slate-700">{primaryKeyword(project)}</p>
                  </div>
                  <button
                    aria-label={`Delete ${project.name}`}
                    className="rounded-lg p-2 text-slate-400 hover:bg-rose-50 hover:text-rose-700"
                    onClick={() => {
                      if (window.confirm(`Delete ${project.name}?`)) deleteMutation.mutate(project.id)
                    }}
                    type="button"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>

                <div className="mt-5 grid grid-cols-3 gap-3 text-sm">
                  <div>
                    <p className="text-slate-500">URLs</p>
                    <p className="mt-1 font-semibold text-slate-950">{project.urls_found.toLocaleString()}</p>
                  </div>
                  <div>
                    <p className="text-slate-500">Scraped</p>
                    <p className="mt-1 font-semibold text-slate-950">{project.urls_processed.toLocaleString()}</p>
                  </div>
                  <div>
                    <p className="text-slate-500">Gaps</p>
                    <p className="mt-1 font-semibold text-slate-950">{project.total_keywords.toLocaleString()}</p>
                  </div>
                </div>

                <div className="mt-5">
                  <div className="mb-2 flex items-center justify-between">
                    {statusBadge(project.status)}
                    <span className="text-xs font-medium text-slate-500">{completed}%</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-slate-100">
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
        <div className="fixed inset-0 z-[100] flex items-center justify-center overflow-y-auto bg-slate-950/40 p-4">
          <Card className="w-full max-w-2xl">
            <div className="mb-5 flex items-start justify-between gap-4">
              <div>
                <h3 className="text-xl font-bold text-slate-950">New keyword gap scan</h3>
                <p className="mt-1 text-sm text-slate-500">Enter your website and the main keyword to compare against competitors.</p>
              </div>
              <button
                aria-label="Close"
                className="rounded-lg p-2 text-slate-500 hover:bg-slate-100"
                onClick={() => setShowNewModal(false)}
                type="button"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form className="space-y-4" onSubmit={handleCreate}>
              {createMutation.error && (
                <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                  {createMutation.error.message}
                </div>
              )}

              <div className="grid gap-4 sm:grid-cols-2">
                <label className="block">
                  <span className="mb-1 block text-sm font-medium text-slate-700">Your website</span>
                  <Input
                    onChange={(event) => setForm({ ...form, site_url: event.target.value })}
                    placeholder="https://yourcompany.com"
                    required
                    value={form.site_url}
                  />
                </label>
                <label className="block">
                  <span className="mb-1 block text-sm font-medium text-slate-700">Primary keyword</span>
                  <Input
                    onChange={(event) => setForm({ ...form, primary_keyword: event.target.value })}
                    placeholder="sitemap generator"
                    required
                    value={form.primary_keyword}
                  />
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
