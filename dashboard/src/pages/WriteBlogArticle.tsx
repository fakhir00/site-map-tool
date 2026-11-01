import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Clock3, FileText } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { api, type ArticleDraft, type ArticleListResponse } from '../lib/api'
import { Card } from '../components/ui/Card'
import { GeneratedArticlePanel } from '../components/GeneratedArticlePanel'

function dossierStamp(article: ArticleDraft) {
  if (article.status === 'passed') return <span className="stamp stamp-green">Passed</span>
  if (article.status === 'needs_revision') return <span className="stamp stamp-red">Needs revision</span>
  if (article.status === 'error') return <span className="stamp stamp-red">Error</span>
  return <span className="stamp stamp-amber">Generating</span>
}

export default function WriteBlogArticle() {
  const { projectId } = useParams<{ projectId: string }>()
  const [selectedArticleId, setSelectedArticleId] = useState<string | null>(null)

  const { data } = useQuery({
    queryKey: ['project-articles', projectId],
    queryFn: () => api.get<ArticleListResponse>(`/projects/${projectId}/articles`),
    enabled: Boolean(projectId),
    refetchInterval: (query) => query.state.data?.items.some((article) => article.status === 'generating') ? 4000 : false,
  })

  if (!projectId) {
    return <div>Project not found</div>
  }

  const isActive = (article: ArticleDraft) => selectedArticleId ? selectedArticleId === article.id : data?.items?.[0]?.id === article.id

  return (
    <div className="mx-auto max-w-7xl py-8">
      <div className="mb-6">
        <Link 
          to="/write-blog" 
          className="mb-4 inline-flex items-center gap-2 font-mono text-xs uppercase tracking-[0.14em] text-muted transition-colors hover:text-amber"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Blog Writer
        </Link>
        <p className="annotation">ARTICLE STUDIO — DOSSIER FILES</p>
        <h1 className="mt-2 font-display text-3xl font-bold tracking-tight text-text">Article Studio</h1>
      </div>
      
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
        <div>
          <Card className="p-4">
            <h3 className="mb-4 flex items-center gap-2 font-display font-semibold text-text">
              <Clock3 className="h-4 w-4 text-amber" />
              History
            </h3>
            <div className="space-y-3">
              {data?.items?.length === 0 ? (
                <div className="bg-blueprint rounded-xl border-2 border-dashed border-line p-6 text-center">
                  <p className="annotation mx-auto max-w-[16rem]">No articles filed yet. Commission one from the Blog Writer slip.</p>
                </div>
              ) : (
                data?.items?.map((article) => {
                  const active = isActive(article)
                  return (
                    <button
                      key={article.id}
                      onClick={() => setSelectedArticleId(article.id)}
                      className={`block w-full rounded-xl border p-3.5 text-left transition-colors ${
                        active
                          ? 'border-amber/70 bg-raised shadow-[0_6px_20px_-8px_rgba(245,165,36,0.4)]'
                          : 'border-line bg-ink hover:border-amber/40 hover:bg-raised'
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <FileText className={`mt-0.5 h-4 w-4 shrink-0 ${active ? 'text-amber' : 'text-muted'}`} />
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-semibold text-text">{article.title || article.keyword_phrase}</p>
                          <p className="mt-1 font-mono text-[0.6875rem] uppercase tracking-[0.12em] text-muted">{new Date(article.created_at).toLocaleDateString()}</p>
                        </div>
                      </div>
                      <div className="mt-3">{dossierStamp(article)}</div>
                    </button>
                  )
                })
              )}
            </div>
          </Card>
        </div>

        <div>
          {/* We pass the active article to the panel if we modify the panel to support it, 
              but since the panel currently just takes the latest (item 0) from the query, 
              let's update GeneratedArticlePanel to accept an optional articleId prop, 
              or just leave it as is if they only care about latest. 
              Actually, passing articleId is better. */}
          <GeneratedArticlePanel projectId={projectId} articleId={selectedArticleId} />
        </div>
      </div>
    </div>
  )
}
