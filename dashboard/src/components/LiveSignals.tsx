import { useEffect, useState } from 'react'
import { Terminal, Cpu } from 'lucide-react'
import { Card } from './ui/Card'

interface LiveSignalsProps {
  isActive?: boolean
}

const FAKE_LOGS = [
  "Extracting topical relevance vectors...",
  "Running TF-IDF baseline against competitors...",
  "Entity disambiguation complete.",
  "Mapping search intent clusters...",
  "Detecting semantic gaps in layer 2...",
  "Calibrating keyword difficulty algorithms...",
  "Bypassing generic informational patterns...",
  "Isolating high-conversion 'Money' spokes...",
  "Scoring topical authority for root domain...",
  "Aggregating LSI variations...",
  "Constructing neural knowledge graph..."
]

export function LiveSignals({ isActive = false }: LiveSignalsProps) {
  const [logs, setLogs] = useState<string[]>([])

  useEffect(() => {
    if (!isActive) {
      setLogs(["System idle. Waiting for next gap scan..."])
      return
    }

    setLogs(["Initializing semantic engine..."])
    const interval = setInterval(() => {
      setLogs((prev) => {
        const nextLog = FAKE_LOGS[Math.floor(Math.random() * FAKE_LOGS.length)]
        const newLogs = [...prev, `[${new Date().toLocaleTimeString()}] ${nextLog}`]
        return newLogs.slice(-6) // Keep only the last 6 logs
      })
    }, 2500)

    return () => clearInterval(interval)
  }, [isActive])

  return (
    <Card className="overflow-hidden p-0 h-[300px] flex flex-col bg-slate-950 dark:bg-black border-slate-800">
      <div className="border-b border-slate-800 bg-slate-900 px-5 py-3 flex items-center justify-between">
        <h3 className="flex items-center gap-2 font-semibold text-slate-100 text-sm">
          <Cpu className="h-4 w-4 text-emerald-400" />
          Neural Processing Log
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
