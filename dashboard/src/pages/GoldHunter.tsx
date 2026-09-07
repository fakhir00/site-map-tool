import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Search, Loader2, Clock, Plus } from 'lucide-react'
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

const renderAuditSummary = (summary: string) => {
  try {
    const parsed = JSON.parse(summary)
    if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
      return (
        <div className="grid gap-3 sm:grid-cols-2 text-sm text-slate-700 dark:text-slate-300">
          {Object.entries(parsed).map(([key, value]) => (
            <div key={key} className="flex flex-col">
              <span className="font-semibold text-slate-900 dark:text-slate-50">{key}</span>
              <span>{String(value)}</span>
            </div>
          ))}
        </div>
      )
    }
  } catch {
    // Fall back to raw text if parsing fails
  }

  return <p className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap">{summary}</p>
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

  return (
    <div className="space-y-8">
      <section>
        <h2 className="text-2xl font-bold text-slate-950 dark:text-slate-50">Gold Hunter Agent</h2>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Mine high-value seed keywords from any of your URLs.
        </p>
      </section>

      {error && (
        <div className="rounded-md bg-red-50 dark:bg-red-900/30 p-4 text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      <Card className="p-6">
        <form onSubmit={handleScan} className="flex gap-4">
          <Input
            className="flex-1"
            placeholder="https://example.com/tool-page"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            disabled={scanMutation.isPending}
          />
          <Button type="submit" disabled={!url.trim() || scanMutation.isPending}>
            {scanMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Search className="h-4 w-4" />
            )}
            <span className="ml-2">Mine Gold</span>
          </Button>
        </form>
      </Card>

      {history.length > 0 && (
        <div className="space-y-6">
          <h3 className="text-xl font-bold text-slate-900 dark:text-slate-50">Scan History</h3>
          
          <div className="grid gap-6">
            {history.map((scan) => (
              <Card key={scan.id} className="p-6">
                <div className="flex items-center gap-2 mb-4">
                  <Clock className="h-4 w-4 text-slate-400 dark:text-slate-500" />
                  <span className="text-sm text-slate-500 dark:text-slate-400">
                    {new Date(scan.created_at).toLocaleString()}
                  </span>
                  <span className="text-slate-300 dark:text-slate-700">|</span>
                  <a href={scan.input_url} target="_blank" rel="noreferrer" className="text-sm font-medium text-cyan-700 dark:text-cyan-400 hover:underline">
                    {scan.input_url}
                  </a>
                </div>

                <div className="mb-6 rounded-lg bg-slate-50 dark:bg-slate-900/50 p-4 border border-slate-100 dark:border-slate-800">
                  <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-50 mb-2">Agent Audit Summary</h4>
                  {renderAuditSummary(scan.audit_summary)}
                </div>

                <div className="mt-4 flex justify-end">
                  <Button 
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
                        audit_summary: scan.audit_summary,
                        search_locale: 'us',
                      })
                    }}
                  >
                    {createMutation.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    ) : (
                      <Plus className="h-4 w-4 mr-2" />
                    )}
                    Gap Hunter
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
