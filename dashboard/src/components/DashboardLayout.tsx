import { useState } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { BarChart3, Bookmark, ExternalLink, FolderKanban, LogOut, Map, Menu, Network, Plus, Settings, X, Search } from 'lucide-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { DEMO_BACKEND_ENABLED, auth, type Project } from '../lib/api'
import { accountQuery, projectsQuery } from '../lib/workspaceQueries'
import { marketingUrl } from '../lib/marketing'
import { Badge } from './ui/Badge'
import { Button } from './ui/Button'
import { ThemeToggle } from './ThemeToggle'

function statusDot(status: Project['status']) {
  const classes: Record<Project['status'], string> = {
    pending: 'bg-muted',
    running: 'bg-soft-violet',
    paused: 'bg-glow-amber',
    complete: 'bg-alive-green',
    error: 'bg-warm-red',
  }

  return classes[status] || classes.pending
}

const navLinkBase =
  'group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-200'

export function DashboardLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const websiteUrl = marketingUrl('/')

  const account = useQuery(accountQuery)
  const projectList = useQuery(projectsQuery)
  const user = account.data
  const projects = projectList.data || []
  const connectionError = account.error || projectList.error
  const initialLoading = account.isPending || projectList.isPending

  const handleLogout = () => {
    auth.clear()
    queryClient.clear()
    navigate('/login', { replace: true })
  }

  const navItems = [
    { name: 'Projects', href: '/', icon: FolderKanban },
    { name: 'Astro Launchpad', href: '/website-prompts', icon: Plus },
    { name: 'Seed Finder', href: '/gold-hunter', icon: Search },
    { name: 'Gap Scan', href: '/scan', icon: Map },
    { name: 'Hub Spoke', href: '/hub-spoke', icon: Network },
    { name: 'Build Page', href: '/gap-page-prompts', icon: Plus },
    { name: 'Blog Writer', href: '/write-blog', icon: Plus },
    { name: 'Keyword Bank', href: '/saved-keywords', icon: Bookmark },
  ]

  const activeNav = [...navItems]
    .sort((a, b) => b.href.length - a.href.length)
    .find((item) => item.href === '/' ? location.pathname === '/' : location.pathname.startsWith(item.href))
  const sectionLabel = location.pathname.startsWith('/settings') ? 'Settings'
    : location.pathname.startsWith('/projects/') ? 'Project' : (activeNav?.name ?? 'Projects')

  return (
    <div className="flex min-h-screen bg-abyss text-ink">
      {sidebarOpen && (
        <button
          aria-label="Close navigation"
          className="fixed inset-0 z-40 bg-abyss/70 backdrop-blur-sm lg:hidden"
          onClick={() => setSidebarOpen(false)}
          type="button"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-line bg-surface transition-transform duration-300 ease-out lg:static lg:translate-x-0 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <a className="flex h-16 shrink-0 items-center gap-3 border-b border-line px-5 transition-colors hover:bg-raised/60" href={websiteUrl}>
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-glow-amber text-on-accent shadow-[0_0_20px_rgba(245,165,36,0.35)]">
            <Map className="h-5 w-5" />
          </div>
          <div>
            <p className="font-display text-sm font-bold tracking-tight">CrawlGap</p>
            <p className="text-xs text-muted">Content intelligence</p>
          </div>
          <ExternalLink className="ml-auto hidden h-4 w-4 text-muted lg:block" />
        </a>
        <div className="absolute right-4 top-3 lg:hidden">
          <button
            aria-label="Close navigation"
            className="rounded-lg p-2 text-muted transition-colors hover:bg-raised hover:text-ink"
            onClick={() => setSidebarOpen(false)}
            type="button"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-4 py-5">
          <div className="space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon
              const isActive = location.pathname === item.href
              return (
                <Link
                  className={`${navLinkBase} ${
                    isActive
                      ? 'bg-glow-amber/[0.08] text-ink'
                      : 'text-muted hover:bg-raised/80 hover:text-ink'
                  }`}
                  key={item.name}
                  onClick={() => setSidebarOpen(false)}
                  to={item.href}
                >
                  {isActive && (
                    <span className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-glow-amber shadow-[0_0_12px_rgba(245,165,36,0.7)]" />
                  )}
                  <Icon className={`h-4 w-4 ${isActive ? 'text-glow-amber' : 'text-muted group-hover:text-ink'}`} />
                  {item.name}
                </Link>
              )
            })}
          </div>

          <div className="mt-8">
            <div className="mb-2 flex items-center justify-between px-3">
              <p className="font-mono text-[11px] font-semibold uppercase tracking-widest text-muted">Scans</p>
              <Button aria-label="New scan" className="h-7 w-7 p-0" onClick={() => navigate('/')} size="sm" variant="ghost">
                <Plus className="h-4 w-4" />
              </Button>
            </div>

            <div className="space-y-1">
              {projects.slice(0, 8).map((project) => {
                const isActive = location.pathname === `/projects/${project.id}`
                return (
                  <Link
                    className={`${navLinkBase} ${
                      isActive ? 'bg-glow-amber/[0.08] text-ink' : 'text-muted hover:bg-raised/80 hover:text-ink'
                    }`}
                    key={project.id}
                    onClick={() => setSidebarOpen(false)}
                    to={`/projects/${project.id}`}
                  >
                    {isActive && (
                      <span className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-glow-amber shadow-[0_0_12px_rgba(245,165,36,0.7)]" />
                    )}
                    <span className={`h-2 w-2 shrink-0 rounded-full ${statusDot(project.status)}`} />
                    <span className="truncate">{project.name}</span>
                  </Link>
                )
              })}

              {projectList.data === undefined && <p className="px-3 py-2 text-sm text-muted">{projectList.error ? 'Projects unavailable' : 'Loading projects…'}</p>}
              {projectList.isSuccess && projects.length === 0 && <p className="px-3 py-2 text-sm text-muted">No scans yet</p>}
            </div>
          </div>
        </nav>

        <div className="shrink-0 border-t border-line bg-abyss/40 p-4">
          <div className="mb-3 flex items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-glow-amber/15 text-sm font-bold text-glow-amber ring-1 ring-glow-amber/30">
              {(user?.full_name || user?.email || 'U').charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold">{user?.full_name || user?.email || (account.error ? 'Account unavailable' : 'Loading account…')}</p>
              <p className="truncate text-xs text-muted">{user?.email}</p>
            </div>
          </div>
          <Link
            className={`${navLinkBase} mb-1 text-muted hover:bg-raised/80 hover:text-ink`}
            onClick={() => setSidebarOpen(false)}
            to="/settings"
          >
            <Settings className="h-4 w-4" />
            Settings
          </Link>
          <div className="mb-1">
            <ThemeToggle />
          </div>
          <Button className="w-full justify-start" onClick={handleLogout} variant="ghost">
            <LogOut className="h-4 w-4" />
            Sign out
          </Button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 items-center justify-between border-b border-line bg-abyss/80 px-5 backdrop-blur-md lg:hidden">
          <a className="flex items-center gap-3" href={websiteUrl}>
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-glow-amber text-on-accent shadow-[0_0_16px_rgba(245,165,36,0.3)]">
              <Map className="h-4 w-4" />
            </div>
            <span className="font-display text-sm font-bold tracking-tight">CrawlGap</span>
          </a>
          <button
            aria-label="Open navigation"
            className="rounded-lg p-2 text-muted transition-colors hover:bg-raised hover:text-ink"
            onClick={() => setSidebarOpen(true)}
            type="button"
          >
            <Menu className="h-5 w-5" />
          </button>
        </header>

        <main className="warm-glow-bg flex-1 overflow-y-auto">
          <div key={location.pathname} className="route-enter mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
            <div className="mb-6 hidden items-center justify-between lg:flex">
              <div>
                <div className="flex items-center gap-2">
                  <p className="font-mono text-[11px] font-medium uppercase tracking-widest text-muted">{sectionLabel}</p>
                  {DEMO_BACKEND_ENABLED && <Badge variant="amber">Demo mode</Badge>}
                </div>
                <h1 className="font-display text-2xl font-bold tracking-tight">{sectionLabel === 'Projects' ? 'CrawlGap workspace' : sectionLabel}</h1>
              </div>
              <div className="flex items-center gap-2 rounded-xl border border-line bg-surface px-3.5 py-2 text-sm text-muted">
                <BarChart3 className="h-4 w-4 text-glow-amber" />
                {projectList.data === undefined ? (projectList.error ? 'Projects unavailable' : 'Loading projects…') : `${projects.length} active project${projects.length === 1 ? '' : 's'}`}
              </div>
            </div>
            {connectionError ? <div role="alert" className="mb-6 rounded-xl border border-glow-amber/30 bg-glow-amber/[0.06] p-4 text-ink">
              <p className="font-semibold">Could not load {account.error ? 'your account' : 'your projects'}</p>
              <p className="mt-1 text-sm text-muted">{connectionError.message}</p>
              <p className="mt-1 text-sm text-muted">Retrying every 15 seconds. Missing information does not mean your saved data was deleted.</p>
              <Button className="mt-3" variant="secondary" disabled={account.isFetching || projectList.isFetching} onClick={() => { void account.refetch(); void projectList.refetch() }}>Retry connection</Button>
            </div> : initialLoading && <p role="status" className="mb-6 text-sm text-muted">Connecting to your workspace…</p>}
            {user && <Outlet />}
          </div>
        </main>
      </div>
    </div>
  )
}
