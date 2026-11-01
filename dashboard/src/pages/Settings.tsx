import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot, CreditCard, Database } from 'lucide-react'
import { api, type ProviderStatus } from '../lib/api'
import { accountQuery } from '../lib/workspaceQueries'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { ThemeToggle } from '../components/ThemeToggle'

type AIStatus = { configured: boolean; message: string; providers: { name: string; model: string; available: boolean | null; message: string }[] }

export function Settings() {
  const queryClient = useQueryClient()
  const { data: aiStatus, error: aiError } = useQuery({
    queryKey: ['provider-status', 'ai'], queryFn: () => api.get<AIStatus>('/providers/ai/status'), retry: false,
  })
  const { data: health } = useQuery({
    queryKey: ['health'], queryFn: () => api.get<{ revision: string; database: string }>('/health'), retry: false,
  })
  const checkAI = useMutation({
    mutationFn: () => api.postAI<AIStatus>('/providers/ai/check'),
    onSuccess: (result) => queryClient.setQueryData(['provider-status', 'ai'], result),
  })
  const { data: user } = useQuery(accountQuery)
  const { data: dataForSeo, isLoading: isLoadingDataForSeo } = useQuery({
    queryKey: ['provider-status', 'dataforseo'],
    queryFn: () => api.get<ProviderStatus>('/providers/dataforseo/status'),
    retry: false,
  })
  const { data: apify, isLoading: isLoadingApify } = useQuery({
    queryKey: ['provider-status', 'apify'],
    queryFn: () => api.get<ProviderStatus>('/providers/apify/status'),
    retry: false,
  })
  const apifyAvailable = apify?.available ?? apify?.authenticated

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <div>
        <h2 className="font-display text-2xl font-bold text-text">Settings</h2>
        <p className="annotation mt-2">Office filing — account record, plan permit, switchboard.</p>
      </div>

      {/* ▸ PROFILE drawer */}
      <section className="space-y-3">
        <p className="font-mono text-xs font-semibold uppercase tracking-[0.22em] text-muted">
          <span className="text-amber">▸</span> Profile
        </p>
        <Card>
          <div className="mb-5 flex items-center gap-4 border-b border-line pb-5">
            <div className="flex h-14 w-14 items-center justify-center rounded-full border border-line bg-raised font-mono text-xl font-semibold text-amber">
              {(user?.full_name || user?.email || 'U').charAt(0).toUpperCase()}
            </div>
            <div>
              <h3 className="font-display text-lg font-semibold text-text">{user?.full_name || 'User'}</h3>
              <p className="font-mono text-sm text-muted">{user?.email}</p>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <p className="mb-1.5 font-mono text-[0.6875rem] uppercase tracking-[0.18em] text-muted">Full name</p>
              <div className="rounded-lg border border-line bg-ink px-3 py-2 text-sm text-text">
                {user?.full_name || 'Not provided'}
              </div>
            </div>
            <div>
              <p className="mb-1.5 font-mono text-[0.6875rem] uppercase tracking-[0.18em] text-muted">Email</p>
              <div className="rounded-lg border border-line bg-ink px-3 py-2 font-mono text-sm text-text">{user?.email}</div>
            </div>
          </div>
        </Card>
      </section>

      {/* ▸ PLAN drawer — stamped permit card */}
      <section className="space-y-3">
        <p className="font-mono text-xs font-semibold uppercase tracking-[0.22em] text-muted">
          <span className="text-amber">▸</span> Plan
        </p>
        <Card>
          <div className="spec-plate">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <p className="spec-label">Current permit</p>
                <p className="spec-value mt-1 capitalize">{user?.plan || 'free'}</p>
              </div>
              {user?.plan === 'free' ? (
                <span className="stamp stamp-amber">Free · Trial</span>
              ) : (
                <span className="stamp stamp-green capitalize">{user?.plan} · Active</span>
              )}
            </div>
          </div>
          <div className="mt-5 flex flex-wrap items-center gap-4">
            <CreditCard className="h-4 w-4 text-muted" />
            <p className="annotation">Permit covers this workspace. Higher tiers raise the scan and blueprint allowance.</p>
          </div>
          <Button variant="primary" className="mt-4 w-full sm:w-auto">
            Upgrade to Agency
          </Button>
        </Card>
      </section>

      {/* ▸ CONNECTIONS drawer — switchboard */}
      <section className="space-y-3">
        <p className="font-mono text-xs font-semibold uppercase tracking-[0.22em] text-muted">
          <span className="text-amber">▸</span> Connections
        </p>
        <Card className="divide-y divide-line py-0!">
          <div className="flex items-center justify-between gap-4 px-5 py-4">
            <div className="flex items-center gap-3">
              <Database className="h-4 w-4 text-sky" />
              <p className="font-mono text-sm text-text">Keyword data</p>
            </div>
            <span className="flex items-center gap-2 font-mono text-xs uppercase tracking-[0.14em] text-muted">
              <span className={`h-2 w-2 rounded-full ${dataForSeo?.authenticated ? 'bg-green' : 'bg-amber'}`} />
              {isLoadingDataForSeo ? 'Checking' : dataForSeo?.authenticated ? 'Connected' : dataForSeo?.configured ? 'Auth failed' : 'Not configured'}
            </span>
          </div>

          <div className="flex items-center justify-between gap-4 px-5 py-4">
            <div className="flex items-center gap-3">
              <Bot className="h-4 w-4 text-sky" />
              <p className="font-mono text-sm text-text">Crawler access</p>
            </div>
            <span className="flex items-center gap-2 font-mono text-xs uppercase tracking-[0.14em] text-muted">
              <span className={`h-2 w-2 rounded-full ${apifyAvailable ? 'bg-green' : 'bg-amber'}`} />
              {isLoadingApify ? 'Checking' : apifyAvailable ? 'Connected' : apify?.configured ? 'Auth failed' : 'Not configured'}
            </span>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-4 px-5 py-4">
            <div className="flex items-center gap-3">
              <span className={`h-2 w-2 rounded-full ${aiError ? 'bg-red' : aiStatus ? 'bg-green' : 'bg-amber'}`} />
              <div>
                <p className="font-mono text-sm text-text">AI drafting pool</p>
                <p className="mt-0.5 font-mono text-xs text-muted">
                  {aiError ? 'Unavailable' : aiStatus ? `${aiStatus.providers.filter((p) => p.available === true).length}/${aiStatus.providers.length} ready` : 'Not checked'}
                </p>
              </div>
            </div>
            <Button variant="draft" onClick={() => checkAI.mutate()} disabled={checkAI.isPending}>
              {checkAI.isPending ? 'Testing…' : 'Test connection'}
            </Button>
          </div>

          <div className="flex items-center justify-between gap-4 px-5 py-4">
            <div className="flex items-center gap-3">
              <span className={`h-2 w-2 rounded-full ${health ? 'bg-green' : 'bg-amber'}`} />
              <p className="font-mono text-sm text-text">Office systems</p>
            </div>
            <span className="font-mono text-xs uppercase tracking-[0.14em] text-muted">
              {health ? 'Nominal' : 'Unknown'}
            </span>
          </div>
        </Card>
        {(checkAI.error || aiError) && (
          <p role="alert" className="font-mono text-xs text-red">▸ The AI connection test failed. Try again shortly.</p>
        )}
      </section>

      {/* ▸ CONTROLS drawer */}
      <section className="space-y-3">
        <p className="font-mono text-xs font-semibold uppercase tracking-[0.22em] text-muted">
          <span className="text-amber">▸</span> Controls
        </p>
        <Card>
          <div className="max-w-xs">
            <ThemeToggle />
          </div>
          <p className="annotation mt-3">Appearance is saved to this workstation only.</p>
        </Card>
      </section>
    </div>
  )
}
