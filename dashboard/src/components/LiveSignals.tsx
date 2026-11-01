import type { ScanProgress } from '../lib/api'
import { Cpu } from 'lucide-react'
import { Card } from './ui/Card'

interface LiveSignalsProps {
  isActive?: boolean
  progress?: ScanProgress
  error?: string | null
}

export function LiveSignals({ isActive = false, progress, error }: LiveSignalsProps) {
  const logs = [
    `Scan status: ${progress?.status || 'pending'}`,
    `URLs discovered: ${progress?.urls_found ?? 0}`,
    `Pages scraped: ${progress?.urls_processed ?? 0}`,
    `Pages failed: ${progress?.urls_failed ?? 0}`,
    ...(progress?.current_url ? [progress.current_url] : []),
    ...(error ? [error] : []),
  ]
  const percent = progress?.percent ?? 0

  return (
    <Card className="overflow-hidden p-0 h-[360px] flex flex-col">
      <div className="border-b border-line px-5 py-3 flex items-center justify-between shrink-0">
        <h3 className="flex items-center gap-2 font-mono text-[0.6875rem] font-semibold uppercase tracking-[0.14em] text-text">
          <Cpu className="h-4 w-4 text-amber" />
          Scan Progress
        </h3>
        {isActive ? (
          <span className="stamp stamp-amber">Scanning</span>
        ) : error ? (
          <span className="stamp stamp-red">Fault</span>
        ) : (
          <span className="stamp stamp-muted">Idle</span>
        )}
      </div>

      {/* Dashed instrument track with mono status annotations */}
      <div className="border-b border-line px-5 py-4 shrink-0">
        <div className="rounded-lg border border-dashed border-line p-3">
          <div className="mb-2 flex items-center justify-between font-mono text-[11px]">
            <span className="uppercase tracking-[0.14em] text-muted">Survey track</span>
            <span className="font-semibold text-amber">{percent}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full border border-line bg-ink">
            <div className="h-full bg-amber transition-all" style={{ width: `${Math.min(percent, 100)}%` }} />
          </div>
          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 font-mono text-[11px] text-muted">
            <span>STATUS <span className="text-text">{progress?.status || 'pending'}</span></span>
            <span>FOUND <span className="text-text">{progress?.urls_found ?? 0}</span></span>
            <span>SCRAPED <span className="text-text">{progress?.urls_processed ?? 0}</span></span>
            <span>FAILED <span className={(progress?.urls_failed ?? 0) > 0 ? 'text-red' : 'text-text'}>{progress?.urls_failed ?? 0}</span></span>
          </div>
        </div>
      </div>

      <div className="flex-1 p-4 font-mono text-xs overflow-y-auto">
        <div className="flex flex-col gap-2">
          {logs.map((log, idx) => (
            <div 
              key={idx} 
              className={`animate-in fade-in slide-in-from-bottom-2 duration-300 ${
                idx === logs.length - 1 ? 'text-amber' : 'text-muted'
              }`}
            >
              <span className="mr-2 text-amber/50">▸</span>{log}
            </div>
          ))}
          {isActive && (
            <div className="text-amber/70 animate-pulse mt-2">
              _
            </div>
          )}
        </div>
      </div>
    </Card>
  )
}
