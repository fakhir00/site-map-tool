import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { RefreshCw, Network } from 'lucide-react'
import { api } from '../lib/api'
import { Button } from './ui/Button'

interface HubSpokeViewProps {
  projectId: string
}

interface NewSchemaLayer {
  [layerName: string]: string[]
}

interface NewSchemaHub {
  hub_title: string
  layers: NewSchemaLayer
}

interface NewSchema {
  hubs: NewSchemaHub[]
}

interface TierMetadataEntry {
  tier: 'merge' | 'subheading_group' | 'related' | 'outlier' | null
  article_title: string | null
  h_tags: string[] | null
  merged_from: string[] | null
  cluster_group_id: string | null
  sub_silo_id: number | null
}

type OldSchema = Record<string, any>
type ClusterData = NewSchema | OldSchema

function TreeDot({ tier }: { tier: string | null }) {
  if (tier === 'merge') return <div className="w-2.5 h-2.5 rounded-full bg-blue-500 shrink-0" />
  if (tier === 'subheading_group') return <div className="w-2.5 h-2.5 rounded-full bg-purple-500 shrink-0" />
  if (tier === 'related') return <div className="w-2.5 h-2.5 rounded-full bg-green-500 shrink-0" />
  return <div className="w-2.5 h-2.5 rounded-full bg-slate-300 dark:bg-slate-200 shrink-0" />
}

function TreeAnnotation({ tier, tierInfo }: { tier: string | null, tierInfo: any }) {
  if (tier === 'merge' && tierInfo?.merged_from) {
    return (
      <span 
        className="text-[12px] text-slate-500 cursor-help" 
        title={`Merged: ${tierInfo.merged_from.join(', ')}`}
      >
        [merged - {tierInfo.merged_from.length + 1} dupes combined]
      </span>
    )
  }
  if (tier === 'subheading_group') {
    return <span className="text-[12px] text-slate-500">[multi-intent article - {tierInfo?.h_tags?.length || 0} H-tags ▾]</span>
  }
  if (tier === 'related') {
    return <span className="text-[12px] text-slate-500">↔ linked</span>
  }
  if (tier === 'outlier') {
    return <span className="text-[12px] text-slate-500">[outlier]</span>
  }
  return null
}

function slugify(text: string) {
  return text
    .toString()
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^\w\-]+/g, '')
    .replace(/\-\-+/g, '-')
    .replace(/^-+/, '')
    .replace(/-+$/, '')
}

function TreeHub({
  hub,
  onWrite,
  tierMetadata,
}: {
  hub: NewSchemaHub
  onWrite: (keyword: string, instruction: string) => void
  tierMetadata: Record<string, TierMetadataEntry>
}) {
  const layerEntries = Object.entries(hub.layers || {})
  
  // Clean hub title for slug (remove "MASTER HUB: " or similar prefixes if they exist)
  const cleanHubTitle = hub.hub_title.replace(/^.*?:\s*/, '')
  const hubSlug = `/${slugify(cleanHubTitle)}`

  return (
    <div className="mb-12 font-mono text-sm max-w-[1000px] w-full">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-slate-900 dark:text-slate-100 uppercase tracking-wide whitespace-pre-wrap">
          {hub.hub_title}
        </h3>
        <button 
          onClick={() => onWrite(hub.hub_title, "INSTRUCTION: This is a Hub/Pillar page. It MUST be an extensive, comprehensive guide of 3000+ words. Cover the topic thoroughly.")} 
          className="text-xs text-cyan-600 hover:text-cyan-500 hover:underline font-mono ml-4 shrink-0"
        >
          [ write hub ]
        </button>
      </div>
      <div className="border-b-[3px] border-double border-slate-300 dark:border-slate-600 mb-8 w-full"></div>

      <div className="flex flex-col gap-8">
        {layerEntries.map(([layerName, spokes], idx) => (
          <div key={idx} className="flex flex-col gap-2">
            <h4 className="text-slate-800 dark:text-slate-200 mb-2 whitespace-pre-wrap">{layerName}</h4>
            
            {(!spokes || spokes.length === 0) ? (
              <div className="text-slate-400 italic pl-4">No keywords in this layer.</div>
            ) : (
              spokes.map((spoke, sIdx) => {
                const match = spoke.match(/(.*?)\s*\(Target Keyword:\s*(.*?)\)/i)
                const displayTitle = match ? match[1].trim() : spoke.trim()
                const targetKeyword = match ? match[2].trim() : null

                const tierInfo = targetKeyword ? tierMetadata[targetKeyword.toLowerCase()] : null
                const tier = tierInfo?.tier || null
                
                const finalTitle = (tier === 'subheading_group' && tierInfo?.article_title) ? tierInfo.article_title : displayTitle
                const isSubheading = tier === 'subheading_group'
                
                const spokeSlug = `${hubSlug}/${slugify(finalTitle)}`

                return (
                  <div key={sIdx} className="flex flex-col">
                    <div className="flex flex-wrap sm:flex-nowrap items-start sm:items-center justify-between group py-1 gap-2 sm:gap-4">
                      <div className="flex items-center gap-3 w-full">
                        <span className="text-slate-400 dark:text-slate-500 select-none shrink-0">├──</span>
                        <TreeDot tier={tier} />
                        <span className="text-[10px] text-emerald-600/80 dark:text-emerald-500/70 font-mono whitespace-nowrap shrink-0">
                          {spokeSlug}
                        </span>
                        <span className="text-slate-700 dark:text-slate-300 group-hover:text-cyan-600 dark:group-hover:text-cyan-400 transition-colors break-words min-w-0 truncate">
                          {isSubheading ? `"${finalTitle}"` : finalTitle}
                        </span>
                      </div>
                      
                      <div className="flex items-center gap-4 ml-6 sm:ml-auto w-full sm:w-auto justify-end">
                        <button 
                          onClick={() => onWrite(targetKeyword || finalTitle, "INSTRUCTION: This is a Spoke article supporting a main hub. It MUST be a detailed, focused article of 1500+ words.")} 
                          className="sm:opacity-0 group-hover:opacity-100 text-[11px] text-cyan-600 hover:text-cyan-500 hover:underline transition-opacity shrink-0"
                        >
                          [ write ]
                        </button>
                        <div className="shrink-0 text-right">
                          <TreeAnnotation tier={tier} tierInfo={tierInfo} />
                        </div>
                      </div>
                    </div>
                    
                    {/* Subheading tags rendering */}
                    {isSubheading && tierInfo?.h_tags && tierInfo.h_tags.length > 0 && (
                      <div className="flex flex-col ml-1.5 pl-9 border-l border-slate-300 dark:border-slate-700 py-1 mb-2 gap-1 text-[12px] text-slate-500 dark:text-slate-400">
                        {tierInfo.h_tags.map((htag, hIdx) => (
                          <div key={hIdx} className="flex items-center gap-2">
                            <span className="select-none text-slate-400 dark:text-slate-600">↳ H2:</span>
                            <span>{htag}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function OldTreeHub({ hub, spokes }: { hub: string; spokes: string[] }) {
  return (
    <div className="mb-10 font-mono text-sm max-w-5xl">
      <div className="mb-2">
        <h3 className="text-slate-900 dark:text-slate-100 uppercase tracking-wide">{hub}</h3>
      </div>
      <div className="border-b-[3px] border-double border-slate-300 dark:border-slate-600 mb-6 w-full"></div>
      <div className="flex flex-col gap-1">
        {spokes.map((spoke, idx) => (
          <div key={idx} className="flex items-center gap-3 py-1 text-slate-700 dark:text-slate-300">
            <span className="text-slate-400 dark:text-slate-500 select-none">├──</span>
            <div className="w-2.5 h-2.5 rounded-full bg-slate-300 dark:bg-slate-600 shrink-0" />
            <span>{spoke}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function HubSpokeView({ projectId }: HubSpokeViewProps) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const { data, isLoading } = useQuery({
    queryKey: ['hub-spoke', projectId],
    queryFn: () => api.get<{ clusters: ClusterData | null; tier_metadata?: Record<string, TierMetadataEntry> }>(`/projects/${projectId}/keywords/hub-spoke`),
  })

  const clusterMutation = useMutation({
    mutationFn: () => api.post<{ clusters: ClusterData }>(`/projects/${projectId}/keywords/hub-spoke`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hub-spoke', projectId] })
    },
  })

  const manualMutation = useMutation({
    mutationFn: ({ main_keyword, keyword_cluster }: { main_keyword: string, keyword_cluster: string }) => 
      api.postArticle<{ project_id: string }>('/projects/manual-generate', { main_keyword, keyword_cluster, project_id: projectId }),
    onSuccess: (data: { project_id: string }) => {
      queryClient.invalidateQueries({ queryKey: ['project-articles', data.project_id] })
      navigate(`/write-blog/${data.project_id}`)
    }
  })

  const handleWrite = (keyword: string, instruction: string) => {
    manualMutation.mutate({ main_keyword: keyword, keyword_cluster: instruction })
  }

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-slate-500 dark:text-slate-400 font-sans">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-200 border-t-cyan-600 dark:border-slate-800 dark:border-t-cyan-400" />
        <p className="mt-4 text-sm font-medium">Loading architecture...</p>
      </div>
    )
  }

  const clusters = data?.clusters
  const tierMetadata = data?.tier_metadata || {}

  if (!clusters || Object.keys(clusters).length === 0) {
    return (
      <div className="flex flex-col items-center justify-center px-4 py-16 text-center font-sans">
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800">
          <Network className="h-6 w-6 text-slate-400 dark:text-slate-500" />
        </div>
        <h3 className="mb-1 text-lg font-bold text-slate-950 dark:text-slate-50">No Hubs & Spokes Generated</h3>
        <p className="mb-6 max-w-sm text-sm text-slate-500 dark:text-slate-400">
          Group your keywords into a semantic Hub and Spoke architecture to maximize topical authority.
        </p>
        <Button 
          onClick={() => clusterMutation.mutate()} 
          disabled={clusterMutation.isPending}
          className="bg-cyan-600 hover:bg-cyan-700"
        >
          {clusterMutation.isPending ? 'Generating Architecture...' : 'Generate Hub & Spoke'}
        </Button>
      </div>
    )
  }

  const isNewSchema = 'hubs' in clusters && Array.isArray((clusters as NewSchema).hubs)

  return (
    <div className="p-4 md:p-8 bg-[#fafafa] dark:bg-[#18181b] min-h-[500px] font-mono rounded-lg border border-slate-200 dark:border-slate-800/60 shadow-inner">
      <div className="mb-10 flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 dark:border-slate-800 pb-6">
        <div>
          <h4 className="text-xl font-bold text-slate-900 dark:text-slate-50 tracking-tight font-sans">Topical Map</h4>
          <p className="text-sm text-slate-500 dark:text-slate-400 font-sans mt-1">Terminal view of your SEO architecture</p>
        </div>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-slate-600 dark:text-slate-400 font-sans">
          <div className="flex items-center gap-2"><TreeDot tier="merge" /> Merged</div>
          <div className="flex items-center gap-2"><TreeDot tier="subheading_group" /> Multi-intent</div>
          <div className="flex items-center gap-2"><TreeDot tier="related" /> Linked</div>
          <div className="flex items-center gap-2"><TreeDot tier="outlier" /> Outlier</div>
          <Button 
            variant="secondary" 
            size="sm" 
            onClick={() => clusterMutation.mutate()}
            disabled={clusterMutation.isPending}
            className="ml-0 md:ml-4"
          >
            <RefreshCw className={`mr-2 h-3 w-3 ${clusterMutation.isPending ? 'animate-spin' : ''}`} />
            {clusterMutation.isPending ? 'Re-building...' : 'Re-build'}
          </Button>
        </div>
      </div>

      <div className="flex flex-col overflow-x-auto pb-8">
        {isNewSchema ? (
          <div className="flex flex-col gap-4">
            {(clusters as NewSchema).hubs.map((hub, i) => (
              <TreeHub key={i} hub={hub} onWrite={handleWrite} tierMetadata={tierMetadata} />
            ))}
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {Object.entries(clusters).map(([category, hubMap]) => {
              if (Array.isArray(hubMap)) {
                return <OldTreeHub key={category} hub={category} spokes={hubMap} />
              } else {
                return Object.entries(hubMap).map(([hub, spokes]) => (
                  <OldTreeHub key={`${category}-${hub}`} hub={hub} spokes={spokes as string[]} />
                ))
              }
            })}
          </div>
        )}
      </div>
    </div>
  )
}
