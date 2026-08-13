import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { Card } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { FilePenLine, FileText, Loader2 } from 'lucide-react'
import { SavedKeywordsTable } from '../components/SavedKeywordsTable'

type KeywordBankItem = {
  id: string
  keyword_id: string
  project_id: string
  phrase: string
  keyword_type: string
  frequency: number
  notes: string | null
  saved_at: string
}

export default function WriteBlog() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [writingKeywordId, setWritingKeywordId] = useState<string | null>(null)
  const [articleError, setArticleError] = useState<string>('')
  
  const [mainKeyword, setMainKeyword] = useState('')
  const [keywordCluster, setKeywordCluster] = useState('')
  const [selectedKeyword, setSelectedKeyword] = useState<KeywordBankItem | null>(null)

  const { data: allKeywords = [], isLoading } = useQuery({
    queryKey: ['keyword-bank'],
    queryFn: () => api.get<KeywordBankItem[]>('/keyword-bank'),
  })

  const keywords = allKeywords.filter(kw => kw.notes === '#blog')

  const articleMutation = useMutation({
    mutationFn: ({ keywordId, projectId }: { keywordId: string, projectId: string }) => 
      api.postArticle(`/projects/${projectId}/keywords/${keywordId}/article/generate`, {}),
    onMutate: ({ keywordId }) => {
      setWritingKeywordId(keywordId)
      setArticleError('')
    },
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: ['project-articles', projectId] })
      window.open(`/write-blog/${projectId}`, '_blank')
      setWritingKeywordId(null)
    },
    onError: (err) => {
      setArticleError(err instanceof Error ? err.message : 'Article generation failed')
      setWritingKeywordId(null)
    },
  })

  const handleGenerateBlog = () => {
    if (selectedKeyword && selectedKeyword.phrase === mainKeyword) {
      articleMutation.mutate({ keywordId: selectedKeyword.keyword_id, projectId: selectedKeyword.project_id })
    } else {
      alert('Manual blog generation without a saved keyword is coming soon! Please select a keyword from the table below.')
    }
  }

  return (
    <div className="mx-auto max-w-3xl py-8 space-y-8">
      
      {articleError && (
        <div className="rounded-md bg-red-50 p-4 text-sm text-red-700">
          {articleError}
        </div>
      )}

      {/* Manual Blog Generator Box */}
      <Card className="p-6">
        <div className="flex items-center gap-3 mb-6">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-cyan-100 text-cyan-700">
            <FilePenLine className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-slate-900">Write Blog</h2>
            <p className="text-sm text-slate-500">Generate a targeted blog post from a main keyword and an optional keyword cluster.</p>
          </div>
        </div>

        <div className="space-y-5">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Main Keyword <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
              placeholder="e.g. mortgage calculator"
              value={mainKeyword}
              onChange={(e) => setMainKeyword(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Keyword Cluster (Optional)
            </label>
            <p className="text-xs text-slate-500 mb-2">
              Enter related keywords to naturally include in the article.
            </p>
            <textarea
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
              rows={4}
              placeholder={`home loan rates\namortization schedule\ninterest rates`}
              value={keywordCluster}
              onChange={(e) => setKeywordCluster(e.target.value)}
            />
          </div>

          <Button 
            className="w-full bg-cyan-500 hover:bg-cyan-600 text-white" 
            size="lg"
            disabled={articleMutation.isPending || !mainKeyword}
            onClick={handleGenerateBlog}
          >
            {articleMutation.isPending ? <Loader2 className="mr-2 h-5 w-5 animate-spin" /> : null}
            {articleMutation.isPending ? 'Generating...' : 'Generate Blog'}
          </Button>
        </div>
      </Card>

      {/* Saved Keywords from Gap Hunter */}
      <SavedKeywordsTable
        keywords={keywords}
        isLoading={isLoading}
        actionIcon="write"
        onAction={(kw) => {
          setMainKeyword(kw.phrase)
          setSelectedKeyword(kw)
          window.scrollTo({ top: 0, behavior: 'smooth' })
        }}
      />
    </div>
  )
}
