import { useQuery } from '@tanstack/react-query'
import { Bookmark, CreditCard } from 'lucide-react'
import { api, type KeywordBankEntry, type User } from '../lib/api'
import { Badge } from '../components/ui/Badge'
import { Card } from '../components/ui/Card'

function keywordBadge(type: KeywordBankEntry['keyword_type']) {
  if (type === 'primary') return <Badge variant="teal">Primary</Badge>
  if (type === 'lsi') return <Badge variant="indigo">LSI</Badge>
  if (type === 'entity') return <Badge variant="amber">Entity</Badge>
  return <Badge variant="slate">Heading</Badge>
}

export function Settings() {
  const { data: user } = useQuery({
    queryKey: ['user'],
    queryFn: () => api.get<User>('/auth/me'),
  })

  const { data: keywordBank = [] } = useQuery({
    queryKey: ['keyword-bank'],
    queryFn: () => api.get<KeywordBankEntry[]>('/keyword-bank'),
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

      <Card className="p-0">
        <div className="flex items-center gap-3 border-b border-slate-200 px-5 py-4">
          <Bookmark className="h-5 w-5 text-cyan-800" />
          <h3 className="font-semibold text-slate-950">Saved keywords</h3>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-5 py-3 font-semibold">Keyword</th>
                <th className="px-5 py-3 font-semibold">Type</th>
                <th className="px-5 py-3 text-right font-semibold">Frequency</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {keywordBank.length === 0 ? (
                <tr>
                  <td className="px-5 py-10 text-center text-slate-500" colSpan={3}>
                    Saved keywords will appear here.
                  </td>
                </tr>
              ) : (
                keywordBank.map((entry) => (
                  <tr className="hover:bg-slate-50" key={entry.id}>
                    <td className="px-5 py-4 font-semibold text-slate-950">{entry.phrase}</td>
                    <td className="px-5 py-4">{keywordBadge(entry.keyword_type)}</td>
                    <td className="px-5 py-4 text-right font-mono text-slate-700">{entry.frequency}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
