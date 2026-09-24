import { Activity } from 'lucide-react'
import { Card } from './ui/Card'

export function SemanticMetrics({ isActive = false }: { isActive?: boolean }) {
  return (
    <Card className="p-5">
      <h3 className="flex items-center gap-2 font-semibold text-slate-950 dark:text-slate-50">
        <Activity className="h-4 w-4 text-cyan-600" />
        Scan activity
      </h3>
      <p className="mt-3 text-sm text-slate-600 dark:text-slate-400">
        {isActive ? 'Scan in progress. See Scan Progress for recorded results.' : 'No scan currently running.'}
      </p>
      <p className="mt-2 text-xs text-slate-500">
        Keyword quality confidence is not measured. Review each suggestion and its sources before planning content.
      </p>
    </Card>
  )
}
