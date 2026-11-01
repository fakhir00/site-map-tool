import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, CheckCircle2, FilePenLine, Sparkles, Copy, Check, PenTool, Code, Eye } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { api, type ArticleDraft, type ArticleListResponse } from '../lib/api'
import { Badge } from './ui/Badge'
import { Button } from './ui/Button'
import { Card } from './ui/Card'

export function articleStatusBadge(article: ArticleDraft) {
  if (article.status === 'passed') return <Badge variant="green">Passed</Badge>
  if (article.status === 'needs_revision') return <Badge variant="red">Needs revision</Badge>
  if (article.status === 'error') return <Badge variant="red">Error</Badge>
  return <Badge variant="teal">Generating</Badge>
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
    return <div className="h-80 animate-pulse rounded-2xl border border-slate-200 bg-white dark:border-line dark:bg-panel" />
  }

  const article = articleId ? data?.items?.find(a => a.id === articleId) : data?.items?.[0]

  if (!article) {
    return (
      <Card>
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-site-sky/15 text-site-sky">
            <FilePenLine className="h-5 w-5" />
          </div>
          <div>
            <h3 className="font-display font-semibold text-slate-950 dark:text-text">AI article studio</h3>
            <p className="mt-1 text-sm text-slate-500 dark:text-muted">Generate a blog post from any keyword gap. The writer drafts it and the auditor scores it before it lands here.</p>
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

  return (
    <div className="space-y-4">
      {writeFinalMutation.error && <p role="alert" className="text-sm text-rose-600 dark:text-signal-red">{writeFinalMutation.error.message}</p>}
      {/* Header Card */}
      <Card className="space-y-5 p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-display text-xl font-bold text-slate-950 dark:text-text">{article.title || article.keyword_phrase}</h3>
              {articleStatusBadge(article)}
            </div>
            <p className="mt-1 text-sm text-slate-500 dark:text-muted">Keyword: {article.keyword_phrase}</p>
          </div>

          <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <div className="rounded-lg border border-slate-200 bg-slate-50 dark:border-line dark:bg-raised px-3 py-2">
              <p className="text-slate-500 dark:text-muted">Audit</p>
              <p className="font-mono text-lg font-bold text-slate-950 dark:text-text">{article.audit_score ?? '-'}</p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 dark:border-line dark:bg-raised px-3 py-2">
              <p className="text-slate-500 dark:text-muted">Attempts</p>
              <p className="font-mono text-lg font-bold text-slate-950 dark:text-text">{article.generation_attempts}</p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 dark:border-line dark:bg-raised px-3 py-2">
              <p className="text-slate-500 dark:text-muted">Sources</p>
              <p className="font-mono text-lg font-bold text-slate-950 dark:text-text">{competitorPages.length}</p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 dark:border-line dark:bg-raised px-3 py-2">
              <p className="text-slate-500 dark:text-muted">Verdict</p>
              <p className="font-mono text-lg font-bold text-slate-950 dark:text-text">{(audit?.passed || (audit?.score && audit.score > 80)) ? 'Pass' : 'Retry'}</p>
            </div>
          </div>
        </div>

        {(brief?.content_gaps?.length || brief?.must_include_terms?.length) && (
          <div className="grid gap-4 lg:grid-cols-2">
            <div>
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-950 dark:text-text">
                <Sparkles className="h-4 w-4 text-sky-700 dark:text-site-sky" />
                Gap brief
              </div>
              <div className="flex flex-wrap gap-2">
                {(brief?.content_gaps || []).slice(0, 6).map((gap: string) => (
                  <span className="inline-flex rounded-md border border-sky-200 bg-sky-50 text-sky-800 dark:border-site-sky/30 dark:bg-site-sky/10 dark:text-site-sky px-2.5 py-1 text-xs font-medium" key={gap}>
                    {gap}
                  </span>
                ))}
              </div>
            </div>
            <div>
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-950 dark:text-text">
                <CheckCircle2 className="h-4 w-4 text-emerald-700 dark:text-built-green" />
                Must-cover terms
              </div>
              <div className="flex flex-wrap gap-2">
                {(brief?.must_include_terms || []).slice(0, 10).map((term: string) => (
                  <span className="inline-flex rounded-md border border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-built-green/30 dark:bg-built-green/10 dark:text-built-green px-2.5 py-1 text-xs font-medium" key={term}>
                    {term}
                  </span>
                ))}
              </div>
            </div>
          </div>
        )}

        {!audit?.passed && !!audit?.issues?.length && (
          <div className="rounded-lg border border-slate-200 bg-slate-50 dark:border-line dark:bg-raised px-4 py-3 text-sm">
            <div className="mb-3 flex items-center gap-2 font-display font-semibold text-slate-950 dark:text-text">
              <AlertCircle className="h-4 w-4 text-signal-amber" />
              Auditor Recommendations
            </div>
            <ul className="space-y-2">
              {audit.issues.slice(0, 5).map((issue: string) => (
                <li key={issue} className="flex items-start gap-3">
                  <Badge variant="red">Fail</Badge>
                  <span className="font-mono text-xs leading-5 text-slate-700 dark:text-muted">{issue}</span>
                </li>
              ))}
              {(audit?.strengths || []).slice(0, 5).map((strength: string) => (
                <li key={strength} className="flex items-start gap-3">
                  <Badge variant="green">Pass</Badge>
                  <span className="font-mono text-xs leading-5 text-slate-700 dark:text-muted">{strength}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>

      {/* Prompt Dropdown */}
      {masterPrompt && (
        <Card className="overflow-hidden">
          <button 
            onClick={() => setPromptOpen(!promptOpen)}
            className="flex w-full items-center justify-between bg-slate-50 dark:bg-raised/50 px-6 py-4 text-left transition-colors hover:bg-slate-100 dark:hover:bg-raised"
          >
            <div className="flex items-center gap-2">
              <FilePenLine className="h-5 w-5 text-sky-700 dark:text-site-sky" />
              <h3 className="font-display font-semibold text-slate-900 dark:text-text">Master Prompt</h3>
            </div>
            <span className="text-sm font-medium text-slate-500 dark:text-muted">{promptOpen ? 'Collapse' : 'Expand'}</span>
          </button>
          
          {promptOpen && (
            <div className="border-t border-slate-200 dark:border-line p-6">
              <div className="mb-4 flex items-center justify-end gap-3">
                <Button
                  onClick={handleWriteArticle}
                  disabled={writeFinalMutation.isPending || article.status === 'generating'}
                  title={hasArticle ? "Rewrite final article" : "Generate final article"}
                >
                  <PenTool className="h-4 w-4" />
                  {writeFinalMutation.isPending || article.status === 'generating' 
                    ? (hasArticle ? 'Rewriting...' : 'Writing...')
                    : (hasArticle ? 'Rewrite Article' : 'Write Article')}
                </Button>

                <Button
                  variant="secondary"
                  onClick={() => copyToClipboard(masterPrompt)}
                >
                  {copied ? <><Check className="h-4 w-4 text-emerald-600 dark:text-built-green" /> Copied!</> : <><Copy className="h-4 w-4" /> Copy Prompt</>}
                </Button>
              </div>
              <div className="prose prose-slate max-w-none whitespace-pre-wrap font-mono text-sm leading-6 text-slate-800 bg-slate-50 border-slate-200 dark:text-muted dark:bg-raised dark:border-line p-4 rounded-md border">
                {masterPrompt}
              </div>
            </div>
          )}
        </Card>
      )}

      {/* Article Dropdown */}
      {hasArticle && (
        <Card className="overflow-hidden">
          <button 
            onClick={() => setArticleOpen(!articleOpen)}
            className="flex w-full items-center justify-between bg-slate-50 dark:bg-panel/70 px-6 py-4 text-left transition-colors hover:bg-slate-100 dark:hover:bg-slate-800/50"
          >
            <div className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
              <h3 className="font-semibold text-slate-900 dark:text-text">Generated Article</h3>
            </div>
            <span className="text-sm font-medium text-slate-500 dark:text-muted">{articleOpen ? 'Collapse' : 'Expand'}</span>
          </button>
          
          {articleOpen && (
            <div className="border-t border-slate-200 dark:border-line p-6">
              <div className="mb-6 flex items-center justify-end gap-3">
                <div className="flex rounded-md border border-slate-300 dark:border-line bg-white dark:bg-panel shadow-sm">
                  <button
                    onClick={() => setViewMode('preview')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-site-sky focus:ring-offset-1 rounded-l-md transition-colors ${
                      viewMode === 'preview' ? 'bg-site-sky/10 text-site-sky' : 'text-slate-600 hover:bg-slate-50 dark:text-muted dark:hover:bg-raised'
                    }`}
                  >
                    <Eye className="h-4 w-4" /> Preview
                  </button>
                  <div className="w-px bg-slate-300 dark:bg-raised" />
                  <button
                    onClick={() => setViewMode('markdown')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-site-sky focus:ring-offset-1 rounded-r-md transition-colors ${
                      viewMode === 'markdown' ? 'bg-site-sky/10 text-site-sky' : 'text-slate-600 hover:bg-slate-50 dark:text-muted dark:hover:bg-raised'
                    }`}
                  >
                    <Code className="h-4 w-4" /> Markdown
                  </button>
                </div>
                <button
                  onClick={() => copyToClipboard(article.content_markdown || '')}
                  className="flex items-center gap-1.5 rounded-md border border-slate-300 bg-white dark:border-line dark:bg-panel px-3 py-1.5 text-sm font-medium text-slate-700 dark:text-muted shadow-sm hover:bg-slate-50 dark:hover:bg-slate-800"
                >
                  {copied ? <><Check className="h-4 w-4 text-emerald-600" /> Copied!</> : <><Copy className="h-4 w-4" /> Copy Article</>}
                </button>
              </div>

              {viewMode === 'markdown' ? (
                <div className="prose prose-slate max-w-none whitespace-pre-wrap font-mono text-sm leading-6 text-slate-800 bg-slate-50 border-slate-200 dark:text-muted dark:bg-panel/70 dark:border-line p-4 rounded-md border">
                  {article.content_markdown}
                </div>
              ) : (
                <div className="prose dark:prose-invert max-w-none font-serif text-black dark:text-text bg-white dark:bg-panel/70 p-8 rounded-md border border-slate-300 dark:border-line shadow-inner dark:shadow-none prose-headings:font-serif prose-headings:text-black dark:prose-headings:text-slate-100 prose-p:text-black dark:prose-p:text-slate-300 prose-a:text-blue-600 dark:prose-a:text-blue-400 prose-a:underline">
                  <ReactMarkdown>
                    {article.content_markdown || ''}
                  </ReactMarkdown>
                </div>
              )}
            </div>
          )}
        </Card>
      )}
    </div>
  )
}
