import { useQuery } from '@tanstack/react-query'
import { Bot, CreditCard, Database } from 'lucide-react'
import { api, type ProviderStatus, type User } from '../lib/api'
import { Badge } from '../components/ui/Badge'
import { Card } from '../components/ui/Card'

export function Settings() {
  const { data: user } = useQuery({
    queryKey: ['user'],
    queryFn: () => api.get<User>('/auth/me'),
  })
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

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-slate-950 dark:text-slate-50">Settings</h2>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Account details, plan status, and saved keyword inventory.</p>
      </div>

      <section className="grid gap-4 lg:grid-cols-[1fr_0.8fr]">
        <Card>
          <div className="mb-5 flex items-center gap-4 border-b border-slate-200 dark:border-slate-800 pb-5">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-cyan-50 text-xl font-bold text-cyan-800 dark:bg-cyan-900/30 dark:text-cyan-300">
              {(user?.full_name || user?.email || 'U').charAt(0).toUpperCase()}
            </div>
            <div>
              <h3 className="text-lg font-semibold text-slate-950 dark:text-slate-50">{user?.full_name || 'User'}</h3>
              <p className="text-sm text-slate-500 dark:text-slate-400">{user?.email}</p>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <p className="mb-1 text-sm font-medium text-slate-500 dark:text-slate-400">Full name</p>
              <div className="rounded-lg border border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900/50 px-3 py-2 text-sm text-slate-800 dark:text-slate-300">
                {user?.full_name || 'Not provided'}
              </div>
            </div>
            <div>
              <p className="mb-1 text-sm font-medium text-slate-500 dark:text-slate-400">Email</p>
              <div className="rounded-lg border border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900/50 px-3 py-2 text-sm text-slate-800 dark:text-slate-300">{user?.email}</div>
            </div>
          </div>
        </Card>

        <Card>
          <div className="mb-5 flex items-center gap-3">
            <CreditCard className="h-5 w-5 text-indigo-700 dark:text-indigo-400" />
            <h3 className="text-lg font-semibold text-slate-950 dark:text-slate-50">Plan</h3>
          </div>
          <p className="text-sm text-slate-500 dark:text-slate-400">Current plan</p>
          <div className="mt-2 flex items-center gap-3">
            <span className="text-2xl font-bold capitalize text-slate-950 dark:text-slate-50">{user?.plan || 'free'}</span>
            <Badge variant={user?.plan === 'free' ? 'slate' : 'teal'}>{user?.plan === 'free' ? 'Trial' : 'Active'}</Badge>
          </div>
        </Card>
      </section>

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <Database className="mt-0.5 h-5 w-5 text-cyan-700 dark:text-cyan-400" />
            <div>
              <h3 className="text-lg font-semibold text-slate-950 dark:text-slate-50">DataForSEO</h3>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                {isLoadingDataForSeo ? 'Checking the Render credentials…' : dataForSeo?.message || 'Provider status unavailable.'}
              </p>
              {dataForSeo?.credential_source && (
                <p className="mt-1 text-xs text-slate-400">Using {dataForSeo.credential_source} and its matching password.</p>
              )}
            </div>
          </div>
          <Badge variant={dataForSeo?.authenticated ? 'teal' : 'amber'}>
            {isLoadingDataForSeo ? 'Checking' : dataForSeo?.authenticated ? 'Connected' : dataForSeo?.configured ? 'Authentication failed' : 'Not configured'}
          </Badge>
        </div>
      </Card>

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <Bot className="mt-0.5 h-5 w-5 text-indigo-700 dark:text-indigo-400" />
            <div>
              <h3 className="text-lg font-semibold text-slate-950 dark:text-slate-50">Apify</h3>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                {isLoadingApify ? 'Checking the Render token…' : apify?.message || 'Provider status unavailable.'}
              </p>
            </div>
          </div>
          <Badge variant={apify?.authenticated ? 'teal' : 'amber'}>
            {isLoadingApify ? 'Checking' : apify?.authenticated ? 'Connected' : apify?.configured ? 'Authentication failed' : 'Not configured'}
          </Badge>
        </div>
      </Card>

    </div>
  )
}
