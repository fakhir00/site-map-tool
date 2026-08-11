import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, type Project } from '../lib/api'
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
    mutationFn: (body: any) => api.post<Project>('/projects', body),
    onSuccess: (project) => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      navigate(`/projects/${project.id}`)
    },
  })

  const handleCreate = (event: FormEvent) => {
    event.preventDefault()
    const siteUrl = form.site_url.trim()
    const keyword = form.primary_keyword.trim()

    createMutation.mutate({
      name: `${keyword} gaps for ${displayHost(siteUrl)}`,
      domain: siteUrl,
      own_domain: siteUrl,
      scan_frequency: 'once',
      target_keywords: [keyword],
      search_locale: form.search_locale,
    })
  }

  return (
    <div className="mx-auto max-w-3xl py-8">
      <Card className="p-6">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-slate-950">New Gap Hunter</h1>
          <p className="mt-1 text-sm text-slate-500">Enter your website and the main keyword to compare against competitors.</p>
        </div>

        <form className="space-y-6" onSubmit={handleCreate}>
          {createMutation.error && (
            <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
              {createMutation.error.message}
            </div>
          )}

          <div className="grid gap-6 sm:grid-cols-2">
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-slate-700">Your website</span>
              <Input
                onChange={(event) => setForm({ ...form, site_url: event.target.value })}
                placeholder="https://yourcompany.com"
                required
                value={form.site_url}
              />
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-slate-700">Primary keyword</span>
              <Input
                onChange={(event) => setForm({ ...form, primary_keyword: event.target.value })}
                placeholder="sitemap generator"
                required
                value={form.primary_keyword}
              />
            </label>
          </div>

          <div className="grid gap-6 sm:grid-cols-2">
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-slate-700">Competitor search region (Optional)</span>
              <select
                className="flex h-10 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 disabled:cursor-not-allowed disabled:opacity-50"
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

          <div className="flex flex-col-reverse gap-3 pt-4 sm:flex-row sm:justify-end">
            <Button disabled={createMutation.isPending} onClick={() => navigate(-1)} type="button" variant="secondary">
              Cancel
            </Button>
            <Button disabled={createMutation.isPending} type="submit">
              {createMutation.isPending ? 'Starting scan...' : 'Find gaps'}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  )
}
