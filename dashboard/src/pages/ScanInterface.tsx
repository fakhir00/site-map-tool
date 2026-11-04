import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, ChevronDown, Radar, Sparkles } from 'lucide-react'
import { api, type Project, type ProjectCreate } from '../lib/api'
import { Card } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Badge } from '../components/ui/Badge'
import { Input } from '../components/ui/Input'

function displayHost(value: string) {
  try {
    const withScheme = value.startsWith('http://') || value.startsWith('https://') ? value : `https://${value}`
    return new URL(withScheme).hostname.replace(/^www\./, '')
  } catch {
    return value.replace(/^https?:\/\//, '')
  }
}

export default function ScanInterface() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [form, setForm] = useState({
    site_url: '',
    primary_keyword: '',
    search_locale: 'us',
  })

  const createMutation = useMutation({
    mutationFn: (body: ProjectCreate) => api.post<Project>('/projects', body),
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

  const handleCreate = (event: FormEvent) => {
    event.preventDefault()
    const siteUrl = form.site_url.trim()
    const rawKeywords = form.primary_keyword.split(',').map(k => k.trim()).filter(k => k.length > 0)

    if (rawKeywords.length === 0) {
      alert("Please enter at least one keyword")
      return
    }

    createMutation.mutate({
      name: `Finding gaps for ${displayHost(siteUrl)}`,
      domain: siteUrl,
      own_domain: siteUrl,
      scan_frequency: 'once',
      target_keywords: rawKeywords,
      search_locale: form.search_locale,
    })
  }

  const keywordPreview = form.primary_keyword.split(',').map(k => k.trim()).filter(k => k.length > 0)
  const isStarting = createMutation.isPending

  return (
    <div className="page-shell warm-glow-bg">
      <div className="mx-auto max-w-2xl space-y-10">
        {/* Hero — one confident focal point */}
        <div className="animate-fade-up pt-4 text-center">
          <Badge variant="amber" className="mb-4">
            <Radar className="mr-1.5 h-3.5 w-3.5" />
            Gap Scan
          </Badge>
          <h1 className="font-display text-4xl font-bold tracking-tight text-ink sm:text-5xl">
            Find content gaps.
          </h1>
          <p className="mx-auto mt-4 max-w-md text-base leading-relaxed text-muted">
            Drop in your site and the keywords you want to own. We'll stack your sitemap
            against your competitors' and surface the pages you're missing.
          </p>
        </div>

        {/* Form — the single thing to do */}
        <Card className="animate-fade-up p-8 sm:p-10" style={{ animationDelay: '80ms' }}>
          <form className="space-y-7" onSubmit={handleCreate}>
            {createMutation.error && (
              <div className="flex items-start gap-2.5 rounded-xl border border-warm-red/30 bg-warm-red/10 px-4 py-3 text-sm text-warm-red">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{createMutation.error.message}</span>
              </div>
            )}

            <label className="block">
              <span className="mb-2.5 block text-sm font-semibold text-ink">Your website</span>
              <Input
                className="h-12 text-base"
                onChange={(event) => setForm({ ...form, site_url: event.target.value })}
                placeholder="https://yourcompany.com"
                required
                value={form.site_url}
              />
            </label>

            <label className="block">
              <span className="mb-2.5 block text-sm font-semibold text-ink">
                Keywords you want to rank for
              </span>
              <Input
                className="h-12 text-base"
                onChange={(event) => setForm({ ...form, primary_keyword: event.target.value })}
                placeholder="sitemap generator, seo audit tool"
                required
                value={form.primary_keyword}
              />
              {keywordPreview.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {keywordPreview.map((keyword) => (
                    <Badge key={keyword} variant="slate">
                      {keyword}
                    </Badge>
                  ))}
                </div>
              )}
            </label>

            {/* Progressive disclosure — options stay out of the way */}
            <details className="rounded-xl border border-line bg-abyss/40 px-4 py-3">
              <summary className="flex cursor-pointer list-none items-center justify-between text-sm font-medium text-muted transition-colors hover:text-ink [&::-webkit-details-marker]:hidden">
                <span>Scan options</span>
                <ChevronDown className="disclosure-chevron h-4 w-4" />
              </summary>
              <div className="disclosure"><div>
              <div className="pt-4">
                <label className="block">
                  <span className="mb-2 block text-sm font-medium text-muted">Competitor search region</span>
                  <select
                    className="flex h-10 w-full rounded-xl border border-line bg-raised px-3 py-2 text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-glow-amber/40 focus-visible:border-glow-amber/60"
                    onChange={(event) => setForm({ ...form, search_locale: event.target.value })}
                    value={form.search_locale}
                  >
                    <option value="us">United States (Default)</option>
                    <option value="gb">United Kingdom</option>
                    <option value="ca">Canada</option>
                    <option value="au">Australia</option>
                    <option value="in">India</option>
                    <option value="de">Germany</option>
                    <option value="fr">France</option>
                  </select>
                </label>
              </div>
              </div></div>
            </details>

            {/* One primary action; everything else is quiet */}
            <div className="flex flex-col-reverse gap-3 pt-2 sm:flex-row sm:items-center sm:justify-end">
              <Button disabled={isStarting} onClick={() => navigate(-1)} type="button" variant="ghost">
                Cancel
              </Button>
              <Button disabled={isStarting} size="lg" type="submit" variant="glow" className="sm:min-w-44">
                {isStarting ? 'Starting scan…' : 'Find gaps'}
              </Button>
            </div>
          </form>
        </Card>

        {/* Warm scan-progress state while the scan spins up */}
        {isStarting && (
          <Card className="animate-fade-up space-y-4 p-6">
            <div className="flex items-center gap-2.5">
              <Sparkles className="h-5 w-5 text-glow-amber" />
              <p className="text-sm font-medium text-ink">
                Spinning up your scan — discovering competitors and reading their sitemaps.
              </p>
            </div>
            <div className="space-y-2.5" aria-hidden="true">
              <div className="animate-shimmer h-3.5 w-3/4 rounded-full" />
              <div className="animate-shimmer h-3.5 w-1/2 rounded-full" />
              <div className="animate-shimmer h-3.5 w-2/3 rounded-full" />
            </div>
            <p className="text-xs text-muted">This usually takes under a minute. Hang tight.</p>
          </Card>
        )}
      </div>
    </div>
  )
}
