import { Brain, Cpu, Database, Network } from 'lucide-react'
import { Card } from './ui/Card'
import { useEffect, useState } from 'react'

export function SemanticMetrics({ isActive = false }: { isActive?: boolean }) {
  const [activeNode, setActiveNode] = useState(0)

  // Rotate active node for visual effect
  useEffect(() => {
    if (!isActive) return
    const interval = setInterval(() => {
      setActiveNode((prev) => (prev + 1) % 4)
    }, 2000)
    return () => clearInterval(interval)
  }, [isActive])

  const metrics = [
    { label: 'Lexical Density', value: '94.2%', icon: Database, color: 'text-indigo-500', bg: 'bg-indigo-500' },
    { label: 'Ontology Confidence', value: '99.1%', icon: Brain, color: 'text-cyan-500', bg: 'bg-cyan-500' },
    { label: 'Cluster Resonance', value: '87.4%', icon: Network, color: 'text-emerald-500', bg: 'bg-emerald-500' },
    { label: 'Vector Mapping', value: isActive ? 'Active' : 'Standby', icon: Cpu, color: 'text-amber-500', bg: 'bg-amber-500' },
  ]

  return (
    <Card className="flex flex-col p-0">
      <div className="border-b border-slate-100 px-5 py-4 flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-slate-950 flex items-center gap-2">
            <Brain className="h-4 w-4 text-cyan-600" />
            Neural Processing Metrics
          </h3>
          <p className="text-xs text-slate-500 mt-1">Real-time entity extraction and vectorization</p>
        </div>
        <div className="flex items-center gap-2">
           <span className="relative flex h-2.5 w-2.5">
            {isActive && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-cyan-400 opacity-75"></span>}
            <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${isActive ? 'bg-cyan-500' : 'bg-slate-300'}`}></span>
          </span>
        </div>
      </div>
      
      <div className="p-5 grid gap-6">
        {/* Progress Bars */}
        <div className="space-y-4">
          <div>
            <div className="flex items-center justify-between text-xs font-semibold text-slate-700 mb-1">
              <span>Entity Resolution Pipeline</span>
              <span className={isActive ? 'text-cyan-600' : 'text-slate-400'}>{isActive ? 'Processing' : 'Idle'}</span>
            </div>
            <div className="h-1.5 w-full bg-slate-100 rounded-full overflow-hidden">
              <div className={`h-full ${isActive ? 'bg-cyan-500 animate-pulse' : 'bg-slate-200'} rounded-full w-3/4`}></div>
            </div>
          </div>
          <div>
            <div className="flex items-center justify-between text-xs font-semibold text-slate-700 mb-1">
              <span>SERP Intent Clustering</span>
              <span className="text-indigo-600">Synced</span>
            </div>
            <div className="h-1.5 w-full bg-slate-100 rounded-full overflow-hidden">
              <div className="h-full bg-indigo-500 rounded-full w-full"></div>
            </div>
          </div>
        </div>

        {/* Status Grid */}
        <div className="grid grid-cols-2 gap-4">
          {metrics.map((metric, idx) => {
            const Icon = metric.icon
            const isNodeActive = isActive && idx === activeNode
            return (
              <div 
                key={idx} 
                className={`flex items-center gap-3 p-3 rounded-lg border transition-all duration-500 ${isNodeActive ? 'border-cyan-200 bg-cyan-50/30' : 'border-slate-100 bg-slate-50/50'}`}
              >
                <div className={`p-2 rounded-md bg-white border border-slate-100 shadow-sm ${metric.color}`}>
                  <Icon className="h-4 w-4" />
                </div>
                <div>
                  <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">{metric.label}</div>
                  <div className={`text-sm font-bold ${isNodeActive ? 'text-slate-900' : 'text-slate-700'}`}>{metric.value}</div>
                </div>
              </div>
            )
          })}
        </div>

        {/* Terminal Log */}
        <div className="bg-slate-900 rounded-lg p-3 font-mono text-[10px] text-emerald-400 h-24 overflow-hidden relative">
          <style dangerouslySetInnerHTML={{__html: `
            @keyframes terminalScroll {
              0% { transform: translateY(0); }
              100% { transform: translateY(-50%); }
            }
            .animate-terminal {
              animation: terminalScroll 10s linear infinite;
            }
          `}} />
          <div className="absolute inset-0 bg-gradient-to-b from-transparent to-slate-900 z-10 pointer-events-none"></div>
          {isActive ? (
            <div className="space-y-1 animate-terminal">
              <p className="opacity-50">&gt; Initializing neural subnet...</p>
              <p className="opacity-60">&gt; Mapping competitor domain vectors...</p>
              <p className="opacity-70">&gt; Extracting semantic entities...</p>
              <p className="opacity-80">&gt; Aligning intent clusters...</p>
              <p className="opacity-90 text-cyan-400">&gt; Ontology framework compiled.</p>
              <p className="opacity-50">&gt; Verifying keyword gaps...</p>
              <p className="opacity-60">&gt; Correlating SERP resonance...</p>
              <p className="opacity-70">&gt; Generating predictive scores...</p>
              <p className="opacity-80">&gt; Optimizing LSI density...</p>
              <p className="opacity-90 text-cyan-400">&gt; Cycle complete. Awaiting next command.</p>
              {/* Duplicate for seamless scrolling */}
              <p className="opacity-50">&gt; Initializing neural subnet...</p>
              <p className="opacity-60">&gt; Mapping competitor domain vectors...</p>
              <p className="opacity-70">&gt; Extracting semantic entities...</p>
              <p className="opacity-80">&gt; Aligning intent clusters...</p>
              <p className="opacity-90 text-cyan-400">&gt; Ontology framework compiled.</p>
            </div>
          ) : (
            <div className="space-y-1 mt-4">
              <p className="opacity-50">&gt; System idle.</p>
              <p className="opacity-60">&gt; Waiting for next scan request...</p>
            </div>
          )}
        </div>
      </div>
    </Card>
  )
}
