import { useQuery } from '@tanstack/react-query'
import { Bookmark } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api, type KeywordBankEntry } from '../lib/api'
import { SavedKeywordsTable } from '../components/SavedKeywordsTable'
import { Badge } from '../components/ui/Badge'

export default function SavedKeywords() {
  const navigate = useNavigate()
  const { data: keywordBank = [], isLoading, error } = useQuery({
    queryKey: ['keyword-bank'],
    queryFn: () => api.get<KeywordBankEntry[]>('/keyword-bank'),
  })

  return (
    <div className="page-shell warm-glow-bg">
      <div className="animate-fade-up">
        <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-glow-amber/25 bg-glow-amber/10 text-glow-amber">
              <Bookmark className="h-6 w-6" />
            </div>
            <div>
              <h1 className="font-display text-3xl font-bold tracking-tight text-ink">Keyword Bank</h1>
              <p className="mt-1 text-sm text-muted">Every keyword you've saved — ready when you are.</p>
            </div>
          </div>
          {!isLoading && !error && keywordBank.length > 0 && (
            <Badge variant="amber" className="px-3 py-1 text-sm">
              {keywordBank.length} saved
            </Badge>
          )}
        </header>

        {error ? (
          <p role="alert" className="rounded-2xl border border-warm-red/25 bg-warm-red/10 px-5 py-4 text-sm text-warm-red">
            {error.message}
          </p>
        ) : (
          <SavedKeywordsTable
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
          />
        )}
      </div>
    </div>
  )
}
