import { type FormEvent, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, Lock, Mail, Map, UserRound } from 'lucide-react'
import { DEMO_BACKEND_ENABLED, api, type RegisterResult } from '../lib/api'
import { marketingUrl } from '../lib/marketing'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Input } from '../components/ui/Input'

export function Register() {
  const navigate = useNavigate()
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
      const data = await api.post<RegisterResult>('/auth/register', {
        email,
        password,
        full_name: fullName,
      })
      sessionStorage.setItem('pending_verification_email', data.email || email)
      navigate('/payment-proof', {
        replace: true,
        state: { email: data.email || email, fullName },
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create account')
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
            <div className="mb-2 inline-flex items-center gap-1.5 rounded-full border border-glow-amber/30 bg-glow-amber/10 px-3 py-1 text-xs font-medium text-glow-amber">
              <span>Step 1 of 2</span>
              <span>•</span>
              <span>Account Details</span>
            </div>
            <h1 className="font-display text-2xl font-bold tracking-tight">Create your account</h1>
            <p className="mt-2 text-sm leading-6 text-muted">Create your profile, then submit payment proof for approval.</p>
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
              <span className="mb-1.5 block text-sm font-medium text-ink">Full name</span>
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

            <Button className="w-full" disabled={loading} size="lg" type="submit" variant="glow">
              {loading ? 'Creating...' : 'Create account'}
              <ArrowRight className="h-4 w-4" />
            </Button>
          </form>

          <p className="mt-6 text-center text-sm text-muted">
            Already registered?{' '}
            <Link className="font-semibold text-glow-amber hover:text-[#ffb63d] hover:underline" to="/login">
              Sign in
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
