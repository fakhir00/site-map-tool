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
      <div className="border-b border-line px-5 py-4 flex items-center justify-between">
        <div>
          <h3 className="flex items-center gap-2 font-mono text-[0.6875rem] font-semibold uppercase tracking-[0.14em] text-text">
            <Activity className="h-4 w-4 text-amber" />
            Competitor Coverage
          </h3>
          <p className="annotation mt-2">
            Pages discovered on competitor websites
          </p>
        </div>
        <div className="flex items-center gap-2">
           <span className="relative flex h-2.5 w-2.5">
            {isActive && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber opacity-75"></span>}
            <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${isActive ? 'bg-amber' : 'bg-line'}`}></span>
          </span>
          <span className="font-mono text-[0.6875rem] uppercase tracking-[0.14em] text-muted">{isActive ? 'Active' : 'Standby'}</span>
        </div>
      </div>
      
      <div className="bg-blueprint relative h-[400px] w-full">
        {data.length === 0 ? <div className="flex h-full items-center justify-center px-6 text-center"><p className="annotation">No competitor pages discovered yet.</p></div> : <ResponsiveContainer width="100%" height="100%">
          <RadarChart cx="50%" cy="50%" outerRadius="70%" data={data}>
            <PolarGrid stroke="#1E3A5F" />
            <PolarAngleAxis 
              dataKey="subject" 
              tick={{ fill: '#93A8C4', fontSize: 11, fontFamily: "'JetBrains Mono', monospace" }} 
            />
            <PolarRadiusAxis 
              angle={30} 
              domain={[0, 'auto']} 
              tick={false} 
              axisLine={false}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#0B1F3A',
                borderColor: '#1E3A5F',
                borderRadius: '8px',
                color: '#EAF2FB',
                boxShadow: '0 12px 32px -16px rgba(0, 0, 0, 0.6)',
              }}
              labelStyle={{ color: '#93A8C4', fontFamily: "'JetBrains Mono', monospace", fontSize: 11 }}
              itemStyle={{ color: '#F5A524', fontWeight: 600, fontFamily: "'JetBrains Mono', monospace" }}
              formatter={(value) => [`${value} pages`, 'URLs found']}
            />
            <Radar
              name="URLs found"
              dataKey="A"
              stroke="#F5A524"
              strokeWidth={2}
              fill="#F5A524"
              fillOpacity={0.15}
              isAnimationActive={true}
              animationDuration={2500}
            />
            {/* Dashed sky baseline for a measured-drawing look */}
            <Radar
              name="Baseline"
              dataKey="A"
              stroke="#38BDF8"
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
