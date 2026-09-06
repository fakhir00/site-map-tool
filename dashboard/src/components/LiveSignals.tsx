import type { ScanProgress } from '../lib/api'
import { Terminal, Cpu } from 'lucide-react'
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
    <Card className="overflow-hidden p-0 h-[300px] flex flex-col bg-slate-950 dark:bg-black border-slate-800">
      <div className="border-b border-slate-800 bg-slate-900 px-5 py-3 flex items-center justify-between">
        <h3 className="flex items-center gap-2 font-semibold text-slate-100 text-sm">
          <Cpu className="h-4 w-4 text-emerald-400" />
          Scan Progress
        </h3>
        <span className="flex items-center gap-2 text-xs font-mono text-slate-400">
          <Terminal className="h-3 w-3" />
          TTY-1
        </span>
      </div>
      <div className="flex-1 p-4 font-mono text-xs overflow-hidden relative">
        <div className="absolute inset-0 bg-[linear-gradient(to_bottom,transparent_0%,rgba(0,0,0,0.4)_100%)] pointer-events-none z-10" />
        <div className="flex flex-col gap-2 relative z-0">
          {logs.map((log, idx) => (
            <div 
              key={idx} 
              className={`animate-in fade-in slide-in-from-bottom-2 duration-300 ${
                idx === logs.length - 1 ? 'text-emerald-400' : 'text-slate-500'
              }`}
            >
              {log}
            </div>
          ))}
          {isActive && (
            <div className="text-emerald-400/70 animate-pulse mt-2">
              _
            </div>
          )}
        </div>
      </div>
    </Card>
  )
}
