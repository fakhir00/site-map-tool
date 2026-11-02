import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Clock, FileText, Feather } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { api, type ArticleDraft, type ArticleListResponse } from '../lib/api'
import { Badge } from '../components/ui/Badge'
import { GeneratedArticlePanel } from '../components/GeneratedArticlePanel'

function statusBadge(article: ArticleDraft) {
  if (article.status === 'passed') return <Badge variant="green">Passed</Badge>
  if (article.status === 'needs_revision') return <Badge variant="amber">Needs revision</Badge>
  if (article.status === 'error') return <Badge variant="red">Error</Badge>
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-soft-violet/20 bg-soft-violet/15 px-2.5 py-0.5 text-xs font-semibold text-soft-violet">
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-soft-violet" />
      Writing
    </span>
  )
}

export default function WriteBlogArticle() {
  const { projectId } = useParams<{ projectId: string }>()
  const [selectedArticleId, setSelectedArticleId] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['project-articles', projectId],
    queryFn: () => api.get<ArticleListResponse>(`/projects/${projectId}/articles`),
    enabled: Boolean(projectId),
    refetchInterval: (query) => query.state.data?.items.some((article) => article.status === 'generating') ? 4000 : false,
  })

  if (!projectId) {
    return (
      <div className="page-shell">
        <div className="mx-auto max-w-md rounded-2xl border border-line bg-surface p-8 text-center">
          <p className="font-display text-lg font-semibold text-ink">Project not found</p>
          <p className="mt-2 text-sm text-muted">This article doesn't belong to a project we can see.</p>
          <Link to="/write-blog" className="mt-4 inline-flex items-center gap-2 text-sm font-medium text-glow-amber hover:text-[#ffb63d]">
            <ArrowLeft className="h-4 w-4" />
            Back to Blog Writer
          </Link>
        </div>
      </div>
    )
  }

  const items = data?.items ?? []
  const activeId = selectedArticleId ?? items[0]?.id ?? null

  return (
    <div className="page-shell warm-glow-bg">
      <div className="animate-fade-up">
        <Link
          to="/write-blog"
          className="mb-6 inline-flex items-center gap-2 text-sm font-medium text-muted transition-colors hover:text-ink"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Blog Writer
        </Link>
        <div className="mb-10">
          <p className="mb-2 font-mono text-xs uppercase tracking-widest text-glow-amber">Article Studio</p>
          <h1 className="font-display text-3xl font-bold tracking-tight text-ink sm:text-4xl">
            Every draft, in one calm place.
          </h1>
          <p className="mt-3 max-w-xl text-muted">
            Prompts, audits and finished articles — pick one from the shelf and read, copy, or rewrite.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[320px_1fr]">
        {/* History shelf */}
        <div className="animate-fade-up">
          <div className="mb-4 flex items-center gap-2">
            <Clock className="h-4 w-4 text-muted" />
            <h2 className="font-display text-lg font-semibold text-ink">History</h2>
            {items.length > 0 && (
              <span className="font-mono text-xs text-muted">{items.length}</span>
            )}
          </div>

          <div className="space-y-3">
            {isLoading ? (
              Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="animate-shimmer h-[76px] rounded-2xl" />
              ))
            ) : items.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-line bg-surface/50 p-8 text-center">
                <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-soft-violet/15 text-soft-violet">
                  <Feather className="h-6 w-6" />
                </div>
                <p className="font-display text-base font-semibold text-ink">Nothing written yet</p>
                <p className="mt-2 text-sm text-muted">
                  Your first draft is one keyword away — generate it and it'll land right here.
                </p>
                <Link
                  to="/write-blog"
                  className="mt-4 inline-flex items-center gap-2 rounded-xl bg-glow-amber px-4 py-2 text-sm font-semibold text-on-accent transition-all hover:bg-[#ffb63d]"
                >
                  Write your first article
                </Link>
              </div>
            ) : (
              items.map((article) => {
                const isActive = activeId === article.id
                return (
                  <button
                    key={article.id}
                    onClick={() => setSelectedArticleId(article.id)}
                    className={`card-lift w-full rounded-2xl border p-4 text-left transition-colors ${
                      isActive
                        ? 'border-glow-amber/40 bg-raised shadow-[0_0_24px_rgba(245,165,36,0.12)]'
                        : 'border-line bg-surface hover:border-overlay/15'
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <div className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${isActive ? 'bg-glow-amber/15 text-glow-amber' : 'bg-overlay/5 text-muted'}`}>
                        <FileText className="h-4 w-4" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-semibold text-ink">
                          {article.title || article.keyword_phrase}
                        </p>
                        <div className="mt-2 flex items-center justify-between gap-2">
                          <p className="font-mono text-[11px] text-muted">
                            {new Date(article.created_at).toLocaleDateString()}
                          </p>
                          {statusBadge(article)}
                        </div>
                      </div>
                    </div>
                  </button>
                )
              })
            )}
          </div>
        </div>

        {/* Reader */}
        <div className="animate-fade-up">
          <GeneratedArticlePanel projectId={projectId} articleId={selectedArticleId} />
        </div>
      </div>
    </div>
  )
}
