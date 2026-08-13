import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Search, Loader2, Clock, Plus } from 'lucide-react'
import { api } from '../lib/api'
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
    mutationFn: (targetUrl: string) => api.post<GoldHunterScan>('/goldhunter/scan', { url: targetUrl }),
    onMutate: () => setError(null),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goldhunter_history'] })
      setUrl('')
    },
    onError: (err: any) => {
      setError(err.message || 'Failed to mine gold from URL')
    }
  })

  const handleScan = (e: React.FormEvent) => {
    e.preventDefault()
    if (!url.trim()) return
    scanMutation.mutate(url.trim())
  }

  const handleLaunchGapHunter = (seed_keyword: string, input_url: string) => {
    navigate(`/?new_keyword=${encodeURIComponent(seed_keyword)}&site_url=${encodeURIComponent(input_url)}`)
  }

  return (
    <div className="space-y-8">
      <section>
        <h2 className="text-2xl font-bold text-slate-950">Gold Hunter Agent</h2>
        <p className="mt-1 text-sm text-slate-500">
          Mine high-value seed keywords from any of your URLs.
        </p>
      </section>

      {error && (
        <div className="rounded-md bg-red-50 p-4 text-sm text-red-700">
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
          <h3 className="text-xl font-bold text-slate-900">Scan History</h3>
          
          <div className="grid gap-6">
            {history.map((scan) => (
              <Card key={scan.id} className="p-6">
                <div className="flex items-center gap-2 mb-4">
                  <Clock className="h-4 w-4 text-slate-400" />
                  <span className="text-sm text-slate-500">
                    {new Date(scan.created_at).toLocaleString()}
                  </span>
                  <span className="text-slate-300">|</span>
                  <a href={scan.input_url} target="_blank" rel="noreferrer" className="text-sm font-medium text-cyan-700 hover:underline">
                    {scan.input_url}
                  </a>
                </div>

                <div className="mb-6 rounded-lg bg-slate-50 p-4 border border-slate-100">
                  <h4 className="text-sm font-semibold text-slate-900 mb-2">Agent Audit Summary</h4>
                  <p className="text-sm text-slate-700 whitespace-pre-wrap">{scan.audit_summary}</p>
                </div>

                <div>
                  <h4 className="text-sm font-semibold text-slate-900 mb-3">Extracted Seeds</h4>
                  <div className="space-y-3">
                    {(scan.seeds || []).map((seed, i) => (
                      <div key={i} className="flex items-start justify-between gap-4 p-4 rounded-lg border border-slate-200">
                        <div>
                          <p className="font-semibold text-slate-900">{seed.keyword}</p>
                          <p className="text-sm text-slate-600 mt-1">{seed.justification}</p>
                        </div>
                        <Button 
                          variant="secondary" 
                          size="sm"
                          onClick={() => handleLaunchGapHunter(seed.keyword, scan.input_url)}
                          className="shrink-0"
                        >
                          <Plus className="h-4 w-4 mr-1" />
                          Gap Hunter
                        </Button>
                      </div>
                    ))}
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
