import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Tooltip
} from 'recharts'
import { Card } from './ui/Card'
import { Activity } from 'lucide-react'

interface SourceData {
  source_type: string
  source_domain: string | null
  urls_found: number
  scraped_urls: number
}

interface CompetitorGraphProps {
  sources: SourceData[]
  isActive?: boolean
}

export function CompetitorGraph({ sources, isActive = false }: CompetitorGraphProps) {
  const competitors = sources.filter((s) => s.source_type === 'competitor' && s.source_domain)
  const data = competitors.map((source) => ({
    subject: source.source_domain?.replace(/^https?:\/\//, ''),
    A: source.urls_found,
  }))

  return (
    <Card className="overflow-hidden p-0">
      <div className="border-b border-slate-200 dark:border-line px-5 py-4 flex items-center justify-between">
        <div>
          <h3 className="flex items-center gap-2 font-semibold text-slate-950 dark:text-text">
            <Activity className="h-4 w-4 text-cyan-600 dark:text-cyan-500" />
            Competitor Coverage
          </h3>
          <p className="mt-1 text-xs text-slate-500 dark:text-muted">
            Pages discovered on competitor websites
          </p>
        </div>
        <div className="flex items-center gap-2">
           <span className="relative flex h-2.5 w-2.5">
            {isActive && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-cyan-400 opacity-75"></span>}
            <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${isActive ? 'bg-cyan-500' : 'bg-slate-300 dark:bg-raised'}`}></span>
          </span>
          <span className="text-xs font-medium text-slate-500 dark:text-muted uppercase tracking-wider">{isActive ? 'Active' : 'Standby'}</span>
        </div>
      </div>
      
      <div className="relative h-[400px] w-full bg-slate-50/50 dark:bg-panel/70">
        {/* Subtle grid background to look high-tech but light-themed */}
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,#8080800a_1px,transparent_1px),linear-gradient(to_bottom,#8080800a_1px,transparent_1px)] bg-[size:24px_24px]"></div>
        
        {data.length === 0 ? <div className="flex h-full items-center justify-center text-sm text-slate-500">No competitor pages discovered yet.</div> : <ResponsiveContainer width="100%" height="100%">
          <RadarChart cx="50%" cy="50%" outerRadius="70%" data={data}>
            <PolarGrid stroke="#e2e8f0" />
            <PolarAngleAxis 
              dataKey="subject" 
              tick={{ fill: '#64748b', fontSize: 11, fontWeight: 500 }} 
            />
            <PolarRadiusAxis 
              angle={30} 
              domain={[0, 'auto']} 
              tick={false} 
              axisLine={false}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: 'rgba(255, 255, 255, 0.95)',
                borderColor: '#e2e8f0',
                borderRadius: '8px',
                color: '#0f172a',
                boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
                backdropFilter: 'blur(4px)'
              }}
              itemStyle={{ color: '#0891b2', fontWeight: 600 }}
              formatter={(value) => [`${value} pages`, 'URLs found']}
            />
            <Radar
              name="URLs found"
              dataKey="A"
              stroke="#06b6d4"
              strokeWidth={2}
              fill="#06b6d4"
              fillOpacity={0.15}
              isAnimationActive={true}
              animationDuration={2500}
            />
            {/* Adding a second radar polygon for a more complex look */}
            <Radar
              name="Baseline"
              dataKey="A"
              stroke="#6366f1"
              strokeWidth={1}
              strokeDasharray="4 4"
              fill="transparent"
              isAnimationActive={true}
              animationDuration={3000}
            />
          </RadarChart>
        </ResponsiveContainer>}
      </div>
    </Card>
  )
}

