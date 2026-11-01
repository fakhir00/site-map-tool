import { useQuery } from '@tanstack/react-query'
import { CreditCard } from 'lucide-react'
import { api, type ProviderStatus } from '../lib/api'
import { accountQuery } from '../lib/workspaceQueries'
import { Button } from '../components/ui/Button'
import { Badge } from '../components/ui/Badge'
import { Card } from '../components/ui/Card'
import { Input } from '../components/ui/Input'

export function Settings() {
  const { data: user } = useQuery(accountQuery)
  const { data: dataForSeo, isLoading: isLoadingDataForSeo } = useQuery({
    queryKey: ['provider-status', 'dataforseo'],
    queryFn: () => api.get<ProviderStatus>('/providers/dataforseo/status'),
    retry: false,
  })

  const keywordDataConnected = dataForSeo?.authenticated ?? false
  const keywordDataLabel = isLoadingDataForSeo
    ? 'Checking'
    : keywordDataConnected
      ? 'Connected'
      : dataForSeo?.configured
        ? 'Authentication failed'
        : 'Not configured'

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h2 className="font-display text-2xl font-bold text-text">Settings</h2>
        <p className="mt-1 text-sm text-muted">Account details, plan status, and saved keyword inventory.</p>
      </div>

      <section className="grid gap-4 lg:grid-cols-[1fr_0.8fr]">
        <Card>
          <div className="mb-5 flex items-center gap-4 border-b border-line pb-5">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-raised font-display text-xl font-bold text-site-sky">
              {(user?.full_name || user?.email || 'U').charAt(0).toUpperCase()}
            </div>
            <div>
              <h3 className="font-display text-lg font-semibold text-text">{user?.full_name || 'User'}</h3>
              <p className="text-sm text-muted">{user?.email}</p>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <p className="mb-1 text-sm font-medium text-muted">Full name</p>
              <Input readOnly value={user?.full_name || 'Not provided'} aria-label="Full name" />
            </div>
            <div>
              <p className="mb-1 text-sm font-medium text-muted">Email</p>
              <Input readOnly value={user?.email || ''} aria-label="Email" />
            </div>
          </div>
        </Card>

        <Card>
          <div className="mb-5 flex items-center gap-3">
            <CreditCard className="h-5 w-5 text-site-sky" />
            <h3 className="font-display text-lg font-semibold text-text">Plan</h3>
          </div>
          <p className="text-sm text-muted">Current plan</p>
          <div className="mt-2 flex items-center gap-3">
            <span className="text-2xl font-bold capitalize text-text">{user?.plan || 'free'}</span>
            <Badge variant={user?.plan === 'free' ? 'slate' : 'teal'}>{user?.plan === 'free' ? 'Trial' : 'Active'}</Badge>
          </div>
          <Button variant="primary" className="mt-6 w-full">Upgrade to Agency</Button>
        </Card>
      </section>

      <Card>
        <h3 className="font-display text-lg font-semibold text-text">Connections</h3>
        <div className="mt-4 flex items-center justify-between gap-4 border-t border-line pt-4">
          <p className="text-sm font-medium text-text">Keyword data</p>
          <span className="flex items-center gap-2.5">
            <span className={`h-2.5 w-2.5 rounded-full ${keywordDataConnected ? 'bg-built-green' : 'bg-signal-amber'}`} aria-hidden="true" />
            <Badge variant={keywordDataConnected ? 'teal' : 'amber'}>{keywordDataLabel}</Badge>
          </span>
        </div>
      </Card>
    </div>
  )
}
