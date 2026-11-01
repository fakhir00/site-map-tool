import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, type Project, type ProjectCreate } from '../lib/api'
import { Card } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
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

  return (
    <div className="mx-auto max-w-3xl py-8 space-y-6">
      <div>
        <p className="font-mono text-[0.6875rem] uppercase tracking-[0.14em] text-muted">New survey order</p>
        <h1 className="mt-1 font-display text-2xl font-bold text-text">New Gap Scan</h1>
        <p className="annotation mt-2">Enter your website and the keywords to compare against competitors.</p>
      </div>

      <Card className="p-6">
        <form className="space-y-6" onSubmit={handleCreate}>
          {createMutation.error && (
            <div className="rounded-lg border border-red/50 bg-red/10 px-3 py-2 font-mono text-xs text-red">
              {createMutation.error.message}
            </div>
          )}

          <div className="grid gap-6 sm:grid-cols-2">
            <label className="block">
              <span className="mb-2 block font-mono text-[0.6875rem] uppercase tracking-[0.14em] text-muted">Your website</span>
              <Input
                onChange={(event) => setForm({ ...form, site_url: event.target.value })}
                placeholder="https://yourcompany.com"
                required
                value={form.site_url}
              />
            </label>
            <label className="block">
              <span className="mb-2 block font-mono text-[0.6875rem] uppercase tracking-[0.14em] text-muted">Keywords (comma-separated)</span>
              <Input
                onChange={(event) => setForm({ ...form, primary_keyword: event.target.value })}
                placeholder="sitemap generator, seo tool"
                required
                value={form.primary_keyword}
              />
            </label>
          </div>

          <div className="border-t border-dashed border-line" />

          <div className="grid gap-6 sm:grid-cols-2">
            <label className="block">
              <span className="mb-2 block font-mono text-[0.6875rem] uppercase tracking-[0.14em] text-muted">Competitor search region (Optional)</span>
              <select
                className="flex h-10 w-full rounded-lg border border-line bg-ink px-3 py-2 font-mono text-sm text-text placeholder:text-muted/60 focus:border-amber/70 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
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

          <div className="flex flex-col-reverse gap-3 pt-2 sm:flex-row sm:justify-end">
            <Button disabled={createMutation.isPending} onClick={() => navigate(-1)} type="button" variant="secondary">
              Cancel
            </Button>
            <Button disabled={createMutation.isPending} type="submit">
              {createMutation.isPending ? 'Starting scan...' : 'Find gaps'}
            </Button>
          </div>
        </form>
      </Card>

      <p className="annotation annotation--leading">
        The survey crawls competitor sitemaps, collects AI recommendations and autocomplete suggestions,
        then diffs them against your site to mark the missing pages.
      </p>
    </div>
  )
}
