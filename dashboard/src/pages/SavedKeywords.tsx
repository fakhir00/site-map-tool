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
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-site-sky/15 text-site-sky">
          <Bookmark className="h-5 w-5" />
        </div>
        <div>
          <h2 className="font-display text-xl font-bold text-text">Keyword Bank</h2>
          <p className="text-sm text-muted">View and manage all keywords you've saved to your bank.</p>
        </div>
      </div>

      {error ? <p role="alert" className="text-sm text-signal-red">{error.message}</p> : <SavedKeywordsTable
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
