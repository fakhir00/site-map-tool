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
    <Card className="overflow-hidden p-0" lift={false}>
      <div className="flex items-center justify-between border-b border-line px-6 py-4">
        <div>
          <h3 className="flex items-center gap-2 font-display font-bold text-ink">
            <Activity className="h-4 w-4 text-glow-amber" />
            Competitor coverage
          </h3>
          <p className="mt-1 text-xs text-muted">
            Pages discovered on competitor websites
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="relative flex h-2.5 w-2.5">
            {isActive && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-alive-green opacity-60"></span>}
            <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${isActive ? 'bg-alive-green shadow-[0_0_10px_rgba(52,211,153,0.8)]' : 'bg-muted/40'}`}></span>
          </span>
          <span className="text-xs font-medium uppercase tracking-wider text-muted">{isActive ? 'Live' : 'Standby'}</span>
        </div>
      </div>

      <div className="relative h-[380px] w-full">
        {/* Subtle dark grid backdrop */}
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,#ffffff08_1px,transparent_1px),linear-gradient(to_bottom,#ffffff08_1px,transparent_1px)] bg-[size:28px_28px]"></div>

        {data.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
            <Activity className="h-8 w-8 text-muted/40" />
            <p className="text-sm font-medium text-ink">No competitor pages discovered yet</p>
            <p className="max-w-xs text-xs text-muted">Run a Gap Scan and this map will light up with the pages your competitors rank for.</p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <RadarChart cx="50%" cy="50%" outerRadius="68%" data={data}>
              <PolarGrid stroke="#2A3348" />
              <PolarAngleAxis
                dataKey="subject"
                tick={{ fill: '#9AA3B2', fontSize: 11, fontWeight: 500 }}
              />
              <PolarRadiusAxis
                angle={30}
                domain={[0, 'auto']}
                tick={false}
                axisLine={false}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#161B26',
                  borderColor: '#1C2230',
                  borderRadius: '12px',
                  color: '#F2F4F8',
                  boxShadow: '0 16px 40px rgba(0,0,0,0.5)',
                }}
                itemStyle={{ color: '#F5A524', fontWeight: 600 }}
                labelStyle={{ color: '#9AA3B2' }}
                formatter={(value) => [`${value} pages`, 'URLs found']}
              />
              <Radar
                name="URLs found"
                dataKey="A"
                stroke="#F5A524"
                strokeWidth={2.5}
                fill="#F5A524"
                fillOpacity={0.22}
                isAnimationActive={true}
                animationDuration={2200}
              />
              <Radar
                name="Baseline"
                dataKey="A"
                stroke="#A78BFA"
                strokeWidth={1}
                strokeDasharray="5 5"
                fill="transparent"
                isAnimationActive={true}
                animationDuration={2600}
              />
            </RadarChart>
          </ResponsiveContainer>
        )}
      </div>
    </Card>
  )
}
