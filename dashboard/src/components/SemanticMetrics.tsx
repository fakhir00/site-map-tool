import { Activity } from 'lucide-react'
import { Card } from './ui/Card'

export function SemanticMetrics({ isActive = false }: { isActive?: boolean }) {
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 font-mono text-[0.6875rem] font-semibold uppercase tracking-[0.14em] text-text">
          <Activity className="h-4 w-4 text-amber" />
          Scan activity
        </h3>
        {isActive ? (
          <span className="stamp stamp-amber">In progress</span>
        ) : (
          <span className="stamp stamp-muted">Standby</span>
        )}
      </div>
      <p className="mt-3 text-sm text-muted">
        {isActive ? 'Scan in progress. See Scan Progress for recorded results.' : 'No scan currently running.'}
      </p>
      <p className="annotation mt-3">
        Keyword quality confidence is not measured. Review each suggestion and its sources before planning content.
      </p>
    </Card>
  )
}
