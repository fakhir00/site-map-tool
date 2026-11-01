import type { ScanProgress } from '../lib/api'
import { Terminal, Radio } from 'lucide-react'
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

  return (
    <Card className="flex h-[300px] flex-col overflow-hidden border-line bg-abyss p-0" lift={false}>
      <div className="flex shrink-0 items-center justify-between border-b border-line bg-raised px-5 py-3">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-ink">
          <span className="relative flex h-2.5 w-2.5">
            {isActive && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-alive-green opacity-60" />}
            <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${isActive ? 'bg-alive-green shadow-[0_0_10px_rgba(52,211,153,0.8)]' : 'bg-muted/40'}`} />
          </span>
          <Radio className="h-4 w-4 text-alive-green" />
          Live scan feed
        </h3>
        <span className="flex items-center gap-1.5 font-mono text-xs text-muted">
          <Terminal className="h-3 w-3" />
          crawl-01
        </span>
      </div>
      <div className="relative flex-1 overflow-hidden p-4 font-mono text-xs">
        <div className="pointer-events-none absolute inset-0 z-10 bg-[linear-gradient(to_bottom,transparent_0%,rgba(11,14,20,0.6)_100%)]" />
        <div className="relative z-0 flex flex-col gap-2">
          {logs.map((log, idx) => (
            <div
              key={idx}
              className={`break-words leading-relaxed ${
                idx === logs.length - 1 ? 'text-alive-green' : 'text-muted/80'
              }`}
            >
              <span className="mr-2 text-muted/40">{String(idx).padStart(2, '0')}</span>
              {log}
            </div>
          ))}
          {isActive && (
            <div className="mt-1 animate-pulse text-alive-green/70">
              <span className="mr-2 text-muted/40">{String(logs.length).padStart(2, '0')}</span>▊
            </div>
          )}
        </div>
      </div>
    </Card>
  )
}
