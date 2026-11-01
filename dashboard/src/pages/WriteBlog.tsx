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

  const pending = articleMutation.isPending || manualMutation.isPending

  return (
    <div className="mx-auto max-w-3xl py-8 space-y-8">
      
      {articleError && (
        <div className="flex items-center gap-3 rounded-xl border-2 border-red/50 bg-panel p-4">
          <span className="stamp stamp-red">Error</span>
          <p className="text-sm text-text">{articleError}</p>
        </div>
      )}

      {/* Commissioning slip */}
      <Card className="relative overflow-hidden">
        <div className="construction-line is-horizontal top-0" />
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-amber/40 bg-amber/10 text-amber">
              <FilePenLine className="h-5 w-5" />
            </div>
            <div>
              <p className="annotation">COMMISSION SLIP — BLOG WRITER</p>
              <h2 className="mt-1 font-display text-2xl font-bold tracking-tight text-text">Blog Writer</h2>
            </div>
          </div>
          <span className="stamp stamp-amber">Commission</span>
        </div>
        <p className="mt-3 text-sm text-muted">Generate a targeted blog post from a main keyword and an optional keyword cluster. The writer drafts it, the auditor scores it, and the finished sheet lands in your Article Studio.</p>

        <div className="mt-6 space-y-5">
          <div>
            <label className="mb-1.5 block font-mono text-xs uppercase tracking-[0.14em] text-muted" htmlFor="blog-main-keyword">
              Main Keyword <span className="text-red">*</span>
            </label>
            <input
              id="blog-main-keyword"
              type="text"
              className="w-full rounded-lg border border-line bg-ink px-3 py-2.5 text-sm text-text placeholder:text-muted/60 focus:border-amber/70 focus:outline-none focus:ring-1 focus:ring-amber/40"
              placeholder="e.g. mortgage calculator"
              value={mainKeyword}
              onChange={(e) => setMainKeyword(e.target.value)}
            />
          </div>

          <div>
            <label className="mb-1.5 block font-mono text-xs uppercase tracking-[0.14em] text-muted" htmlFor="blog-cluster">
              Keyword Cluster <span className="text-muted/70">(optional)</span>
            </label>
            <p className="annotation mb-2">Related keywords to naturally include in the article, one per line.</p>
            <textarea
              id="blog-cluster"
              className="w-full rounded-lg border border-line bg-ink px-3 py-2.5 font-mono text-sm text-text placeholder:text-muted/60 focus:border-amber/70 focus:outline-none focus:ring-1 focus:ring-amber/40"
              rows={4}
              placeholder={`home loan rates\namortization schedule\ninterest rates`}
              value={keywordCluster}
              onChange={(e) => setKeywordCluster(e.target.value)}
            />
          </div>

          {architectureBrief && (
            <div>
              <label className="mb-1.5 block font-mono text-xs uppercase tracking-[0.14em] text-muted" htmlFor="blog-brief">
                Architecture brief <span className="text-muted/70">(attached sheet)</span>
              </label>
              <textarea
                id="blog-brief"
                aria-label="Architecture brief"
                value={architectureBrief}
                onChange={event => setArchitectureBrief(event.target.value)}
                maxLength={12000}
                rows={8}
                className="w-full rounded-lg border border-line bg-ink p-3 font-mono text-sm text-text placeholder:text-muted/60 focus:border-amber/70 focus:outline-none focus:ring-1 focus:ring-amber/40"
              />
            </div>
          )}

          <Button 
            variant="primary"
            className="w-full"
            size="lg"
            disabled={pending || !mainKeyword}
            onClick={handleGenerateBlog}
          >
            {pending ? <Loader2 className="mr-2 h-5 w-5 animate-spin" /> : null}
            {pending ? 'Generating…' : 'Generate Blog'}
          </Button>
        </div>
      </Card>

      {/* Keyword Bank from Gap Scan */}
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
