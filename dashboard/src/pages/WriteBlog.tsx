import { useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, type KeywordBankEntry } from '../lib/api'
import { Card } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { Badge } from '../components/ui/Badge'
import { FilePenLine, Loader2, Sparkles, X } from 'lucide-react'
import { SavedKeywordsTable } from '../components/SavedKeywordsTable'
import { scrollToTop } from '../lib/utils'

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

  const isGenerating = articleMutation.isPending || manualMutation.isPending

  return (
    <div className="page-shell warm-glow-bg">
      <div className="mx-auto max-w-3xl space-y-10">
        {/* Page header */}
        <div className="animate-fade-up">
          <p className="mb-2 font-mono text-xs uppercase tracking-widest text-glow-amber">Blog Writer</p>
          <h1 className="font-display text-3xl font-bold tracking-tight text-ink sm:text-4xl">
            Turn a keyword gap into a draft.
          </h1>
          <p className="mt-3 max-w-xl text-muted">
            The writer drafts it, the auditor scores it, and you get an article that is
            ready to ship — from one keyword.
          </p>
        </div>

        {articleError && (
          <div className="animate-fade-up rounded-2xl border border-warm-red/30 bg-warm-red/10 p-4 text-sm text-warm-red" role="alert">
            {articleError}
          </div>
        )}

        {/* Editor card */}
        <Card className="animate-fade-up p-6 sm:p-8" lift={false}>
          <div className="mb-8 flex items-center gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-glow-amber/15 text-glow-amber">
              <FilePenLine className="h-6 w-6" />
            </div>
            <div>
              <h2 className="font-display text-xl font-semibold text-ink">New article</h2>
              <p className="text-sm text-muted">One keyword in, a full draft out.</p>
            </div>
          </div>

          <div className="space-y-6">
            {selectedKeyword && (
              <div className="flex items-center justify-between gap-3 rounded-2xl border border-glow-amber/25 bg-glow-amber/8 px-4 py-3">
                <div className="flex min-w-0 items-center gap-2">
                  <Badge variant="amber">From your gap scan</Badge>
                  <span className="truncate text-sm font-medium text-ink">{selectedKeyword.phrase}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedKeyword(null)}
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-muted transition-colors hover:bg-white/5 hover:text-ink"
                  aria-label="Clear selected keyword"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            )}

            <div>
              <label className="mb-2 block text-sm font-medium text-ink">
                Main Keyword <span className="text-warm-red">*</span>
              </label>
              <Input
                type="text"
                placeholder="e.g. mortgage calculator"
                value={mainKeyword}
                onChange={(e) => setMainKeyword(e.target.value)}
                className="h-12 text-base"
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-ink">
                Keyword Cluster <span className="font-normal text-muted">(optional)</span>
              </label>
              <p className="mb-2 text-xs text-muted">
                Related keywords the writer will weave in naturally — one per line.
              </p>
              <textarea
                className="w-full rounded-xl border border-line bg-raised px-3 py-2 text-sm text-ink placeholder:text-muted/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-glow-amber/40 focus-visible:border-glow-amber/60 transition-colors"
                rows={4}
                placeholder={`home loan rates\namortization schedule\ninterest rates`}
                value={keywordCluster}
                onChange={(e) => setKeywordCluster(e.target.value)}
              />
            </div>

            {architectureBrief && (
              <div>
                <label className="mb-2 block text-sm font-medium text-ink">
                  Architecture Brief
                </label>
                <textarea
                  aria-label="Architecture brief"
                  value={architectureBrief}
                  onChange={event => setArchitectureBrief(event.target.value)}
                  maxLength={12000}
                  rows={8}
                  className="w-full rounded-xl border border-line bg-raised px-3 py-2 text-sm text-ink placeholder:text-muted/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-glow-amber/40 focus-visible:border-glow-amber/60 transition-colors"
                />
              </div>
            )}

            <Button
              variant="glow"
              size="lg"
              className="w-full"
              disabled={isGenerating || !mainKeyword}
              onClick={handleGenerateBlog}
            >
              {isGenerating ? (
                <Loader2 className="h-5 w-5 animate-spin" />
              ) : (
                <Sparkles className="h-5 w-5" />
              )}
              {isGenerating ? 'Writing your draft...' : 'Generate Blog Post'}
            </Button>
          </div>
        </Card>

        {/* Keyword Bank from Gap Scan */}
        <div className="animate-fade-up">
          <div className="mb-4 flex items-end justify-between">
            <div>
              <h2 className="font-display text-xl font-semibold text-ink">From your keyword bank</h2>
              <p className="mt-1 text-sm text-muted">Pick a saved gap keyword to pre-fill the writer.</p>
            </div>
          </div>
          <SavedKeywordsTable
            keywords={keywords}
            isLoading={isLoading}
            actionIcon="write"
            onAction={(kw) => {
              setMainKeyword(kw.phrase)
              setArchitectureBrief('')
              setKeywordCluster('')
              setSelectedKeyword(kw)
              scrollToTop()
            }}
          />
        </div>
      </div>
    </div>
  )
}
