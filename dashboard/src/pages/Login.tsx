import { useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ArrowRight, Lock, Mail, Map } from 'lucide-react'
import { DEMO_BACKEND_ENABLED, api, auth, type User } from '../lib/api'
import { marketingUrl } from '../lib/marketing'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Input } from '../components/ui/Input'

type TokenResponse = {
  access_token: string
  token_type: string
  user: User
}

export function Login() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname || '/'
  const websiteUrl = marketingUrl('/')

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    setLoading(true)

    try {
      const data = await api.post<TokenResponse>('/auth/login', { email, password })
      queryClient.clear()
      auth.setToken(data.access_token)
      navigate(from, { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to sign in')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="min-h-screen bg-slate-50 dark:bg-slate-950 px-4 py-10 text-slate-950 dark:text-slate-50">
      <div className="mx-auto flex min-h-[calc(100vh-5rem)] max-w-6xl items-center">
        <div className="grid w-full gap-8 lg:grid-cols-[1fr_420px] lg:items-center">
          <section className="max-w-2xl">
            <a className="mb-8 inline-flex h-11 w-11 items-center justify-center rounded-lg bg-cyan-700 dark:bg-cyan-600 text-white" href={websiteUrl} aria-label="SiteMapSEO homepage">
              <Map className="h-6 w-6" />
            </a>
            <p className="mb-3 text-sm font-semibold uppercase text-cyan-800 dark:text-cyan-400">SiteMapSEO</p>
            <h1 className="max-w-xl text-4xl font-bold leading-tight text-slate-950 dark:text-slate-50 md:text-5xl">
              Turn competitor sitemaps into content intelligence.
            </h1>
            <p className="mt-5 max-w-xl text-base leading-7 text-slate-600 dark:text-slate-400">
              Scan content URLs, extract keyword opportunities, and keep every project organized in one workspace.
            </p>
          </section>

          <Card className="p-6">
            <div className="mb-6">
              <h2 className="text-xl font-bold text-slate-950 dark:text-slate-50">Sign in</h2>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Access your project dashboard.</p>
            </div>

            {DEMO_BACKEND_ENABLED && (
              <div className="mb-4 rounded-lg border border-amber-200 dark:border-amber-900/50 bg-amber-50 dark:bg-amber-900/20 px-3 py-2 text-sm text-amber-800 dark:text-amber-200">
                Demo mode is active. Accounts and projects stay in this browser.
              </div>
            )}

            <form className="space-y-4" onSubmit={handleSubmit}>
              {error && (
                <div className="rounded-lg border border-rose-200 dark:border-rose-900/50 bg-rose-50 dark:bg-rose-900/20 px-3 py-2 text-sm text-rose-700 dark:text-rose-200">
                  {error}
                </div>
              )}

              <label className="block">
                <span className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">Email</span>
                <div className="relative">
                  <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400 dark:text-slate-500" />
                  <Input
                    autoComplete="email"
                    className="pl-9"
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="you@company.com"
                    required
                    type="email"
                    value={email}
                  />
                </div>
              </label>

              <label className="block">
                <span className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">Password</span>
                <div className="relative">
                  <Lock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400 dark:text-slate-500" />
                  <Input
                    autoComplete="current-password"
                    className="pl-9"
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder="Enter your password"
                    required
                    type="password"
                    value={password}
                  />
                </div>
              </label>

              <Button className="w-full" disabled={loading} type="submit">
                {loading ? 'Signing in...' : 'Sign in'}
                <ArrowRight className="h-4 w-4" />
              </Button>
            </form>

            <p className="mt-6 text-center text-sm text-slate-500 dark:text-slate-400">
              New here?{' '}
              <Link className="font-semibold text-cyan-800 dark:text-cyan-400 hover:text-cyan-900 dark:hover:text-cyan-300" to="/register">
                Create an account
              </Link>
            </p>
          </Card>
        </div>
      </div>
    </main>
  )
}
