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
    pending: 'bg-slate-400',
    running: 'bg-indigo-500',
    paused: 'bg-amber-500',
    complete: 'bg-emerald-500',
    error: 'bg-rose-500',
  }

  return classes[status] || classes.pending
}

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
    <div className="flex min-h-screen bg-slate-50 text-slate-950 dark:bg-slate-950 dark:text-slate-50">
      {sidebarOpen && (
        <button
          aria-label="Close navigation"
          className="fixed inset-0 z-40 bg-slate-950/40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
          type="button"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 transition-transform duration-200 lg:static lg:translate-x-0 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <a className="flex h-16 items-center gap-3 border-b border-slate-200 dark:border-slate-800 px-5 hover:bg-slate-50 dark:hover:bg-slate-800/50" href={websiteUrl}>
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-cyan-700 text-white dark:bg-cyan-600">
            <Map className="h-5 w-5" />
          </div>
          <div>
            <p className="text-sm font-bold text-slate-950 dark:text-slate-50">GapCrawl</p>
            <p className="text-xs text-slate-500 dark:text-slate-400">Content intelligence</p>
          </div>
          <ExternalLink className="ml-auto hidden h-4 w-4 text-slate-400 lg:block" />
        </a>
        <div className="absolute right-4 top-3 lg:hidden">
          <button
            aria-label="Close navigation"
            className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
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
                  className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                    isActive ? 'bg-cyan-50 text-cyan-900 dark:bg-cyan-900/30 dark:text-cyan-400' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-50'
                  }`}
                  key={item.name}
                  onClick={() => setSidebarOpen(false)}
                  to={item.href}
                >
                  <Icon className="h-4 w-4" />
                  {item.name}
                </Link>
              )
            })}
          </div>

          <div className="mt-8">
            <div className="mb-2 flex items-center justify-between px-3">
              <p className="text-xs font-semibold uppercase text-slate-400">Scans</p>
              <Button aria-label="New scan" className="h-7 w-7 p-0" onClick={() => navigate('/')} size="sm" variant="ghost">
                <Plus className="h-4 w-4" />
              </Button>
            </div>

            <div className="space-y-1">
              {projects.slice(0, 8).map((project) => {
                const isActive = location.pathname === `/projects/${project.id}`
                return (
                  <Link
                    className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                      isActive ? 'bg-indigo-50 text-indigo-900 dark:bg-indigo-900/30 dark:text-indigo-400' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-50'
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

              {projectList.data === undefined && <p className="px-3 py-2 text-sm text-slate-500">{projectList.error ? 'Projects unavailable' : 'Loading projects…'}</p>}
              {projectList.isSuccess && projects.length === 0 && <p className="px-3 py-2 text-sm text-slate-500">No scans yet</p>}
            </div>
          </div>
        </nav>

        <div className="border-t border-slate-200 dark:border-slate-800 p-4">
          <div className="mb-3 flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800 text-sm font-bold text-cyan-800 dark:text-cyan-400">
              {(user?.full_name || user?.email || 'U').charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-slate-950 dark:text-slate-50">{user?.full_name || user?.email || (account.error ? 'Account unavailable' : 'Loading account…')}</p>
              <p className="truncate text-xs text-slate-500 dark:text-slate-400">{user?.email}</p>
            </div>
          </div>
          <Link
            className="mb-2 flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-50"
            onClick={() => setSidebarOpen(false)}
            to="/settings"
          >
            <Settings className="h-4 w-4" />
            Settings
          </Link>
          <div className="mb-2">
            <ThemeToggle />
          </div>
          <Button className="w-full justify-start dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700" onClick={handleLogout} variant="secondary">
            <LogOut className="h-4 w-4" />
            Sign out
          </Button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 items-center justify-between border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 px-4 lg:hidden">
          <a className="flex items-center gap-3" href={websiteUrl}>
            <Map className="h-5 w-5 text-cyan-800 dark:text-cyan-500" />
            <span className="text-sm font-bold">SiteMapSEO</span>
          </a>
          <button
            aria-label="Open navigation"
            className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
            onClick={() => setSidebarOpen(true)}
            type="button"
          >
            <Menu className="h-5 w-5" />
          </button>
        </header>

        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
            <div className="mb-6 hidden items-center justify-between lg:flex">
              <div>
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium text-slate-500 dark:text-slate-400">Projects</p>
                  {DEMO_BACKEND_ENABLED && <Badge variant="amber">Demo mode</Badge>}
                </div>
                <h1 className="text-2xl font-bold text-slate-950 dark:text-slate-50">GapCrawl workspace</h1>
              </div>
              <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 px-3 py-2 text-sm text-slate-600 dark:text-slate-300">
                <BarChart3 className="h-4 w-4 text-cyan-800 dark:text-cyan-500" />
                {projectList.data === undefined ? (projectList.error ? 'Projects unavailable' : 'Loading projects…') : `${projects.length} active project${projects.length === 1 ? '' : 's'}`}
              </div>
            </div>
            {connectionError ? <div role="alert" className="mb-6 rounded-lg border border-amber-300 bg-amber-50 p-4 text-amber-950 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-100">
              <p className="font-semibold">Could not load {account.error ? 'your account' : 'your projects'}</p>
              <p className="mt-1 text-sm">{connectionError.message}</p>
              <p className="mt-1 text-sm">Retrying every 15 seconds. Missing information does not mean your saved data was deleted.</p>
              <Button className="mt-3" variant="secondary" disabled={account.isFetching || projectList.isFetching} onClick={() => { void account.refetch(); void projectList.refetch() }}>Retry connection</Button>
            </div> : initialLoading && <p role="status" className="mb-6 text-sm text-slate-500">Connecting to your workspace…</p>}
            {user && <Outlet />}
          </div>
        </main>
      </div>
    </div>
  )
}
