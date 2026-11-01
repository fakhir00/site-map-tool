import { useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, Lock, Mail, Map, UserRound } from 'lucide-react'
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

export function Register() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const websiteUrl = marketingUrl('/')

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    setLoading(true)

    try {
      const data = await api.post<TokenResponse>('/auth/register', {
        email,
        password,
        full_name: fullName,
      })
      queryClient.clear()
      auth.setToken(data.access_token)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create account')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="min-h-screen bg-blueprint-deep px-4 py-10 font-sans text-text">
      <div className="mx-auto flex min-h-[calc(100vh-5rem)] max-w-6xl items-center">
        <div className="grid w-full gap-10 lg:grid-cols-[1fr_420px] lg:items-center">
          <section className="max-w-2xl">
            <a className="mb-8 inline-flex h-11 w-11 items-center justify-center rounded-xl border border-line bg-raised text-site-sky" href={websiteUrl} aria-label="CrawlGap homepage">
              <Map className="h-6 w-6" />
            </a>
            <p className="mb-3 text-sm font-semibold uppercase tracking-widest text-site-sky">CrawlGap</p>
            <h1 className="max-w-xl font-display text-4xl font-bold leading-tight text-text md:text-5xl">
              Build your SEO discovery workspace.
            </h1>
            <p className="mt-5 max-w-xl text-base leading-7 text-muted">
              Start with your website and main keyword, then export competitor keyword gaps worth acting on.
            </p>
          </section>

          <Card className="p-6">
            <div className="mb-6">
              <h2 className="font-display text-xl font-bold text-text">Create account</h2>
              <p className="mt-1 text-sm text-muted">Start with a working project dashboard.</p>
            </div>

            {DEMO_BACKEND_ENABLED && (
              <div className="mb-4 rounded-lg border border-signal-amber/40 bg-signal-amber/10 px-3 py-2 text-sm text-signal-amber">
                Demo mode is active. Accounts and projects stay in this browser.
              </div>
            )}

            <form className="space-y-4" onSubmit={handleSubmit}>
              {error && (
                <div className="rounded-lg border border-signal-red/40 bg-signal-red/10 px-3 py-2 text-sm text-signal-red">
                  {error}
                </div>
              )}

              <label className="block">
                <span className="mb-1 block text-sm font-medium text-text">Full name</span>
                <div className="relative">
                  <UserRound className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
                  <Input
                    autoComplete="name"
                    className="pl-9"
                    onChange={(event) => setFullName(event.target.value)}
                    placeholder="Jane Doe"
                    required
                    value={fullName}
                  />
                </div>
              </label>

              <label className="block">
                <span className="mb-1 block text-sm font-medium text-text">Email</span>
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
                <span className="mb-1 block text-sm font-medium text-text">Password</span>
                <div className="relative">
                  <Lock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
                  <Input
                    autoComplete="new-password"
                    className="pl-9"
                    minLength={8}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder="Min 8 characters"
                    required
                    type="password"
                    value={password}
                  />
                </div>
              </label>

              <Button className="w-full" disabled={loading} type="submit">
                {loading ? 'Creating...' : 'Create account'}
                <ArrowRight className="h-4 w-4" />
              </Button>
            </form>

            <p className="mt-6 text-center text-xs text-muted">
              No credit card to start · Your first scan is free
            </p>

            <p className="mt-4 text-center text-sm text-muted">
              Already registered?{' '}
              <Link className="font-semibold text-site-sky hover:text-site-sky/80" to="/login">
                Sign in
              </Link>
            </p>
          </Card>
        </div>
      </div>
    </main>
  )
}
