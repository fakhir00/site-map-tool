import { useParams, Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { GeneratedArticlePanel } from '../components/GeneratedArticlePanel'

export default function WriteBlogArticle() {
  const { projectId } = useParams<{ projectId: string }>()

  if (!projectId) {
    return <div>Project not found</div>
  }

  return (
    <div className="mx-auto max-w-5xl py-8">
      <div className="mb-6">
        <Link 
          to="/write-blog" 
          className="inline-flex items-center gap-2 text-sm font-medium text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-50 mb-4"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Write Blog
        </Link>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-50">Write Blog Article</h1>
      </div>
      
      <GeneratedArticlePanel projectId={projectId} />
    </div>
  )
}
