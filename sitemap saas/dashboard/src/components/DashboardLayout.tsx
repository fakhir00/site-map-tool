import { useState } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { BarChart3, ExternalLink, FolderKanban, LogOut, Map, Menu, Plus, Settings, X } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { api, auth, type Project, type User } from '../lib/api'
import { marketingUrl } from '../lib/marketing'
import { Button } from './ui/Button'

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
  const websiteUrl = marketingUrl('/')

  const { data: user } = useQuery({
    queryKey: ['user'],
    queryFn: () => api.get<User>('/auth/me'),
  })

  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => api.get<Project[]>('/projects'),
  })

  const handleLogout = () => {
    auth.clear()
    navigate('/login', { replace: true })
  }

  const navItems = [
    { name: 'Projects', href: '/', icon: FolderKanban },
    { name: 'Settings', href: '/settings', icon: Settings },
  ]

  return (
    <div className="flex min-h-screen bg-slate-50 text-slate-950">
      {sidebarOpen && (
        <button
          aria-label="Close navigation"
          className="fixed inset-0 z-40 bg-slate-950/40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
          type="button"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-slate-200 bg-white transition-transform duration-200 lg:static lg:translate-x-0 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <a className="flex h-16 items-center gap-3 border-b border-slate-200 px-5 hover:bg-slate-50" href={websiteUrl}>
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-cyan-700 text-white">
            <Map className="h-5 w-5" />
          </div>
          <div>
            <p className="text-sm font-bold text-slate-950">SiteMapSEO</p>
            <p className="text-xs text-slate-500">Content intelligence</p>
          </div>
          <ExternalLink className="ml-auto hidden h-4 w-4 text-slate-400 lg:block" />
        </a>
        <div className="absolute right-4 top-3 lg:hidden">
          <button
            aria-label="Close navigation"
            className="rounded-lg p-2 text-slate-500 hover:bg-slate-100"
            onClick={() => setSidebarOpen(false)}
            type="button"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-4 py-5">
          <div className="space-y-1">
            <a
              className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-950"
              href={websiteUrl}
              onClick={() => setSidebarOpen(false)}
            >
              <Map className="h-4 w-4" />
              Website
              <ExternalLink className="ml-auto h-3.5 w-3.5 text-slate-400" />
            </a>
            {navItems.map((item) => {
              const Icon = item.icon
              const isActive = location.pathname === item.href
              return (
                <Link
                  className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                    isActive ? 'bg-cyan-50 text-cyan-900' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-950'
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
                      isActive ? 'bg-indigo-50 text-indigo-900' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-950'
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

              {projects.length === 0 && <p className="px-3 py-2 text-sm text-slate-500">No scans yet</p>}
            </div>
          </div>
        </nav>

        <div className="border-t border-slate-200 p-4">
          <div className="mb-3 flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-100 text-sm font-bold text-cyan-800">
              {(user?.full_name || user?.email || 'U').charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-slate-950">{user?.full_name || 'User'}</p>
              <p className="truncate text-xs text-slate-500">{user?.email}</p>
            </div>
          </div>
          <Button className="w-full justify-start" onClick={handleLogout} variant="secondary">
            <LogOut className="h-4 w-4" />
            Sign out
          </Button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 items-center justify-between border-b border-slate-200 bg-white px-4 lg:hidden">
          <a className="flex items-center gap-3" href={websiteUrl}>
            <Map className="h-5 w-5 text-cyan-800" />
            <span className="text-sm font-bold">SiteMapSEO</span>
          </a>
          <button
            aria-label="Open navigation"
            className="rounded-lg p-2 text-slate-600 hover:bg-slate-100"
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
                <p className="text-sm font-medium text-slate-500">Dashboard</p>
                <h1 className="text-2xl font-bold text-slate-950">SEO scan workspace</h1>
              </div>
              <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600">
                <BarChart3 className="h-4 w-4 text-cyan-800" />
                {projects.length} active project{projects.length === 1 ? '' : 's'}
              </div>
            </div>
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
