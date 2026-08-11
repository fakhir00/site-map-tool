import { useQuery } from '@tanstack/react-query'
import { Bookmark, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, type KeywordBankEntry } from '../lib/api'
import { Badge } from '../components/ui/Badge'
import { Card } from '../components/ui/Card'
import { Button } from '../components/ui/Button'

function keywordBadge(type: KeywordBankEntry['keyword_type']) {
  if (type === 'primary') return <Badge variant="teal">Primary</Badge>
  if (type === 'lsi') return <Badge variant="indigo">LSI</Badge>
  if (type === 'long-tail') return <Badge variant="cyan">Long-tail</Badge>
  if (type === 'entity') return <Badge variant="amber">Entity</Badge>
  return <Badge variant="slate">Heading</Badge>
}

export default function SavedKeywords() {
  const { data: keywordBank = [] } = useQuery({
    queryKey: ['keyword-bank'],
    queryFn: () => api.get<KeywordBankEntry[]>('/keyword-bank'),
  })

  return (
    <div className="mx-auto max-w-5xl py-8">
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
                <th className="px-5 py-3 font-semibold">Frequency</th>
                <th className="px-5 py-3 text-right font-semibold">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {keywordBank.length === 0 ? (
                <tr>
                  <td className="px-5 py-10 text-center text-slate-500" colSpan={4}>
                    Saved keywords will appear here.
                  </td>
                </tr>
              ) : (
                keywordBank.map((entry) => (
                  <tr className="hover:bg-slate-50" key={entry.id}>
                    <td className="px-5 py-4 font-semibold text-slate-950">{entry.phrase}</td>
                    <td className="px-5 py-4">{keywordBadge(entry.keyword_type)}</td>
                    <td className="px-5 py-4 font-mono text-slate-700">{entry.frequency}</td>
                    <td className="px-5 py-4 text-right">
                      <Button
                        asChild
                        size="sm"
                        variant="secondary"
                      >
                        <Link to={`/gap-page-prompts?keyword=${encodeURIComponent(entry.phrase)}`}>
                          <Sparkles className="mr-1.5 h-4 w-4" />
                          Gap Page
                        </Link>
                      </Button>
                    </td>
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
