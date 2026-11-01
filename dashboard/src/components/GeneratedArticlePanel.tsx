import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, ClipboardCheck, FilePenLine, Sparkles, Copy, Check, PenTool, Code, Eye } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { api, type ArticleDraft, type ArticleListResponse } from '../lib/api'
import { Card } from '../components/ui/Card'
import { Button } from '../components/ui/Button'

function articleStatusStamp(article: ArticleDraft) {
  if (article.status === 'passed') return <span className="stamp stamp-green">Passed</span>
  if (article.status === 'needs_revision') return <span className="stamp stamp-red">Needs revision</span>
  if (article.status === 'error') return <span className="stamp stamp-red">Error</span>
  return <span className="stamp stamp-amber">Generating</span>
}

export function GeneratedArticlePanel({ projectId, articleId }: { projectId: string, articleId?: string | null }) {
  const [copied, setCopied] = useState(false)
  const [viewMode, setViewMode] = useState<'markdown' | 'preview'>('preview')
  const [promptOpen, setPromptOpen] = useState(true)
  const [articleOpen, setArticleOpen] = useState(false)
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['project-articles', projectId],
    queryFn: () => api.get<ArticleListResponse>(`/projects/${projectId}/articles`),
    enabled: Boolean(projectId),
    refetchInterval: (query) => query.state.data?.items.some((article) => article.status === 'generating') ? 4000 : false,
  })

  const writeFinalMutation = useMutation({
    mutationFn: (articleId: string) => api.postArticle(`/projects/${projectId}/articles/${articleId}/write-final`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project-articles', projectId] })
      setPromptOpen(false)
      setArticleOpen(true)
    },
  })

  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy text: ', err)
    }
  }

  if (isLoading && !data) {
    return <div className="h-80 animate-pulse rounded-2xl border border-line bg-panel" />
  }

  const article = articleId ? data?.items?.find(a => a.id === articleId) : data?.items?.[0]

  if (!article) {
    return (
      <Card>
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-amber/40 bg-amber/10 text-amber">
            <FilePenLine className="h-5 w-5" />
          </div>
          <div>
            <p className="annotation">AI ARTICLE STUDIO — EMPTY DESK</p>
            <h3 className="mt-1 font-display font-bold text-text">AI article studio</h3>
            <p className="mt-1 text-sm text-muted">Generate a blog post from any keyword gap. The writer drafts it and the auditor scores it before it lands here.</p>
          </div>
        </div>
      </Card>
    )
  }

  const competitorPages = article.research_summary?.competitor_pages || []
  const brief = article.research_summary?.brief
  const audit = article.audit_feedback

  const isPrompt = article.content_markdown?.startsWith('# CONTENT WRITING ASSIGNMENT')

  const masterPrompt = article.research_summary?.master_prompt || (isPrompt ? article.content_markdown : null)
  const hasArticle = !isPrompt && !!article.content_markdown

  const handleWriteArticle = () => {
    writeFinalMutation.mutate(article.id)
  }

  // Determine initial open states (only on first load)
  // We already initialized state, we can use a basic effect to sync if needed.
  // We'll skip sync since user can just toggle manually and the UI is robust enough.

  const verdictPassed = audit?.passed || (audit?.score !== undefined && audit.score > 80)

  return (
    <div className="space-y-4">
      {writeFinalMutation.error && (
        <div className="flex items-center gap-3 rounded-xl border-2 border-red/50 bg-panel p-4">
          <span className="stamp stamp-red">Error</span>
          <p role="alert" className="text-sm text-text">{writeFinalMutation.error.message}</p>
        </div>
      )}
      {/* Header Card */}
      <Card className="space-y-5 p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="annotation">DOSSIER — ARTICLE DRAFT</p>
            <div className="mt-1 flex flex-wrap items-center gap-3">
              <h3 className="font-display text-xl font-bold tracking-tight text-text">{article.title || article.keyword_phrase}</h3>
              {articleStatusStamp(article)}
            </div>
            <p className="mt-2 font-mono text-xs text-muted">KEYWORD <span className="text-text">“{article.keyword_phrase}”</span></p>
          </div>

          <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <div className="spec-plate">
              <p className="spec-label">Audit</p>
              <p className="spec-value">{article.audit_score ?? '—'}</p>
            </div>
            <div className="spec-plate">
              <p className="spec-label">Attempts</p>
              <p className="spec-value">{article.generation_attempts}</p>
            </div>
            <div className="spec-plate">
              <p className="spec-label">Sources</p>
              <p className="spec-value">{competitorPages.length}</p>
            </div>
            <div className="spec-plate">
              <p className="spec-label">Verdict</p>
              <p className={`spec-value ${verdictPassed ? '!text-green' : '!text-red'}`}>{verdictPassed ? 'Pass' : 'Retry'}</p>
            </div>
          </div>
        </div>

        {(brief?.content_gaps?.length || brief?.must_include_terms?.length) && (
          <div className="grid gap-4 lg:grid-cols-2">
            <div>
              <div className="mb-2 flex items-center gap-2 font-mono text-xs uppercase tracking-[0.14em] text-muted">
                <Sparkles className="h-4 w-4 text-amber" />
                Gap brief
              </div>
              <div className="flex flex-wrap gap-2">
                {(brief?.content_gaps || []).slice(0, 6).map((gap: string) => (
                  <span className="inline-flex rounded-md border border-amber/50 bg-amber/10 px-2.5 py-1 font-mono text-xs text-amber" key={gap}>
                    {gap}
                  </span>
                ))}
              </div>
            </div>
            <div>
              <div className="mb-2 flex items-center gap-2 font-mono text-xs uppercase tracking-[0.14em] text-muted">
                <CheckCircle2 className="h-4 w-4 text-sky" />
                Must-cover terms
              </div>
              <div className="flex flex-wrap gap-2">
                {(brief?.must_include_terms || []).slice(0, 10).map((term: string) => (
                  <span className="inline-flex rounded-md border border-sky/40 bg-sky/10 px-2.5 py-1 font-mono text-xs text-sky" key={term}>
                    {term}
                  </span>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Inspector's checklist — audit log */}
        {(audit?.passed !== undefined || !!audit?.issues?.length || !!audit?.strengths?.length) && (
          <div className="rounded-xl border border-line bg-ink p-4">
            <div className="mb-3 flex items-center gap-2 font-mono text-xs uppercase tracking-[0.14em] text-muted">
              <ClipboardCheck className="h-4 w-4 text-amber" />
              Inspector's checklist — audit log
            </div>
            <ul className="space-y-2.5">
              {audit?.passed !== undefined && (
                <li className="flex items-center gap-3">
                  <span className={`stamp ${audit.passed ? 'stamp-green' : 'stamp-red'}`}>{audit.passed ? 'Pass' : 'Fail'}</span>
                  <span className="font-mono text-xs uppercase tracking-[0.14em] text-text">Verdict</span>
                  {audit.score !== undefined && <span className="font-mono text-xs text-muted">score {audit.score}</span>}
                </li>
              )}
              {(audit?.strengths || []).map((strength: string) => (
                <li className="flex items-center gap-3" key={`pass-${strength}`}>
                  <span className="stamp stamp-green">Pass</span>
                  <span className="font-mono text-xs text-muted">{strength}</span>
                </li>
              ))}
              {(audit?.issues || []).map((issue: string) => (
                <li className="flex items-center gap-3" key={`fail-${issue}`}>
                  <span className="stamp stamp-red">Fail</span>
                  <span className="font-mono text-xs text-muted">{issue}</span>
                </li>
              ))}
              {(audit?.revision_notes || []).map((note: string) => (
                <li className="flex items-center gap-3" key={`rev-${note}`}>
                  <span className="stamp stamp-amber">Revise</span>
                  <span className="font-mono text-xs text-muted">{note}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

      </Card>

      {/* Prompt Dropdown */}
      {masterPrompt && (
        <Card className="overflow-hidden !p-0">
          <button
            onClick={() => setPromptOpen(!promptOpen)}
            className="flex w-full items-center justify-between bg-raised px-6 py-4 text-left transition-colors hover:bg-ink"
          >
            <div className="flex items-center gap-2">
              <FilePenLine className="h-5 w-5 text-amber" />
              <h3 className="font-display font-semibold text-text">Master Prompt</h3>
            </div>
            <span className="font-mono text-xs uppercase tracking-[0.14em] text-muted">{promptOpen ? 'Collapse' : 'Expand'}</span>
          </button>

          {promptOpen && (
            <div className="border-t border-line p-6">
              <div className="mb-4 flex items-center justify-end gap-3">
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleWriteArticle}
                  disabled={writeFinalMutation.isPending || article.status === 'generating'}
                  title={hasArticle ? "Rewrite final article" : "Generate final article"}
                >
                  <PenTool className="h-4 w-4" />
                  {writeFinalMutation.isPending || article.status === 'generating'
                    ? (hasArticle ? 'Rewriting…' : 'Writing…')
                    : (hasArticle ? 'Rewrite Article' : 'Write Article')}
                </Button>

                <Button
                  variant="draft"
                  onClick={() => copyToClipboard(masterPrompt)}
                >
                  {copied ? <><Check className="h-4 w-4" /> Copied!</> : <><Copy className="h-4 w-4" /> Copy Prompt</>}
                </Button>
              </div>
              <div className="whitespace-pre-wrap rounded-lg border border-line bg-ink p-4 font-mono text-sm leading-6 text-muted">
                {masterPrompt}
              </div>
            </div>
          )}
        </Card>
      )}

      {/* Article Dropdown — manuscript sheet */}
      {hasArticle && (
        <Card className="overflow-hidden !p-0">
          <button
            onClick={() => setArticleOpen(!articleOpen)}
            className="flex w-full items-center justify-between bg-raised px-6 py-4 text-left transition-colors hover:bg-ink"
          >
            <div className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-green" />
              <h3 className="font-display font-semibold text-text">Generated Article</h3>
            </div>
            <span className="font-mono text-xs uppercase tracking-[0.14em] text-muted">{articleOpen ? 'Collapse' : 'Expand'}</span>
          </button>

          {articleOpen && (
            <div className="border-t border-line p-6">
              <div className="mb-6 flex items-center justify-end gap-3">
                <div className="flex gap-2">
                  <Button
                    variant="draft"
                    aria-pressed={viewMode === 'preview'}
                    className={viewMode === 'preview' ? '!border-amber bg-amber/15' : ''}
                    onClick={() => setViewMode('preview')}
                  >
                    <Eye className="h-4 w-4" /> Preview
                  </Button>
                  <Button
                    variant="draft"
                    aria-pressed={viewMode === 'markdown'}
                    className={viewMode === 'markdown' ? '!border-amber bg-amber/15' : ''}
                    onClick={() => setViewMode('markdown')}
                  >
                    <Code className="h-4 w-4" /> Markdown
                  </Button>
                </div>
                <Button
                  variant="draft"
                  onClick={() => copyToClipboard(article.content_markdown || '')}
                >
                  {copied ? <><Check className="h-4 w-4" /> Copied!</> : <><Copy className="h-4 w-4" /> Copy Article</>}
                </Button>
              </div>

              {viewMode === 'markdown' ? (
                <div className="whitespace-pre-wrap rounded-lg border border-line bg-ink p-4 font-mono text-sm leading-6 text-muted">
                  {article.content_markdown}
                </div>
              ) : (
                <div className="rounded-lg border border-line bg-[#f4eee1] p-8 font-serif text-[#16233a] shadow-[0_16px_40px_-16px_rgba(0,0,0,0.7)]">
                  <div className="prose max-w-none font-serif text-[#16233a] prose-headings:font-serif prose-headings:text-[#16233a] prose-p:text-[#16233a] prose-a:text-[#0b5cad] prose-a:underline prose-strong:text-[#16233a] prose-li:text-[#16233a] prose-blockquote:text-[#16233a]/80">
                    <ReactMarkdown>
                      {article.content_markdown || ''}
                    </ReactMarkdown>
                  </div>
                </div>
              )}
            </div>
          )}
        </Card>
      )}
    </div>
  )
}
