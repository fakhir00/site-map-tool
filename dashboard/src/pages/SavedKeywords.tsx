import { useQuery } from '@tanstack/react-query'
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
    <div className="mx-auto max-w-6xl py-8">
      <div className="mb-6 px-1">
        <p className="annotation">▸ KEYWORD BANK — SHEET 04</p>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-display text-3xl font-bold tracking-tight text-text">Keyword Bank</h2>
          <span className="stamp stamp-amber">
            {keywordBank.length} {keywordBank.length === 1 ? 'PART' : 'PARTS'}
          </span>
        </div>
        <p className="annotation annotation--leading mt-3 max-w-2xl">
          Every keyword you saved from the Gap Scan or the Blog tool, shelved like parts on the bench. Pull a part, then write the article or build the page.
        </p>
      </div>

      {error ? (
        <p role="alert" className="annotation !text-red">{error.message}</p>
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
  )
}
