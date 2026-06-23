import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, ExternalLink, FilePenLine, Sparkles } from 'lucide-react'
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
  const { data, isLoading } = useQuery({
    queryKey: ['project-articles', projectId],
    queryFn: () => api.get<ArticleListResponse>(`/projects/${projectId}/articles`),
    enabled: Boolean(projectId),
    refetchInterval: 10000,
  })

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

  return (
    <Card className="space-y-5">
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
              {(brief?.content_gaps || []).slice(0, 6).map((gap) => (
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
              {(brief?.must_include_terms || []).slice(0, 10).map((term) => (
                <span className="inline-flex rounded-md border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-800" key={term}>
                  {term}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {competitorPages.length > 0 && (
        <div>
          <p className="mb-2 text-sm font-semibold text-slate-950">Compared competitor pages</p>
          <div className="flex flex-wrap gap-2">
            {competitorPages.slice(0, 6).map((page) => (
              <a
                className="inline-flex max-w-[240px] items-center gap-2 truncate rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 hover:border-cyan-300 hover:text-cyan-800"
                href={page.url}
                key={page.url}
                rel="noopener noreferrer"
                target="_blank"
                title={page.url}
              >
                {displayHost(page.domain || page.url)}
                <ExternalLink className="h-3.5 w-3.5 shrink-0" />
              </a>
            ))}
          </div>
        </div>
      )}

      {!!audit?.issues?.length && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <div className="mb-2 flex items-center gap-2 font-semibold">
            <AlertTriangle className="h-4 w-4" />
            Auditor notes
          </div>
          <ul className="space-y-1">
            {audit.issues.slice(0, 5).map((issue) => (
              <li key={issue}>- {issue}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
        <div className="prose prose-slate max-w-none whitespace-pre-wrap text-sm leading-7 text-slate-800">
          {article.content_markdown}
        </div>
      </div>
    </Card>
  )
}
