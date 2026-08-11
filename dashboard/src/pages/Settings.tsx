import { useQuery } from '@tanstack/react-query'
import { CreditCard } from 'lucide-react'
import { api, type User } from '../lib/api'
import { Badge } from '../components/ui/Badge'
import { Card } from '../components/ui/Card'

export function Settings() {
  const { data: user } = useQuery({
    queryKey: ['user'],
    queryFn: () => api.get<User>('/auth/me'),
  })

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-slate-950">Settings</h2>
        <p className="mt-1 text-sm text-slate-500">Account details, plan status, and saved keyword inventory.</p>
      </div>

      <section className="grid gap-4 lg:grid-cols-[1fr_0.8fr]">
        <Card>
          <div className="mb-5 flex items-center gap-4 border-b border-slate-200 pb-5">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-cyan-50 text-xl font-bold text-cyan-800">
              {(user?.full_name || user?.email || 'U').charAt(0).toUpperCase()}
            </div>
            <div>
              <h3 className="text-lg font-semibold text-slate-950">{user?.full_name || 'User'}</h3>
              <p className="text-sm text-slate-500">{user?.email}</p>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <p className="mb-1 text-sm font-medium text-slate-500">Full name</p>
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800">
                {user?.full_name || 'Not provided'}
              </div>
            </div>
            <div>
              <p className="mb-1 text-sm font-medium text-slate-500">Email</p>
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800">{user?.email}</div>
            </div>
          </div>
        </Card>

        <Card>
          <div className="mb-5 flex items-center gap-3">
            <CreditCard className="h-5 w-5 text-indigo-700" />
            <h3 className="text-lg font-semibold text-slate-950">Plan</h3>
          </div>
          <p className="text-sm text-slate-500">Current plan</p>
          <div className="mt-2 flex items-center gap-3">
            <span className="text-2xl font-bold capitalize text-slate-950">{user?.plan || 'free'}</span>
            <Badge variant={user?.plan === 'free' ? 'slate' : 'teal'}>{user?.plan === 'free' ? 'Trial' : 'Active'}</Badge>
          </div>
        </Card>
      </section>

    </div>
  )
}
