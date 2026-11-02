import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Search, Loader2, Plus, Sparkles, ArrowRight, CalendarDays } from 'lucide-react'
import { api, type Project, type ProjectCreate } from '../lib/api'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Input } from '../components/ui/Input'
import { scrollToTop } from '../lib/utils'

type Seed = {
  keyword: string
  justification: string
}

type GoldHunterScan = {
  id: string
  input_url: string
  audit_summary: string
  seeds: Seed[]
  created_at: string
}

const renderAuditSummary = (summary: string) => {
  try {
    const parsed = JSON.parse(summary)
    if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
      return (
        <div className="grid gap-4 sm:grid-cols-2">
          {Object.entries(parsed).filter(([key]) => key !== 'competitor_profile').map(([key, value]) => (
            <div key={key} className="flex flex-col">
              <span className="font-mono text-[11px] uppercase tracking-wider text-glow-amber/90">{key}</span>
              <span className="mt-1 text-sm text-muted">{String(value)}</span>
            </div>
          ))}
        </div>
      )
    }
  } catch {
    // Fall back to raw text if parsing fails
  }

  return <p className="text-sm text-muted whitespace-pre-wrap">{summary}</p>
}

const withoutCompetitorProfile = (summary: string) => {
  try {
    const parsed = JSON.parse(summary)
    if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
      delete parsed.competitor_profile
      return JSON.stringify(parsed, null, 2)
    }
  } catch {
    // Preserve historical plain-text summaries.
  }
  return summary
}

function hostOf(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url.replace(/^https?:\/\//, '')
  }
}

function SeedEmptyState({ onExplore }: { onExplore: () => void }) {
  return (
    <div className="animate-fade-up py-16 text-center">
      <svg
        aria-hidden="true"
        viewBox="0 0 120 120"
        className="mx-auto h-28 w-28"
      >
        <circle cx="60" cy="60" r="52" fill="rgba(245,165,36,0.08)" />
        <circle cx="60" cy="60" r="38" fill="rgba(245,165,36,0.05)" />
        <ellipse cx="60" cy="84" rx="18" ry="7" fill="#161B26" />
        <ellipse cx="52" cy="80" rx="4.5" ry="3" fill="#F5A524" opacity="0.9" />
        <ellipse cx="64" cy="81" rx="5.5" ry="3.4" fill="#F5A524" opacity="0.7" />
        <ellipse cx="71" cy="79" rx="3.6" ry="2.6" fill="#F5A524" opacity="0.5" />
        <path
          d="M60 76 C60 62 58 52 50 44 M60 76 C60 60 62 50 70 42"
          stroke="#34D399"
          strokeWidth="4"
          strokeLinecap="round"
          fill="none"
        />
        <path
          d="M50 44 C42 42 36 36 34 28 C42 30 48 34 50 44 Z"
          fill="#34D399"
          opacity="0.85"
        />
        <path
          d="M70 42 C78 40 84 34 86 26 C78 28 72 32 70 42 Z"
          fill="#34D399"
          opacity="0.6"
        />
      </svg>
      <h3 className="font-display mt-6 text-xl font-semibold text-ink">Nothing planted yet</h3>
      <p className="mx-auto mt-2 max-w-sm text-sm text-muted">
        Paste any page from your site above and we'll dig out the seed keywords hiding underneath it.
      </p>
      <Button variant="secondary" size="sm" className="mt-5" onClick={onExplore}>
        <Search className="h-4 w-4" />
        Find my first seeds
      </Button>
    </div>
  )
}

function SeedSkeleton() {
  return (
    <div className="space-y-8" aria-hidden="true">
      {[0, 1].map((card) => (
        <div key={card} className="rounded-2xl border border-white/8 bg-surface p-8">
          <div className="animate-shimmer h-5 w-56 rounded-full" />
          <div className="animate-shimmer mt-6 h-24 rounded-xl" />
          <div className="mt-6 space-y-3">
            {[0, 1, 2].map((row) => (
              <div key={row} className="animate-shimmer h-14 rounded-xl" />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export function GoldHunter() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [url, setUrl] = useState('')

  const [error, setError] = useState<string | null>(null)

  const { data: history = [] } = useQuery({
    queryKey: ['goldhunter_history'],
    queryFn: () => api.get<GoldHunterScan[]>('/goldhunter/history'),
  })

  const scanMutation = useMutation({
    mutationFn: (targetUrl: string) => api.postAI<GoldHunterScan>('/goldhunter/scan', { url: targetUrl }),
    onMutate: () => setError(null),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goldhunter_history'] })
      setUrl('')
    },
    onError: (err: Error) => {
      setError(err.message || 'Failed to mine gold from URL')
    }
  })

  const createMutation = useMutation({
    mutationFn: (body: ProjectCreate) => api.post<Project>('/projects', body),
    onMutate: () => setError(null),
    onError: (err: Error) => setError(err.message || 'Failed to create the Gap Scan project'),
    onSuccess: async (project: Project) => {
      try {
        await api.post(`/projects/${project.id}/scan/start`)
      } catch (err) {
        console.error('Failed to auto-start scan:', err)
      }
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      navigate(`/projects/${project.id}`)
    },
  })

  const handleScan = (e: React.FormEvent) => {
    e.preventDefault()
    if (!url.trim()) return
    scanMutation.mutate(url.trim())
  }

  const scanning = scanMutation.isPending

  return (
    <div className="page-shell warm-glow-bg glow-drift">
      {/* Hero — the one place to act */}
      <section className="animate-fade-up mx-auto max-w-2xl pt-8 text-center">
        <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-glow-amber/80">
          Seed Finder
        </p>
        <h1 className="font-display mt-3 text-4xl font-bold leading-tight text-ink sm:text-5xl">
          What should we explore?
        </h1>
        <p className="mt-4 text-base text-muted">
          Drop in any page from your site. Our AI reads it, figures out what it could rank for, and hands you the seed keywords to build on.
        </p>

        <form onSubmit={handleScan} className="relative mt-10">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -inset-4 rounded-[2rem] bg-glow-amber/15 blur-3xl"
          />
          <div className="relative flex flex-col gap-3 sm:flex-row">
            <Input
              className="h-14 flex-1 rounded-2xl border-white/10 bg-raised/90 px-5 text-base shadow-[0_12px_40px_rgba(0,0,0,0.45)] backdrop-blur"
              placeholder="https://yoursite.com/best-page"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              disabled={scanning}
              aria-label="Page URL to explore"
            />
            <Button
              type="submit"
              variant="glow"
              size="lg"
              className="h-14 shrink-0 rounded-2xl px-7 text-base"
              disabled={!url.trim() || scanning}
            >
              {scanning ? (
                <>
                  <Loader2 className="h-5 w-5 animate-spin" />
                  Digging…
                </>
              ) : (
                <>
                  <Sparkles className="h-5 w-5" />
                  Find seeds
                </>
              )}
            </Button>
          </div>
        </form>

        {error && (
          <div className="animate-fade-up mt-6 rounded-xl border border-warm-red/25 bg-warm-red/10 px-5 py-4 text-sm text-warm-red">
            {error}
          </div>
        )}

        {scanning && (
          <p className="animate-fade-up mt-6 text-sm text-muted">
            <span className="inline-flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin text-glow-amber" />
              Reading your page and digging up seed keywords… this takes a moment.
            </span>
          </p>
        )}
      </section>

      {/* Results */}
      <section className="mx-auto mt-16 max-w-3xl">
        {scanning ? (
          <SeedSkeleton />
        ) : history.length === 0 ? (
          <SeedEmptyState onExplore={() => scrollToTop()} />
        ) : (
          <div className="space-y-10">
            <div className="flex items-center justify-between">
              <h2 className="font-display text-2xl font-semibold text-ink">Your finds</h2>
              <Badge variant="amber">
                {history.length} {history.length === 1 ? 'scan' : 'scans'}
              </Badge>
            </div>

            {history.map((scan, scanIndex) => (
              <Card key={scan.id} className={`animate-fade-up p-8 sm:p-10 stagger-${Math.min(scanIndex + 1, 8)}`} >
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <span className="truncate text-base font-semibold text-ink">{hostOf(scan.input_url)}</span>
                  <a
                    href={scan.input_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-sm text-glow-amber/90 hover:text-glow-amber hover:underline"
                  >
                    view page
                    <ArrowRight className="ml-1 inline h-3.5 w-3.5" />
                  </a>
                  <span className="ml-auto inline-flex items-center gap-1.5 text-xs text-muted">
                    <CalendarDays className="h-3.5 w-3.5" />
                    {new Date(scan.created_at).toLocaleString()}
                  </span>
                </div>

                <div className="mt-6 rounded-xl border border-line bg-raised/60 p-5">
                  <p className="font-mono text-[11px] uppercase tracking-wider text-soft-violet">
                    What the AI saw
                  </p>
                  <div className="mt-3">{renderAuditSummary(scan.audit_summary)}</div>
                </div>

                <div className="mt-8">
                  <div className="flex items-center justify-between">
                    <h3 className="font-display text-lg font-semibold text-ink">Seed keywords</h3>
                    <Badge variant="teal">{scan.seeds?.length || 0} seeds</Badge>
                  </div>
                  <ol className="mt-4 space-y-3">
                    {(scan.seeds || []).map((seed, index) => (
                      <li
                        key={seed.keyword}
                        className="flex gap-4 rounded-xl border border-line bg-raised/40 p-4 transition-colors hover:border-glow-amber/30"
                      >
                        <span className="font-mono text-lg font-semibold leading-7 text-glow-amber">
                          {String(index + 1).padStart(2, '0')}
                        </span>
                        <div className="min-w-0">
                          <p className="font-semibold text-ink">{seed.keyword}</p>
                          <p className="mt-1 text-sm leading-relaxed text-muted">{seed.justification}</p>
                        </div>
                      </li>
                    ))}
                  </ol>
                </div>

                <div className="mt-8 flex justify-end border-t border-line pt-6">
                  <Button
                    variant="secondary"
                    size="lg"
                    disabled={createMutation.isPending}
                    onClick={() => {
                      const allKeywords = (scan.seeds || [])
                        .flatMap(s => s.keyword.split(/[,;\n|]+/))
                        .map(keyword => keyword.trim())
                        .filter((keyword, index, items) => Boolean(keyword) && items.indexOf(keyword) === index)
                      if (allKeywords.length === 0) return

                      const siteUrl = scan.input_url
                      const host = new URL(siteUrl).hostname.replace(/^www\./, '')

                      createMutation.mutate({
                        name: `Finding gaps for ${host}`,
                        domain: siteUrl,
                        own_domain: siteUrl,
                        scan_frequency: 'once',
                        target_keywords: allKeywords,
                        audit_summary: withoutCompetitorProfile(scan.audit_summary),
                        search_locale: 'us',
                      })
                    }}
                  >
                    {createMutation.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Plus className="h-4 w-4" />
                    )}
                    Run Gap Scan with {scan.seeds?.length || 0} seeds
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
