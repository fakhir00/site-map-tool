import { useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, type KeywordBankEntry } from '../lib/api'
import { Card } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { FilePenLine, Loader2 } from 'lucide-react'
import { SavedKeywordsTable } from '../components/SavedKeywordsTable'

export default function WriteBlog() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const location = useLocation()
  const [architectureBrief, setArchitectureBrief] = useState<string>(location.state?.architectureBrief || '')
  
  const initialKeyword = searchParams.get('keyword') || ''
  const initialCluster = searchParams.get('cluster') || ''

  const [articleError, setArticleError] = useState<string>('')
  
  const [mainKeyword, setMainKeyword] = useState(initialKeyword)
  const [keywordCluster, setKeywordCluster] = useState(initialCluster)
  const [chosenKeyword, setSelectedKeyword] = useState<KeywordBankEntry | null>(null)

  const { data: allKeywords = [], isLoading } = useQuery({
    queryKey: ['keyword-bank'],
    queryFn: () => api.get<KeywordBankEntry[]>('/keyword-bank'),
  })

  const selectedKeyword = chosenKeyword || allKeywords.find(kw => kw.phrase === initialKeyword) || null

  const keywords = allKeywords.filter(kw => kw.notes === '#blog')

  const articleMutation = useMutation({
    mutationFn: ({ keywordId, projectId }: { keywordId: string, projectId: string }) => 
      api.postArticle(`/projects/${projectId}/keywords/${keywordId}/article/generate`, {}),
    onMutate: () => {
      setArticleError('')
    },
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: ['project-articles', projectId] })
      navigate(`/write-blog/${projectId}`)
    },
    onError: (err) => {
      setArticleError(err instanceof Error ? err.message : 'Article generation failed')
    },
  })

  const manualMutation = useMutation({
    mutationFn: ({ main_keyword, keyword_cluster }: { main_keyword: string, keyword_cluster: string }) => 
      api.postArticle<{ project_id: string }>('/projects/manual-generate', { main_keyword, keyword_cluster, project_id: searchParams.get('project_id') || undefined, architecture_brief: architectureBrief }),
    onMutate: () => {
      setArticleError('')
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['project-articles', data.project_id] })
      navigate(`/write-blog/${data.project_id}`)
    },
    onError: (err) => {
      setArticleError(err instanceof Error ? err.message : 'Manual article generation failed')
    },
  })

  const handleGenerateBlog = () => {
    if (!architectureBrief && (chosenKeyword || !searchParams.get('project_id')) && selectedKeyword && selectedKeyword.phrase === mainKeyword) {
      articleMutation.mutate({ keywordId: selectedKeyword.keyword_id, projectId: selectedKeyword.project_id })
    } else {
      manualMutation.mutate({ main_keyword: mainKeyword, keyword_cluster: keywordCluster })
    }
  }

  return (
    <div className="mx-auto max-w-3xl py-8 space-y-8">
      
      {articleError && (
        <div className="rounded-md bg-red-50 dark:bg-red-900/30 p-4 text-sm text-red-700 dark:text-red-300">
          {articleError}
        </div>
      )}

      {/* Manual Blog Generator Box */}
      <Card className="p-6">
        <div className="flex items-center gap-3 mb-6">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-400">
            <FilePenLine className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-slate-900 dark:text-slate-50">Write Blog</h2>
            <p className="text-sm text-slate-500 dark:text-slate-400">Generate a targeted blog post from a main keyword and an optional keyword cluster.</p>
          </div>
        </div>

        <div className="space-y-5">
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              Main Keyword <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              className="w-full rounded-md border border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-50 px-3 py-2 text-sm focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
              placeholder="e.g. mortgage calculator"
              value={mainKeyword}
              onChange={(e) => setMainKeyword(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              Keyword Cluster (Optional)
            </label>
            <p className="text-xs text-slate-500 dark:text-slate-400 mb-2">
              Enter related keywords to naturally include in the article.
            </p>
            <textarea
              className="w-full rounded-md border border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-50 px-3 py-2 text-sm focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
              rows={4}
              placeholder={`home loan rates\namortization schedule\ninterest rates`}
              value={keywordCluster}
              onChange={(e) => setKeywordCluster(e.target.value)}
            />
          </div>

          {architectureBrief && <label className="block text-sm font-medium">Architecture brief<textarea aria-label="Architecture brief" value={architectureBrief} onChange={event => setArchitectureBrief(event.target.value)} maxLength={12000} rows={8} className="mt-2 w-full rounded-lg border border-slate-300 bg-transparent p-3 text-sm dark:border-slate-700" /></label>}

          <Button 
            className="w-full bg-cyan-500 hover:bg-cyan-600 text-white" 
            size="lg"
            disabled={articleMutation.isPending || manualMutation.isPending || !mainKeyword}
            onClick={handleGenerateBlog}
          >
            {articleMutation.isPending || manualMutation.isPending ? <Loader2 className="mr-2 h-5 w-5 animate-spin" /> : null}
            {articleMutation.isPending || manualMutation.isPending ? 'Generating...' : 'Generate Blog'}
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
          setArchitectureBrief('')
          setKeywordCluster('')
          setSelectedKeyword(kw)
          window.scrollTo({ top: 0, behavior: 'smooth' })
        }}
      />
    </div>
  )
}
