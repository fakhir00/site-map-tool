import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, ExternalLink, FilePenLine, Sparkles, Copy, Check, PenTool, Code, Eye } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { api, type ArticleDraft, type ArticleListResponse } from '../lib/api'
import { Badge } from './ui/Badge'
import { Card } from './ui/Card'

function displayHost(value: string) {
  try {
    const withScheme = value.startsWith('http://') || value.startsWith('https://') ? value : `https://${value}`
    return new URL(withScheme).hostname.replace(/^www\./, '')
  } catch {
    return value.replace(/^https?:\/\//, '')
  }
}

function articleStatusBadge(article: ArticleDraft) {
  if (article.status === 'passed') return <Badge variant="teal">Passed</Badge>
  if (article.status === 'needs_revision') return <Badge variant="amber">Needs revision</Badge>
  if (article.status === 'error') return <Badge variant="red">Error</Badge>
  return <Badge variant="indigo">Generating</Badge>
}

export function GeneratedArticlePanel({ projectId }: { projectId: string }) {
  const [copied, setCopied] = useState(false)
  const [viewMode, setViewMode] = useState<'markdown' | 'preview'>('preview')
  const [promptOpen, setPromptOpen] = useState(true)
  const [articleOpen, setArticleOpen] = useState(false)
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['project-articles', projectId],
    queryFn: () => api.get<ArticleListResponse>(`/projects/${projectId}/articles`),
    enabled: Boolean(projectId),
    refetchInterval: 10000,
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
    return <div className="h-80 animate-pulse rounded-lg border border-slate-200 bg-white" />
  }

  const article = data?.items?.[0]

  if (!article) {
    return (
      <Card>
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-cyan-50 text-cyan-700">
            <FilePenLine className="h-5 w-5" />
          </div>
          <div>
            <h3 className="font-semibold text-slate-950">AI article studio</h3>
            <p className="mt-1 text-sm text-slate-500">Generate a blog post from any keyword gap. The writer drafts it and the auditor scores it before it lands here.</p>
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
      {/* Header Card */}
      <Card className="space-y-5 p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-xl font-bold text-slate-950">{article.title || article.keyword_phrase}</h3>
              {articleStatusBadge(article)}
            </div>
            <p className="mt-1 text-sm text-slate-500">Keyword: {article.keyword_phrase}</p>
          </div>

          <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
              <p className="text-slate-500">Audit</p>
              <p className="text-lg font-bold text-slate-950">{article.audit_score ?? '-'}</p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
              <p className="text-slate-500">Attempts</p>
              <p className="text-lg font-bold text-slate-950">{article.generation_attempts}</p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
              <p className="text-slate-500">Sources</p>
              <p className="text-lg font-bold text-slate-950">{competitorPages.length}</p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
              <p className="text-slate-500">Verdict</p>
              <p className="text-lg font-bold text-slate-950">{audit?.passed ? 'Pass' : 'Retry'}</p>
            </div>
          </div>
        </div>

        {(brief?.content_gaps?.length || brief?.must_include_terms?.length) && (
          <div className="grid gap-4 lg:grid-cols-2">
            <div>
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-950">
                <Sparkles className="h-4 w-4 text-cyan-700" />
                Gap brief
              </div>
              <div className="flex flex-wrap gap-2">
                {(brief?.content_gaps || []).slice(0, 6).map((gap: string) => (
                  <span className="inline-flex rounded-md border border-cyan-200 bg-cyan-50 px-2.5 py-1 text-xs font-medium text-cyan-800" key={gap}>
                    {gap}
                  </span>
                ))}
              </div>
            </div>
            <div>
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-950">
                <CheckCircle2 className="h-4 w-4 text-emerald-700" />
                Must-cover terms
              </div>
              <div className="flex flex-wrap gap-2">
                {(brief?.must_include_terms || []).slice(0, 10).map((term: string) => (
                  <span className="inline-flex rounded-md border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-800" key={term}>
                    {term}
                  </span>
                ))}
              </div>
            </div>
          </div>
        )}

        {!audit?.passed && !!audit?.issues?.length && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            <div className="mb-2 flex items-center gap-2 font-semibold">
              <AlertTriangle className="h-4 w-4" />
              Auditor notes
            </div>
            <ul className="space-y-1">
              {audit.issues.slice(0, 5).map((issue: string) => (
                <li key={issue}>- {issue}</li>
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
            className="flex w-full items-center justify-between bg-slate-50 px-6 py-4 text-left transition-colors hover:bg-slate-100"
          >
            <div className="flex items-center gap-2">
              <FilePenLine className="h-5 w-5 text-cyan-700" />
              <h3 className="font-semibold text-slate-900">Master Prompt</h3>
            </div>
            <span className="text-sm font-medium text-slate-500">{promptOpen ? 'Collapse' : 'Expand'}</span>
          </button>
          
          {promptOpen && (
            <div className="border-t border-slate-200 p-6">
              <div className="mb-4 flex items-center justify-end gap-3">
                <button
                  onClick={handleWriteArticle}
                  disabled={writeFinalMutation.isPending || article.status === 'generating'}
                  className="flex items-center gap-1.5 rounded-md border border-cyan-600 bg-cyan-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-cyan-700 disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:ring-offset-1"
                  title={hasArticle ? "Rewrite final article" : "Generate final article"}
                >
                  <PenTool className="h-4 w-4" />
                  {writeFinalMutation.isPending || article.status === 'generating' 
                    ? (hasArticle ? 'Rewriting...' : 'Writing...')
                    : (hasArticle ? 'Rewrite Article' : 'Write Article')}
                </button>

                <button
                  onClick={() => copyToClipboard(masterPrompt)}
                  className="flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:ring-offset-1"
                >
                  {copied ? <><Check className="h-4 w-4 text-emerald-600" /> Copied!</> : <><Copy className="h-4 w-4" /> Copy Prompt</>}
                </button>
              </div>
              <div className="prose prose-slate max-w-none whitespace-pre-wrap font-mono text-sm leading-6 text-slate-800 bg-slate-50 p-4 rounded-md border border-slate-200">
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
            className="flex w-full items-center justify-between bg-slate-50 px-6 py-4 text-left transition-colors hover:bg-slate-100"
          >
            <div className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-emerald-600" />
              <h3 className="font-semibold text-slate-900">Generated Article</h3>
            </div>
            <span className="text-sm font-medium text-slate-500">{articleOpen ? 'Collapse' : 'Expand'}</span>
          </button>
          
          {articleOpen && (
            <div className="border-t border-slate-200 p-6">
              <div className="mb-6 flex items-center justify-end gap-3">
                <div className="flex rounded-md border border-slate-300 bg-white shadow-sm">
                  <button
                    onClick={() => setViewMode('preview')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:ring-offset-1 rounded-l-md transition-colors ${
                      viewMode === 'preview' ? 'bg-cyan-50 text-cyan-700' : 'text-slate-600 hover:bg-slate-50'
                    }`}
                  >
                    <Eye className="h-4 w-4" /> Preview
                  </button>
                  <div className="w-px bg-slate-300" />
                  <button
                    onClick={() => setViewMode('markdown')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:ring-offset-1 rounded-r-md transition-colors ${
                      viewMode === 'markdown' ? 'bg-cyan-50 text-cyan-700' : 'text-slate-600 hover:bg-slate-50'
                    }`}
                  >
                    <Code className="h-4 w-4" /> Markdown
                  </button>
                </div>
                <button
                  onClick={() => copyToClipboard(article.content_markdown || '')}
                  className="flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50"
                >
                  {copied ? <><Check className="h-4 w-4 text-emerald-600" /> Copied!</> : <><Copy className="h-4 w-4" /> Copy Article</>}
                </button>
              </div>

              {viewMode === 'markdown' ? (
                <div className="prose prose-slate max-w-none whitespace-pre-wrap font-mono text-sm leading-6 text-slate-800 bg-slate-50 p-4 rounded-md border border-slate-200">
                  {article.content_markdown}
                </div>
              ) : (
                <div className="prose prose-slate max-w-none text-base leading-7 text-slate-800 prose-headings:text-slate-900 prose-headings:font-bold prose-h1:text-3xl prose-h2:text-2xl prose-h3:text-xl prose-a:text-cyan-700 hover:prose-a:text-cyan-800 prose-strong:text-slate-900 prose-hr:border-slate-200 bg-white p-6 rounded-md border border-slate-200 shadow-sm">
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
