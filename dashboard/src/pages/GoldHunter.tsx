import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Crosshair, Loader2, Plus } from 'lucide-react'
import { api, type Project, type ProjectCreate } from '../lib/api'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Input } from '../components/ui/Input'

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

const hostOf = (rawUrl: string) => {
  try {
    return new URL(rawUrl).hostname.replace(/^www\./, '')
  } catch {
    return rawUrl
  }
}

const renderAuditSummary = (summary: string) => {
  try {
    const parsed = JSON.parse(summary)
    if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
      return (
        <div className="grid gap-3 sm:grid-cols-2 text-sm">
          {Object.entries(parsed).filter(([key]) => key !== 'competitor_profile').map(([key, value]) => (
            <div key={key} className="flex flex-col gap-1">
              <span className="font-mono text-[0.6875rem] uppercase tracking-[0.14em] text-muted">{key}</span>
              <span className="text-text">{String(value)}</span>
            </div>
          ))}
        </div>
      )
    }
  } catch {
    // Fall Back to raw text if parsing fails
  }

  return <p className="whitespace-pre-wrap text-sm text-muted">{summary}</p>
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

  const latest = history[0]
  const latestSeeds = latest?.seeds ?? []
  const isScanning = scanMutation.isPending

  return (
    <div className="space-y-8">
      {/* Header — instrument plate title */}
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-3">
          <p className="font-mono text-[0.6875rem] uppercase tracking-[0.18em] text-muted">
            ▸ FIELD INSTRUMENT / SITE SURVEY
          </p>
          <h2 className="font-display text-3xl font-bold text-text">Seed Finder</h2>
          <p className="annotation max-w-xl">
            Drive a survey stake into any page and pull the seed keywords it can rank for —
            numbered, justified, ready for a Gap Scan.
          </p>
        </div>
        <span className="stamp stamp-amber">Survey</span>
      </header>

      {error && (
        <div className="rounded-lg border-2 border-red/70 bg-red/10 p-4 font-mono text-sm text-red">
          ▸ {error}
        </div>
      )}

      {/* Survey line */}
      <div className="relative h-6" aria-hidden="true">
        <div className="construction-line is-horizontal">
          <span className="dimension">SURVEY LINE · 01</span>
        </div>
      </div>

      {/* Instrument plate — big centered URL input */}
      <section className="mx-auto w-full max-w-2xl">
        <form onSubmit={handleScan} className="spec-plate p-6 sm:p-8">
          <label htmlFor="seed-finder-url" className="spec-label">
            ▸ SITE TO SURVEY
          </label>
          <div className="mt-3 flex flex-col gap-3 sm:flex-row">
            <Input
              id="seed-finder-url"
              className="h-12 flex-1 text-base"
              placeholder="Paste a page URL to survey…"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              disabled={isScanning}
            />
            <Button type="submit" size="lg" className="shrink-0" disabled={!url.trim() || isScanning}>
              {isScanning ? (
                <Loader2 className="h-5 w-5 animate-spin" />
              ) : (
                <Crosshair className="h-5 w-5" />
              )}
              Find seeds
            </Button>
          </div>
          <p className="annotation mt-4">
            The surveyor reads the page, audits what it targets, and stakes the strongest
            seed keywords into the sheet below.
          </p>
        </form>
      </section>

      {/* Loading skeleton — blueprint grid + dashed instrument outline */}
      {isScanning && (
        <section className="bg-blueprint rounded-2xl border border-line p-8">
          <p className="font-mono text-xs uppercase tracking-[0.18em] text-amber animate-pulse">
            ▸ SURVEYING SITE…
          </p>
          <div className="mt-6 grid gap-3 md:grid-cols-2">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="dashed-amber rounded-lg p-4 animate-pulse">
                <div className="h-7 w-10 rounded bg-line/70" />
                <div className="mt-3 h-5 w-3/4 rounded bg-line/50" />
                <div className="mt-3 space-y-2">
                  <div className="h-3 w-full rounded bg-line/40" />
                  <div className="h-3 w-5/6 rounded bg-line/40" />
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Results — latest scan as numbered survey stakes */}
      {!isScanning && latest && (
        <section className="space-y-8">
          <Card className="p-6 sm:p-8">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="space-y-2">
                <p className="font-mono text-[0.6875rem] uppercase tracking-[0.18em] text-muted">
                  ▸ SURVEY RESULT — LATEST SHEET
                </p>
                <h3 className="font-display text-2xl font-bold text-text">
                  {latestSeeds.length} {latestSeeds.length === 1 ? 'seed' : 'seeds'} found for{' '}
                  <span className="font-mono text-amber">{hostOf(latest.input_url)}</span>
                </h3>
                <p className="annotation">
                  {new Date(latest.created_at).toLocaleString()} · {latest.input_url}
                </p>
              </div>
              <span className="stamp stamp-green">Staked</span>
            </div>

            <div className="mt-6 rounded-xl border border-line bg-ink p-4 sm:p-5">
              <p className="font-mono text-[0.6875rem] uppercase tracking-[0.14em] text-muted">
                ▸ FIELD NOTES — AGENT AUDIT
              </p>
              <div className="mt-3">{renderAuditSummary(latest.audit_summary)}</div>
            </div>

            <div className="mt-6 grid gap-3 md:grid-cols-2">
              {latestSeeds.map((seed, index) => (
                <div
                  key={seed.keyword}
                  className="rounded-lg border border-line bg-raised p-4 transition-colors hover:border-amber/40"
                >
                  <div className="flex items-baseline gap-3">
                    <span className="font-mono text-2xl font-semibold text-amber">
                      {String(index + 1).padStart(2, '0')}
                    </span>
                    <p className="font-mono text-lg font-semibold text-text break-words">
                      {seed.keyword}
                    </p>
                  </div>
                  <p className="annotation mt-3">{seed.justification}</p>
                </div>
              ))}
            </div>

            <div className="mt-6 flex justify-end">
              <Button
                variant="draft"
                disabled={createMutation.isPending}
                onClick={() => {
                  const allKeywords = latestSeeds
                    .flatMap(s => s.keyword.split(/[,;\n|]+/))
                    .map(keyword => keyword.trim())
                    .filter((keyword, index, items) => Boolean(keyword) && items.indexOf(keyword) === index)
                  if (allKeywords.length === 0) return

                  const siteUrl = latest.input_url
                  const host = new URL(siteUrl).hostname.replace(/^www\./, '')

                  createMutation.mutate({
                    name: `Finding gaps for ${host}`,
                    domain: siteUrl,
                    own_domain: siteUrl,
                    scan_frequency: 'once',
                    target_keywords: allKeywords,
                    audit_summary: withoutCompetitorProfile(latest.audit_summary),
                    search_locale: 'us',
                  })
                }}
              >
                {createMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Plus className="h-4 w-4" />
                )}
                Run Gap Scan with {latestSeeds.length} seeds
              </Button>
            </div>
          </Card>

          {/* Field log — hairline-ruled ledger of every scan */}
          <div>
            <p className="font-mono text-[0.6875rem] uppercase tracking-[0.18em] text-muted">
              ▸ FIELD LOG
            </p>
            <div className="mt-3 overflow-hidden rounded-xl border border-line bg-panel">
              {history.map((scan, index) => (
                <div
                  key={scan.id}
                  className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-line px-4 py-3 font-mono text-xs last:border-b-0 hover:bg-raised/60"
                >
                  <span className="text-muted">{new Date(scan.created_at).toLocaleString()}</span>
                  <a
                    href={scan.input_url}
                    target="_blank"
                    rel="noreferrer"
                    className="max-w-full truncate text-text hover:text-amber hover:underline"
                  >
                    {scan.input_url}
                  </a>
                  <span className="ml-auto text-amber">{scan.seeds?.length || 0} seeds</span>
                  {index === 0 && (
                    <span className="text-[0.625rem] uppercase tracking-[0.14em] text-green">
                      ▸ latest
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* Empty state — blueprint grid + dashed instrument skeleton */}
      {!isScanning && !latest && (
        <section className="bg-blueprint rounded-2xl border border-dashed border-line p-12 text-center">
          <p className="font-mono text-xs uppercase tracking-[0.18em] text-muted">
            ▸ NO SURVEYS ON RECORD
          </p>
          <div className="dashed-amber mx-auto mt-8 max-w-md rounded-lg p-6">
            <div className="h-4 w-40 rounded bg-line/70" />
            <div className="mt-4 h-12 rounded bg-line/40" />
            <div className="mt-4 flex justify-center">
              <div className="h-10 w-36 rounded bg-line/50" />
            </div>
          </div>
          <p className="annotation mx-auto mt-8 max-w-md text-left">
            Point the instrument at a page above and press Find seeds — staked results will
            be pinned to this sheet.
          </p>
        </section>
      )}
    </div>
  )
}
