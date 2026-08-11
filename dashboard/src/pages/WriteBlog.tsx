import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { Card } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { FilePenLine, FileText } from 'lucide-react'
import { GeneratedArticlePanel } from '../components/GeneratedArticlePanel'

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
  const [writingKeywordId, setWritingKeywordId] = useState<string | null>(null)
  const [articleError, setArticleError] = useState<string>('')
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null)

  const { data: keywords = [], isLoading } = useQuery({
    queryKey: ['keyword-bank'],
    queryFn: () => api.get<KeywordBankItem[]>('/keyword-bank'),
  })

  const articleMutation = useMutation({
    mutationFn: ({ keywordId, projectId }: { keywordId: string, projectId: string }) => 
      api.postArticle(`/projects/${projectId}/keywords/${keywordId}/article/generate`, {}),
    onMutate: ({ keywordId, projectId }) => {
      setWritingKeywordId(keywordId)
      setActiveProjectId(projectId)
      setArticleError('')
    },
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: ['project-articles', projectId] })
    },
    onError: (err) => {
      setArticleError(err instanceof Error ? err.message : 'Article generation failed')
    },
    onSettled: () => {
      setWritingKeywordId(null)
    },
  })

  return (
    <div className="mx-auto max-w-7xl py-8 flex gap-8">
      <div className="flex-1">
        <div className="mb-8 flex items-center justify-between">
          <h1 className="text-2xl font-bold text-slate-900">Write Blog</h1>
        </div>
        
        {articleError && (
          <div className="mb-6 rounded-md bg-red-50 p-4 text-sm text-red-700">
            {articleError}
          </div>
        )}
        
        <Card className="overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <th className="px-5 py-3 font-semibold">Keyword</th>
                <th className="px-5 py-3 font-semibold">Type</th>
                <th className="px-5 py-3 font-semibold">Saved Date</th>
                <th className="px-5 py-3 text-right font-semibold">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {isLoading ? (
                <tr>
                  <td colSpan={4} className="px-5 py-8 text-center text-slate-500">
                    Loading saved keywords...
                  </td>
                </tr>
              ) : keywords.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-5 py-8 text-center text-slate-500">
                    <FileText className="mx-auto mb-3 h-8 w-8 text-slate-300" />
                    <p>No keywords saved yet.</p>
                    <p className="mt-1 text-xs">Go to a project's Keyword gaps and save keywords to your bank to write blogs.</p>
                  </td>
                </tr>
              ) : (
                keywords.map((kw) => (
                  <tr key={kw.id} className="hover:bg-slate-50">
                    <td className="px-5 py-4 font-medium text-slate-900">{kw.phrase}</td>
                    <td className="px-5 py-4 text-slate-500 capitalize">{kw.keyword_type}</td>
                    <td className="px-5 py-4 text-slate-500">
                      {new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(kw.saved_at))}
                    </td>
                    <td className="px-5 py-4 text-right">
                      <Button
                        disabled={articleMutation.isPending && writingKeywordId === kw.keyword_id}
                        onClick={() => {
                          setActiveProjectId(kw.project_id)
                          articleMutation.mutate({ keywordId: kw.keyword_id, projectId: kw.project_id })
                        }}
                        size="sm"
                        variant="secondary"
                      >
                        <FilePenLine className="h-4 w-4" />
                        {articleMutation.isPending && writingKeywordId === kw.keyword_id ? 'Writing...' : 'Write'}
                      </Button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </Card>
      </div>

      {activeProjectId && (
        <div className="w-96">
          <div className="sticky top-8">
            <GeneratedArticlePanel projectId={activeProjectId} />
          </div>
        </div>
      )}
    </div>
  )
}
