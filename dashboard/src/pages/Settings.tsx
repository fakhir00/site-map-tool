import { useQuery } from '@tanstack/react-query'
import { CreditCard, SlidersHorizontal, UserRound } from 'lucide-react'
import { accountQuery } from '../lib/workspaceQueries'
import { Badge } from '../components/ui/Badge'
import { Card } from '../components/ui/Card'

function joinedLabel(createdAt: string | undefined) {
  if (!createdAt) return null
  const d = new Date(createdAt)
  if (Number.isNaN(d.getTime())) return null
  return d.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
}

export function Settings() {
  const { data: user } = useQuery(accountQuery)
  const joined = joinedLabel(user?.created_at)
  const initial = (user?.full_name || user?.email || 'U').charAt(0).toUpperCase()
  const plan = user?.plan || 'free'
  const browserTimeZone = typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone : undefined

  return (
    <div className="page-shell warm-glow-bg">
      <div className="animate-fade-up">
        <h2 className="font-display text-3xl font-bold text-ink">Settings</h2>
        <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted">
          Your account details, your plan, and your preferences — all in one calm place.
        </p>
      </div>

      <div className="mt-8 space-y-5">
        {/* Profile */}
        <section className="animate-fade-up" style={{ animationDelay: '60ms' }}>
          <Card className="p-6 sm:p-8">
            <div className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-glow-amber/10 text-glow-amber">
                <UserRound className="h-5 w-5" />
              </span>
              <div>
                <h3 className="font-display text-xl font-semibold text-ink">Profile</h3>
                <p className="text-sm text-muted">Who you are on CrawlGap.</p>
              </div>
            </div>

            <div className="mt-6 flex items-center gap-4">
              <div className="flex h-16 w-16 items-center justify-center rounded-full border border-glow-amber/30 bg-glow-amber/10 font-display text-2xl font-bold text-glow-amber">
                {initial}
              </div>
              <div>
                <p className="font-display text-lg font-semibold text-ink">{user?.full_name || 'Your name'}</p>
                <p className="text-sm text-muted">{user?.email}</p>
                {joined && <p className="mt-1 text-xs text-muted">Member since {joined}</p>}
              </div>
            </div>

            <div className="mt-6 grid gap-4 border-t border-line pt-6 sm:grid-cols-2">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-muted">Full name</p>
                <p className="mt-1.5 text-sm text-ink">{user?.full_name || 'Not provided'}</p>
              </div>
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-muted">Email</p>
                <p className="mt-1.5 text-sm text-ink">{user?.email}</p>
              </div>
            </div>
          </Card>
        </section>

        {/* Plan */}
        <section className="animate-fade-up" style={{ animationDelay: '120ms' }}>
          <Card className="p-6 sm:p-8">
            <div className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-glow-amber/10 text-glow-amber">
                <CreditCard className="h-5 w-5" />
              </span>
              <div>
                <h3 className="font-display text-xl font-semibold text-ink">Plan</h3>
                <p className="text-sm text-muted">What you're on, and what's included.</p>
              </div>
            </div>

            <div className="mt-6 flex flex-wrap items-center gap-4">
              <p className="font-display text-3xl font-bold capitalize text-ink">{plan}</p>
              <Badge variant={plan === 'free' ? 'slate' : 'teal'}>
                {plan === 'free' ? 'Trial' : 'Active'}
              </Badge>
            </div>
            <p className="mt-3 max-w-xl text-sm leading-relaxed text-muted">
              {plan === 'free'
                ? 'You are trying CrawlGap on the free plan. When you need more scans, keywords, and projects, you can move up anytime.'
                : `You are on the ${plan} plan. Everything included in your plan is available across all your projects.`}
            </p>
          </Card>
        </section>

        {/* Preferences */}
        <section className="animate-fade-up" style={{ animationDelay: '180ms' }}>
          <Card className="p-6 sm:p-8">
            <div className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-soft-violet/10 text-soft-violet">
                <SlidersHorizontal className="h-5 w-5" />
              </span>
              <div>
                <h3 className="font-display text-xl font-semibold text-ink">Preferences</h3>
                <p className="text-sm text-muted">Small touches that make the app feel like yours.</p>
              </div>
            </div>

            <div className="mt-6 divide-y divide-line border-t border-line">
              <div className="flex items-center justify-between gap-4 py-4">
                <div>
                  <p className="text-sm font-medium text-ink">Language</p>
                  <p className="mt-0.5 text-xs text-muted">The language the app speaks to you in.</p>
                </div>
                <Badge variant="slate">English</Badge>
              </div>
              <div className="flex items-center justify-between gap-4 py-4">
                <div>
                  <p className="text-sm font-medium text-ink">Timezone</p>
                  <p className="mt-0.5 text-xs text-muted">Dates and times across the app follow this.</p>
                </div>
                <Badge variant="slate">{browserTimeZone || 'Automatic'}</Badge>
              </div>
              <div className="flex items-center justify-between gap-4 py-4">
                <div>
                  <p className="text-sm font-medium text-ink">Appearance</p>
                  <p className="mt-0.5 text-xs text-muted">CrawlGap is dark, warm, and easy on the eyes.</p>
                </div>
                <Badge variant="indigo">Dark</Badge>
              </div>
            </div>
          </Card>
        </section>
      </div>
    </div>
  )
}
