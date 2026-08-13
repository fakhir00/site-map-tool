import { useQuery } from '@tanstack/react-query'
import { Bookmark } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api, type KeywordBankEntry } from '../lib/api'
import { SavedKeywordsTable } from '../components/SavedKeywordsTable'

export default function SavedKeywords() {
  const navigate = useNavigate()
  const { data: keywordBank = [], isLoading } = useQuery({
    queryKey: ['keyword-bank'],
    queryFn: () => api.get<KeywordBankEntry[]>('/keyword-bank'),
  })

  return (
    <div className="mx-auto max-w-5xl py-8">
      <div className="flex items-center gap-3 mb-6 px-1">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-cyan-100 text-cyan-700">
          <Bookmark className="h-5 w-5" />
        </div>
        <div>
          <h2 className="text-xl font-bold text-slate-900">All Saved Keywords</h2>
          <p className="text-sm text-slate-500">View and manage all keywords you've saved to your bank.</p>
        </div>
      </div>

      <SavedKeywordsTable
        keywords={keywordBank}
        isLoading={isLoading}
      />
    </div>
  )
}
