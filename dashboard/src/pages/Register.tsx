import { useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { DEMO_BACKEND_ENABLED, api, auth, type User } from '../lib/api'
import { marketingUrl } from '../lib/marketing'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'

type TokenResponse = {
  access_token: string
  token_type: string
  user: User
}

/** Drafted sitemap-tree mark: white root node, two solid sky page nodes,
 *  one dashed-amber missing-page node. Pure SVG, no imagery. */
function SitemapMark({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 240 172" className={className} fill="none" role="img" aria-label="CrawlGap sitemap tree mark">
      {/* registration crosshairs */}
      {[
        [16, 16],
        [224, 16],
        [16, 156],
        [224, 156],
      ].map(([x, y]) => (
        <g key={`${x}-${y}`} stroke="#1e3a5f" strokeWidth="2">
          <line x1={x - 6} y1={y} x2={x + 6} y2={y} />
          <line x1={x} y1={y - 6} x2={x} y2={y + 6} />
        </g>
      ))}
      {/* connectors */}
      <line x1="120" y1="62" x2="44" y2="108" stroke="#1e3a5f" strokeWidth="2.5" />
      <line x1="120" y1="62" x2="120" y2="108" stroke="#1e3a5f" strokeWidth="2.5" />
      <line x1="120" y1="62" x2="196" y2="108" stroke="#f5a524" strokeWidth="2.5" strokeDasharray="7 6" />
      {/* root node — white */}
      <rect x="102" y="26" width="36" height="36" rx="7" fill="#eaf2fb" />
      <line x1="110" y1="38" x2="130" y2="38" stroke="#0a1628" strokeWidth="3" strokeLinecap="round" />
      <line x1="110" y1="46" x2="124" y2="46" stroke="#0a1628" strokeWidth="3" strokeLinecap="round" opacity="0.55" />
      {/* existing page nodes — solid sky */}
      <rect x="26" y="108" width="36" height="36" rx="7" fill="#38bdf8" />
      <line x1="34" y1="120" x2="54" y2="120" stroke="#0a1628" strokeWidth="3" strokeLinecap="round" />
      <line x1="34" y1="128" x2="48" y2="128" stroke="#0a1628" strokeWidth="3" strokeLinecap="round" opacity="0.55" />
      <rect x="102" y="108" width="36" height="36" rx="7" fill="#38bdf8" />
      <line x1="110" y1="120" x2="130" y2="120" stroke="#0a1628" strokeWidth="3" strokeLinecap="round" />
      <line x1="110" y1="128" x2="124" y2="128" stroke="#0a1628" strokeWidth="3" strokeLinecap="round" opacity="0.55" />
      {/* missing page node — dashed amber */}
      <rect x="178" y="108" width="36" height="36" rx="7" stroke="#f5a524" strokeWidth="2.5" strokeDasharray="7 5" />
      <text
        x="196"
        y="134"
        textAnchor="middle"
        fontFamily="'JetBrains Mono', monospace"
        fontSize="24"
        fontWeight="600"
        fill="#f5a524"
      >
        +
      </text>
    </svg>
  )
}

function GoogleMark({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#4285F4" d="M23.5 12.3c0-.9-.1-1.5-.3-2.3H12v4.1h6.5c-.1 1.1-.8 2.7-2.4 3.8l-.1.1 3.5 2.7.2.1c2.2-2 3.8-5 3.8-8.5z" />
      <path fill="#34A853" d="M12 24c3.2 0 6-1.1 7.9-2.9l-3.8-2.9c-1 .7-2.4 1.2-4.1 1.2-3.2 0-5.9-2.1-6.8-5l-.1.1-3.6 2.8v.1C3.5 21.4 7.4 24 12 24z" />
      <path fill="#FBBC05" d="M5.2 14.4c-.2-.7-.4-1.5-.4-2.4s.1-1.7.4-2.4l-.1-.1-3.6-2.8-.1.1C.5 8.5 0 10.1 0 12s.5 3.5 1.4 5.1l3.8-2.7z" />
      <path fill="#EA4335" d="M12 4.6c1.8 0 3 .8 3.7 1.4l3.3-3.2C17.9 1.1 15.2 0 12 0 7.4 0 3.5 2.6 1.4 6.9l3.8 2.7c.9-2.9 3.6-5 6.8-5z" />
    </svg>
  );
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
    <main className="min-h-screen bg-ink text-text">
      <div className="mx-auto grid min-h-screen max-w-7xl lg:grid-cols-[1.05fr_480px]">
        {/* Brand panel — the drafting sheet */}
        <section className="bg-blueprint relative hidden overflow-hidden border-r border-line lg:flex lg:flex-col lg:justify-center lg:px-14 xl:px-20">
          <div className="construction-line is-horizontal top-14">
            <span className="dimension">DWG. NO. CG-001</span>
          </div>
          <div className="construction-line is-vertical right-12">
            <span className="dimension">SCALE 1:1</span>
          </div>

          <a href={websiteUrl} className="relative mb-10 inline-flex w-fit items-center gap-3" aria-label="CrawlGap homepage">
            <SitemapMark className="h-11 w-auto" />
            <span className="font-display text-xl font-bold tracking-tight text-text">CrawlGap</span>
          </a>

          <SitemapMark className="relative mb-10 h-auto w-full max-w-md" />

          <p className="annotation relative mb-4">Site office — sheet 01</p>
          <h1 className="relative max-w-lg font-display text-4xl font-bold leading-[1.1] text-text xl:text-5xl">
            Turn competitor sitemaps into <span className="text-amber">content intelligence.</span>
          </h1>
          <p className="relative mt-5 max-w-md text-base leading-7 text-muted">
            Start with your website and main keyword, then export competitor keyword gaps worth acting on.
          </p>

          <div className="relative mt-8 flex items-center gap-4 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
            <span>Seed Finder</span>
            <span className="text-amber">→</span>
            <span>Gap Scan</span>
            <span className="text-amber">→</span>
            <span>Hub-Spoke</span>
          </div>

          <p className="relative mt-8 font-mono text-sm font-semibold uppercase tracking-[0.18em] text-amber">
            One URL in. Your whole architecture out.
          </p>

          <p className="annotation relative mt-10">Drafted at the CrawlGap site office</p>
        </section>

        {/* Register side — the new site permit */}
        <section className="relative flex min-h-screen items-center justify-center px-5 py-12 sm:px-8">
          <div className="w-full max-w-[440px]">
            <a href={websiteUrl} className="mb-8 flex items-center gap-3 lg:hidden" aria-label="CrawlGap homepage">
              <SitemapMark className="h-10 w-auto" />
              <span className="font-display text-lg font-bold text-text">CrawlGap</span>
            </a>

            <div className="spec-plate">
              <div className="px-5 py-6 sm:px-7">
                <div className="mb-6 flex items-start justify-between gap-4">
                  <div>
                    <span className="stamp stamp-green">New permit</span>
                    <h2 className="mt-4 font-display text-2xl font-bold text-text">Create account</h2>
                    <p className="annotation mt-2">Start with a working project dashboard</p>
                  </div>
                  <p className="whitespace-nowrap text-right font-mono text-[10px] uppercase leading-5 tracking-[0.14em] text-muted">
                    Form
                    <br />
                    CG-AUTH-02
                  </p>
                </div>

                {DEMO_BACKEND_ENABLED && (
                  <div className="mb-5 rounded-lg border border-amber/40 bg-amber/10 px-3 py-2 font-mono text-xs leading-5 text-amber">
                    Demo mode is active. Accounts and projects stay in this browser.
                  </div>
                )}

                <form className="space-y-5" onSubmit={handleSubmit}>
                  {error && (
                    <div role="alert" className="rounded-lg border border-red/40 bg-red/10 px-3 py-2 font-mono text-xs leading-5 text-red">
                      {error}
                    </div>
                  )}

                  <label className="block">
                    <span className="annotation mb-2 block uppercase tracking-[0.14em]">Full name</span>
                    <Input
                      autoComplete="name"
                      className="h-11"
                      onChange={(event) => setFullName(event.target.value)}
                      placeholder="Jane Doe"
                      required
                      value={fullName}
                    />
                  </label>

                  <label className="block">
                    <span className="annotation mb-2 block uppercase tracking-[0.14em]">Email</span>
                    <Input
                      autoComplete="email"
                      className="h-11"
                      onChange={(event) => setEmail(event.target.value)}
                      placeholder="you@company.com"
                      required
                      type="email"
                      value={email}
                    />
                  </label>

                  <label className="block">
                    <span className="annotation mb-2 block uppercase tracking-[0.14em]">Password</span>
                    <Input
                      autoComplete="new-password"
                      className="h-11"
                      minLength={8}
                      onChange={(event) => setPassword(event.target.value)}
                      placeholder="Min 8 characters"
                      required
                      type="password"
                      value={password}
                    />
                  </label>

                  <Button className="w-full" disabled={loading} size="lg" type="submit">
                    {loading ? 'Creating...' : 'Create account'}
                    <ArrowRight className="h-4 w-4" />
                  </Button>

                  <div className="flex items-center gap-3" aria-hidden="true">
                    <span className="h-px flex-1 bg-line" />
                    <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted">or</span>
                    <span className="h-px flex-1 bg-line" />
                  </div>

                  <Button className="w-full" type="button" variant="draft">
                    <GoogleMark className="h-4 w-4" />
                    Continue with Google
                  </Button>
                </form>

                <div className="mt-6 flex justify-center">
                  <p className="annotation">No credit card to start · Your first scan is free</p>
                </div>

                <p className="mt-5 text-center text-sm text-muted">
                  Already registered?{' '}
                  <Link className="font-semibold text-amber hover:brightness-110" to="/login">
                    Sign in
                  </Link>
                </p>
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>
  )
}
