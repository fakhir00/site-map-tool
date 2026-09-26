import { useQuery } from '@tanstack/react-query'
import { Bookmark } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api, type KeywordBankEntry } from '../lib/api'
import { SavedKeywordsTable } from '../components/SavedKeywordsTable'

export default function SavedKeywords() {
  const navigate = useNavigate()
  const { data: keywordBank = [], isLoading, error } = useQuery({
    queryKey: ['keyword-bank'],
    queryFn: () => api.get<KeywordBankEntry[]>('/keyword-bank'),
  })

  return (
    <div className="mx-auto max-w-5xl py-8">
      <div className="flex items-center gap-3 mb-6 px-1">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-400">
          <Bookmark className="h-5 w-5" />
        </div>
        <div>
          <h2 className="text-xl font-bold text-slate-900 dark:text-slate-50">All Saved Keywords</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">View and manage all keywords you've saved to your bank.</p>
        </div>
      </div>

      {error ? <p role="alert" className="text-sm text-red-600">{error.message}</p> : <SavedKeywordsTable
        keywords={keywordBank}
        isLoading={isLoading}
        actionIcon="both"
        onAction={(kw, actionType) => {
          if (actionType === 'write') {
            navigate(`/write-blog/${kw.project_id}?keyword=${encodeURIComponent(kw.phrase)}`)
          } else {
            navigate(`/gap-page-prompts?keyword=${encodeURIComponent(kw.phrase)}`)
          }
        }}
      />}
    </div>
  )
}
