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
    running: 'bg-sky',
    paused: 'bg-amber',
    complete: 'bg-green',
    error: 'bg-red',
  }

  return classes[status] || classes.pending
}

/* Active chrome item — a clipped amber tag: amber left-edge clip + amber-tinted sheet. */
const activeChromeItem =
  'border-l-2 border-amber bg-amber/10 text-amber'
const idleChromeItem =
  'border-l-2 border-transparent text-muted hover:border-line hover:bg-raised hover:text-text'

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

  return (
    <div className="flex min-h-screen bg-ink text-text">
      {sidebarOpen && (
        <button
          aria-label="Close navigation"
          className="fixed inset-0 z-40 bg-ink/70 lg:hidden"
          onClick={() => setSidebarOpen(false)}
          type="button"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-line bg-ink transition-transform duration-200 lg:static lg:translate-x-0 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Logo plate — wordmark text untouched */}
        <a className="flex h-16 items-center gap-3 border-b border-line px-5 hover:bg-raised" href={websiteUrl}>
          <div className="flex h-9 w-9 items-center justify-center border border-amber/60 bg-amber/10 text-amber">
            <Map className="h-5 w-5" />
          </div>
          <div>
            <p className="font-display text-sm font-bold text-text">CrawlGap</p>
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted">Content intelligence</p>
          </div>
          <ExternalLink className="ml-auto hidden h-4 w-4 text-muted lg:block" />
        </a>
        <div className="absolute right-4 top-3 lg:hidden">
          <button
            aria-label="Close navigation"
            className="rounded-lg p-2 text-muted hover:bg-raised hover:text-text"
            onClick={() => setSidebarOpen(false)}
            type="button"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-4 py-5">
          <p className="annotation mb-2 uppercase tracking-[0.2em]">Modules</p>
          <div className="space-y-1">
            {navItems.map((item, index) => {
              const Icon = item.icon
              const isActive = location.pathname === item.href
              return (
                <Link
                  className={`flex items-center gap-3 rounded-r-md py-2 pl-3 pr-3 text-sm font-medium transition-colors ${
                    isActive ? activeChromeItem : idleChromeItem
                  }`}
                  key={item.name}
                  onClick={() => setSidebarOpen(false)}
                  to={item.href}
                >
                  <span className="font-mono text-[10px] tracking-[0.12em] opacity-60">
                    {String(index + 1).padStart(2, '0')}
                  </span>
                  <Icon className="h-4 w-4" />
                  {item.name}
                </Link>
              )
            })}
          </div>

          <div className="mt-8">
            <div className="mb-2 flex items-center justify-between">
              <p className="annotation uppercase tracking-[0.2em]">Scans</p>
              <Button aria-label="New scan" className="h-7 w-7 p-0" onClick={() => navigate('/')} size="sm" variant="draft">
                <Plus className="h-4 w-4" />
              </Button>
            </div>

            <div className="space-y-1">
              {projects.slice(0, 8).map((project) => {
                const isActive = location.pathname === `/projects/${project.id}`
                return (
                  <Link
                    className={`flex items-center gap-3 rounded-r-md py-2 pl-3 pr-3 text-sm transition-colors ${
                      isActive ? activeChromeItem : idleChromeItem
                    }`}
                    key={project.id}
                    onClick={() => setSidebarOpen(false)}
                    to={`/projects/${project.id}`}
                  >
                    <span className={`h-2 w-2 rounded-full ${statusDot(project.status)}`} />
                    <span className="truncate">{project.name}</span>
                  </Link>
                )
              })}

              {projectList.data === undefined && <p className="py-2 pl-3 pr-3 font-mono text-xs text-muted">{projectList.error ? 'Projects unavailable' : 'Loading projects…'}</p>}
              {projectList.isSuccess && projects.length === 0 && <p className="py-2 pl-3 pr-3 font-mono text-xs text-muted">No scans yet</p>}
            </div>
          </div>
        </nav>

        {/* Name plate */}
        <div className="border-t border-line p-4">
          <div className="mb-3 flex items-center gap-3 border border-line bg-panel px-3 py-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-full border border-amber/50 bg-amber/10 text-sm font-bold text-amber">
              {(user?.full_name || user?.email || 'U').charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-text">{user?.full_name || user?.email || (account.error ? 'Account unavailable' : 'Loading account…')}</p>
              <p className="truncate font-mono text-[11px] text-muted">{user?.email}</p>
            </div>
          </div>
          <Link
            className={`mb-2 flex items-center gap-3 rounded-r-md py-2 pl-3 pr-3 text-sm font-medium transition-colors ${
              location.pathname === '/settings' ? activeChromeItem : idleChromeItem
            }`}
            onClick={() => setSidebarOpen(false)}
            to="/settings"
          >
            <Settings className="h-4 w-4" />
            Settings
          </Link>
          <Button className="w-full justify-start" onClick={handleLogout} variant="secondary">
            <LogOut className="h-4 w-4" />
            Sign out
          </Button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile topbar */}
        <header className="flex h-16 items-center justify-between border-b border-line bg-ink px-4 lg:hidden">
          <a className="flex items-center gap-3" href={websiteUrl}>
            <Map className="h-5 w-5 text-amber" />
            <span className="font-display text-sm font-bold text-text">CrawlGap</span>
          </a>
          <div className="flex items-center gap-2">
            <ThemeToggle compact />
            <button
              aria-label="Open navigation"
              className="rounded-lg p-2 text-muted hover:bg-raised hover:text-text"
              onClick={() => setSidebarOpen(true)}
              type="button"
            >
              <Menu className="h-5 w-5" />
            </button>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
            {/* Desktop page context */}
            <div className="mb-6 hidden items-center justify-between border-b border-line pb-5 lg:flex">
              <div>
                <div className="flex items-center gap-2">
                  <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-muted">Projects</p>
                  {DEMO_BACKEND_ENABLED && <Badge variant="amber">Demo mode</Badge>}
                </div>
                <h1 className="font-display text-2xl font-bold text-text">CrawlGap workspace</h1>
              </div>
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2 border border-line bg-panel px-3 py-2 text-sm text-muted">
                  <BarChart3 className="h-4 w-4 text-amber" />
                  {projectList.data === undefined ? (projectList.error ? 'Projects unavailable' : 'Loading projects…') : `${projects.length} active project${projects.length === 1 ? '' : 's'}`}
                </div>
                <ThemeToggle compact />
              </div>
            </div>
            {connectionError ? <div role="alert" className="mb-6 border border-amber/50 bg-amber/10 p-4 text-text">
              <p className="font-display font-semibold">Could not load {account.error ? 'your account' : 'your projects'}</p>
              <p className="mt-1 text-sm text-muted">{connectionError.message}</p>
              <p className="mt-1 font-mono text-xs text-muted">Retrying every 15 seconds. Missing information does not mean your saved data was deleted.</p>
              <Button className="mt-3" variant="secondary" disabled={account.isFetching || projectList.isFetching} onClick={() => { void account.refetch(); void projectList.refetch() }}>Retry connection</Button>
            </div> : initialLoading && <p role="status" className="mb-6 font-mono text-xs text-muted">Connecting to your workspace…</p>}
            {user && <Outlet />}
          </div>
        </main>
      </div>
    </div>
  )
}
