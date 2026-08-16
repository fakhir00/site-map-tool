
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

interface SourceData {
  source_type: string
  source_domain: string | null
  urls_found: number
  scraped_urls: number
}

interface CompetitorGraphProps {
  sources: SourceData[]
}

export function CompetitorGraph({ sources }: CompetitorGraphProps) {
  // Filter out the 'own' site and focus on competitors
  const competitors = sources.filter((s) => s.source_type !== 'own' && s.source_domain)

  if (competitors.length === 0) {
    return (
      <Card className="flex h-64 items-center justify-center bg-slate-950 p-0 text-slate-500">
        <p>No competitor data available for mapping.</p>
      </Card>
    )
  }

  // Format data for radar chart
  const data = competitors.map((c) => {
    // Trim 'www.' for cleaner display
    const name = c.source_domain?.replace('www.', '') || 'Unknown'
    return {
      subject: name,
      A: c.urls_found || 1, // Add 1 so 0 doesn't break the shape completely
      fullScore: Math.max(...competitors.map((comp) => comp.urls_found || 1))
    }
  })

  return (
    <Card className="overflow-hidden border-slate-800 bg-slate-950 p-0 shadow-2xl">
      <div className="border-b border-slate-800 px-5 py-4">
        <h3 className="flex items-center gap-2 font-semibold text-cyan-400">
          <span className="relative flex h-3 w-3">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-cyan-400 opacity-75"></span>
            <span className="relative inline-flex h-3 w-3 rounded-full bg-cyan-500"></span>
          </span>
          Competitor Intelligence Mapping
        </h3>
        <p className="mt-1 text-xs text-slate-400">
          Deep-scan structural footprint across top industry rivals
        </p>
      </div>
      
      <div className="relative h-[400px] w-full bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-slate-900 via-slate-950 to-black">
        {/* Decorative high-tech grid background overlay */}
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px]"></div>
        
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart cx="50%" cy="50%" outerRadius="70%" data={data}>
            <PolarGrid stroke="#334155" />
            <PolarAngleAxis 
              dataKey="subject" 
              tick={{ fill: '#94a3b8', fontSize: 11 }} 
            />
            <PolarRadiusAxis 
              angle={30} 
              domain={[0, 'auto']} 
              tick={false} 
              axisLine={false}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: 'rgba(15, 23, 42, 0.9)',
                borderColor: '#1e293b',
                borderRadius: '8px',
                color: '#f8fafc',
                boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.5)',
                backdropFilter: 'blur(4px)'
              }}
              itemStyle={{ color: '#06b6d4' }}
              formatter={(value: any) => [`${value} footprint nodes`, 'Detected']}
            />
            <Radar
              name="Detected Footprint"
              dataKey="A"
              stroke="#06b6d4"
              strokeWidth={2}
              fill="#06b6d4"
              fillOpacity={0.3}
              isAnimationActive={true}
              animationDuration={2500}
            />
          </RadarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}
