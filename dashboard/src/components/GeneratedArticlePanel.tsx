import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Loader2, ChevronDown, FilePenLine, Sparkles, Copy, Check, PenTool, Code, Eye, Target, ListChecks } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { api, type ArticleDraft, type ArticleListResponse } from '../lib/api'
import { Badge } from './ui/Badge'
import { Button } from './ui/Button'
import { Card } from './ui/Card'

function articleStatusBadge(article: ArticleDraft) {
  if (article.status === 'passed') return <Badge variant="teal">Passed</Badge>
  if (article.status === 'needs_revision') return <Badge variant="amber">Needs revision</Badge>
  if (article.status === 'error') return <Badge variant="red">Error</Badge>
  return <Badge variant="indigo">Generating</Badge>
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
    return (
      <div className="space-y-4">
        <div className="animate-shimmer h-[220px] rounded-2xl" />
        <div className="animate-shimmer h-[140px] rounded-2xl" />
      </div>
    )
  }

  const article = articleId ? data?.items?.find(a => a.id === articleId) : data?.items?.[0]

  if (!article) {
    return (
      <Card lift={false}>
        <div className="flex items-start gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-soft-violet/15 text-soft-violet">
            <FilePenLine className="h-6 w-6" />
          </div>
          <div>
            <h3 className="font-display text-lg font-semibold text-ink">Your articles will live here</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              Generate a blog post from any keyword gap. The writer drafts it, the auditor
              scores it, and the finished piece lands right here — ready to copy or refine.
            </p>
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

  const isBusy = writeFinalMutation.isPending || article.status === 'generating'

  return (
    <div className="space-y-6">
      {writeFinalMutation.error && (
        <p role="alert" className="rounded-2xl border border-warm-red/30 bg-warm-red/10 px-4 py-3 text-sm text-warm-red">
          {writeFinalMutation.error.message}
        </p>
      )}

      {/* Header Card */}
      <Card lift={false} className="p-6 sm:p-8">
        <div className="flex flex-col gap-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-3">
                <h3 className="font-display text-2xl font-bold tracking-tight text-ink">
                  {article.title || article.keyword_phrase}
                </h3>
                {articleStatusBadge(article)}
              </div>
              <p className="mt-2 font-mono text-xs uppercase tracking-widest text-muted">
                Keyword · {article.keyword_phrase}
              </p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              { label: 'Audit', value: article.audit_score != null ? String(article.audit_score) : '–' },
              { label: 'Attempts', value: String(article.generation_attempts) },
              { label: 'Sources', value: String(competitorPages.length) },
              { label: 'Verdict', value: (audit?.passed || (audit?.score && audit.score > 80)) ? 'Pass' : 'Retry' },
            ].map((stat) => (
              <div key={stat.label} className="rounded-2xl border border-line bg-raised px-4 py-3">
                <p className="font-mono text-[11px] uppercase tracking-widest text-muted">{stat.label}</p>
                <p className="mt-1 font-display text-xl font-bold text-ink">{stat.value}</p>
              </div>
            ))}
          </div>
        </div>

        {(brief?.content_gaps?.length || brief?.must_include_terms?.length) ? (
          <div className="mt-8 grid gap-6 lg:grid-cols-2">
            <div>
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
                <Target className="h-4 w-4 text-glow-amber" />
                Gap brief
              </div>
              <div className="flex flex-wrap gap-2">
                {(brief?.content_gaps || []).slice(0, 6).map((gap: string) => (
                  <span className="inline-flex rounded-full border border-glow-amber/25 bg-glow-amber/10 px-3 py-1 text-xs font-medium text-glow-amber" key={gap}>
                    {gap}
                  </span>
                ))}
              </div>
            </div>
            <div>
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
                <ListChecks className="h-4 w-4 text-alive-green" />
                Must-cover terms
              </div>
              <div className="flex flex-wrap gap-2">
                {(brief?.must_include_terms || []).slice(0, 10).map((term: string) => (
                  <span className="inline-flex rounded-full border border-alive-green/25 bg-alive-green/10 px-3 py-1 text-xs font-medium text-alive-green" key={term}>
                    {term}
                  </span>
                ))}
              </div>
            </div>
          </div>
        ) : null}

        {!audit?.passed && !!audit?.issues?.length && (
          <div className="mt-8 rounded-2xl border border-glow-amber/25 bg-glow-amber/8 px-5 py-4 text-sm text-ink">
            <div className="mb-2 flex items-center gap-2 font-semibold text-glow-amber">
              <AlertCircle className="h-4 w-4" />
              Auditor recommendations
            </div>
            <ul className="space-y-1.5 text-muted">
              {audit.issues.slice(0, 5).map((issue: string) => (
                <li key={issue} className="flex gap-2">
                  <span className="text-glow-amber">–</span>
                  <span>{issue}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>

      {/* Master Prompt */}
      {masterPrompt && (
        <Card lift={false} className="overflow-hidden p-0">
          <button
            onClick={() => setPromptOpen(!promptOpen)}
            className="flex w-full items-center justify-between px-6 py-5 text-left transition-colors hover:bg-white/[0.02]"
          >
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-soft-violet/15 text-soft-violet">
                <FilePenLine className="h-5 w-5" />
              </div>
              <div>
                <h3 className="font-display text-base font-semibold text-ink">Master Prompt</h3>
                <p className="text-xs text-muted">The exact brief the writer follows</p>
              </div>
            </div>
            <ChevronDown className={`h-5 w-5 text-muted transition-transform ${promptOpen ? 'rotate-180' : ''}`} />
          </button>

          {promptOpen && (
            <div className="border-t border-line px-6 pb-6 pt-5">
              <div className="mb-5 flex flex-wrap items-center justify-end gap-3">
                <Button variant="ghost" size="sm" onClick={() => copyToClipboard(masterPrompt)}>
                  {copied ? <Check className="h-4 w-4 text-alive-green" /> : <Copy className="h-4 w-4" />}
                  {copied ? 'Copied!' : 'Copy Prompt'}
                </Button>
                <Button
                  variant="glow"
                  size="sm"
                  onClick={handleWriteArticle}
                  disabled={isBusy}
                  title={hasArticle ? 'Rewrite final article' : 'Generate final article'}
                >
                  {isBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <PenTool className="h-4 w-4" />}
                  {isBusy
                    ? (hasArticle ? 'Rewriting...' : 'Writing...')
                    : (hasArticle ? 'Rewrite Article' : 'Write Article')}
                </Button>
              </div>
              <div className="whitespace-pre-wrap rounded-2xl border border-line bg-abyss p-5 font-mono text-[13px] leading-7 text-muted">
                {masterPrompt}
              </div>
            </div>
          )}
        </Card>
      )}

      {/* Generated Article */}
      {hasArticle && (
        <Card lift={false} className="overflow-hidden p-0">
          <button
            onClick={() => setArticleOpen(!articleOpen)}
            className="flex w-full items-center justify-between px-6 py-5 text-left transition-colors hover:bg-white/[0.02]"
          >
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-alive-green/15 text-alive-green">
                <Sparkles className="h-5 w-5" />
              </div>
              <div>
                <h3 className="font-display text-base font-semibold text-ink">Generated Article</h3>
                <p className="text-xs text-muted">Ready to read, copy, and publish</p>
              </div>
            </div>
            <ChevronDown className={`h-5 w-5 text-muted transition-transform ${articleOpen ? 'rotate-180' : ''}`} />
          </button>

          {articleOpen && (
            <div className="border-t border-line px-6 pb-8 pt-5">
              <div className="mb-6 flex flex-wrap items-center justify-end gap-3">
                <div className="flex rounded-xl border border-line bg-raised p-1">
                  <button
                    onClick={() => setViewMode('preview')}
                    className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                      viewMode === 'preview' ? 'bg-white/10 text-ink' : 'text-muted hover:text-ink'
                    }`}
                  >
                    <Eye className="h-4 w-4" /> Preview
                  </button>
                  <button
                    onClick={() => setViewMode('markdown')}
                    className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                      viewMode === 'markdown' ? 'bg-white/10 text-ink' : 'text-muted hover:text-ink'
                    }`}
                  >
                    <Code className="h-4 w-4" /> Markdown
                  </button>
                </div>
                <Button variant="ghost" size="sm" onClick={() => copyToClipboard(article.content_markdown || '')}>
                  {copied ? <Check className="h-4 w-4 text-alive-green" /> : <Copy className="h-4 w-4" />}
                  {copied ? 'Copied!' : 'Copy Article'}
                </Button>
              </div>

              {viewMode === 'markdown' ? (
                <div className="whitespace-pre-wrap rounded-2xl border border-line bg-abyss p-5 font-mono text-[13px] leading-7 text-muted">
                  {article.content_markdown}
                </div>
              ) : (
                <div className="prose prose-invert mx-auto max-w-prose font-sans leading-relaxed text-ink prose-headings:font-display prose-headings:tracking-tight prose-headings:text-ink prose-p:text-ink/85 prose-a:text-glow-amber prose-strong:text-ink prose-li:text-ink/85">
                  <ReactMarkdown>
                    {article.content_markdown || ''}
                  </ReactMarkdown>
                </div>
              )}
            </div>
          )}
        </Card>
      )}

      {/* Generating skeleton */}
      {!hasArticle && article.status === 'generating' && !masterPrompt && (
        <div className="space-y-3">
          <div className="animate-shimmer h-10 w-2/3 rounded-xl" />
          <div className="animate-shimmer h-4 w-full rounded-xl" />
          <div className="animate-shimmer h-4 w-11/12 rounded-xl" />
          <div className="animate-shimmer h-4 w-4/5 rounded-xl" />
        </div>
      )}
    </div>
  )
}
