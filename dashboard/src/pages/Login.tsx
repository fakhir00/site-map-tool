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
    <main className="warm-glow-bg flex min-h-screen items-center justify-center bg-abyss px-4 py-12 text-ink">
      <div className="animate-fade-up w-full max-w-sm">
        <a href={websiteUrl} aria-label="CrawlGap homepage" className="mb-8 flex flex-col items-center gap-3">
          <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-glow-amber/15 text-glow-amber ring-1 ring-glow-amber/30 shadow-[0_0_28px_rgba(245,165,36,0.25)]">
            <Map className="h-6 w-6" />
          </span>
          <span className="font-display text-lg font-bold tracking-tight">CrawlGap</span>
        </a>

        <Card className="p-8">
          <div className="mb-7 text-center">
            <h1 className="font-display text-2xl font-bold tracking-tight">Welcome back</h1>
            <p className="mt-2 text-sm leading-6 text-muted">Your projects are waiting — pick up right where you left off.</p>
          </div>

          {DEMO_BACKEND_ENABLED && (
            <div className="mb-5 rounded-xl border border-glow-amber/30 bg-glow-amber/10 px-3 py-2 text-sm text-glow-amber">
              Demo mode is active. Accounts and projects stay in this browser.
            </div>
          )}

          <form className="space-y-4" onSubmit={handleSubmit}>
            {error && (
              <div className="rounded-xl border border-warm-red/30 bg-warm-red/10 px-3 py-2 text-sm text-warm-red">
                {error}
              </div>
            )}

            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-ink">Email</span>
              <div className="relative">
                <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
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
              <span className="mb-1.5 block text-sm font-medium text-ink">Password</span>
              <div className="relative">
                <Lock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
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

            <Button className="w-full" disabled={loading} size="lg" type="submit" variant="glow">
              {loading ? 'Signing in...' : 'Sign in'}
              <ArrowRight className="h-4 w-4" />
            </Button>
          </form>

          <p className="mt-6 text-center text-sm text-muted">
            New here?{' '}
            <Link className="font-semibold text-glow-amber hover:text-[#ffb63d] hover:underline" to="/register">
              Create an account
            </Link>
          </p>
        </Card>

        <p className="mt-6 text-center text-xs text-muted/70">
          Something not working? You can{' '}
          <a href={websiteUrl} className="text-glow-amber/80 hover:text-glow-amber hover:underline">
            head back to the homepage
          </a>{' '}
          any time.
        </p>
      </div>
    </main>
  )
}
