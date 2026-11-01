import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Clock, FileText } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { api, type ArticleListResponse } from '../lib/api'
import { GeneratedArticlePanel } from '../components/GeneratedArticlePanel'

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

  return (
    <div className="mx-auto max-w-7xl py-8">
      <div className="mb-6">
        <Link 
          to="/write-blog" 
          className="inline-flex items-center gap-2 text-sm font-medium text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-50 mb-4"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Blog Writer
        </Link>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-50">Article Studio</h1>
      </div>
      
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[300px_1fr]">
        <div className="space-y-4">
          <div className="rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-4">
            <h3 className="mb-4 flex items-center gap-2 font-semibold text-slate-950 dark:text-slate-50">
              <Clock className="h-4 w-4" />
              History
            </h3>
            <div className="space-y-2">
              {data?.items?.length === 0 ? (
                <p className="text-sm text-slate-500 dark:text-slate-400">No articles generated yet.</p>
              ) : (
                data?.items?.map((article) => (
                  <button
                    key={article.id}
                    onClick={() => setSelectedArticleId(article.id)}
                    className={`flex w-full items-start gap-3 rounded-md px-3 py-2 text-left transition-colors ${
                      (selectedArticleId ? selectedArticleId === article.id : data?.items?.[0]?.id === article.id)
                        ? 'bg-cyan-50 text-cyan-900 dark:bg-cyan-900/30 dark:text-cyan-50'
                        : 'hover:bg-slate-50 dark:hover:bg-slate-800'
                    }`}
                  >
                    <FileText className={`mt-0.5 h-4 w-4 shrink-0 ${(selectedArticleId ? selectedArticleId === article.id : data?.items?.[0]?.id === article.id) ? 'text-cyan-600 dark:text-cyan-400' : 'text-slate-400'}`} />
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{article.title || article.keyword_phrase}</p>
                      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{new Date(article.created_at).toLocaleDateString()}</p>
                    </div>
                  </button>
                ))
              )}
            </div>
          </div>
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
