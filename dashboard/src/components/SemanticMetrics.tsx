import { Card } from './ui/Card'

export function SemanticMetrics({ isActive = false }: { isActive?: boolean }) {
  return (
    <Card lift={false}>
      <h3 className="flex items-center gap-2 font-display font-bold text-ink">
        <span className={`relative flex h-2.5 w-2.5 ${isActive ? '' : 'opacity-40'}`}>
          {isActive && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-alive-green opacity-60" />}
          <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-alive-green" />
        </span>
        Scan activity
      </h3>
      <p className="mt-3 text-sm text-muted">
        {isActive ? 'Scan in progress. See the live feed for recorded results.' : 'No scan currently running.'}
      </p>
      <p className="mt-2 text-xs leading-relaxed text-muted/80">
        Keyword quality confidence is not measured. Review each suggestion and its sources before planning content.
      </p>
    </Card>
  )
}
