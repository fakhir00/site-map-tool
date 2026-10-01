import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { RefreshCw, Network, Download } from 'lucide-react'
import { api } from '../lib/api'
import { Button } from './ui/Button'

interface HubSpokeViewProps {
  projectId: string
  search?: string
  type?: string
}

interface NewSchemaLayer {
  [layerName: string]: string[]
}

interface NewSchemaHub {
  hub_title: string
  target_keyword?: string
  h2_keywords?: string[]
  layers: NewSchemaLayer
  sub_silos?: NewSchemaHub[]
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
  keyword_type?: string
}

type OldSchema = Record<string, string[] | Record<string, string[]>>
type ClusterData = NewSchema | OldSchema

function shouldBuildTool(keyword: string) {
  const toolIntent = /\b(tool|software|calculator|generator|maker|builder|creator|checker|converter|app)\b/i
  const informationalIntent = /^(how|what|why|when|where|can|does)\b|\b(guide|tutorial|examples|symbols|definition|meaning|tips|troubleshooting|review|comparison|alternatives|vs)\b/i
  return toolIntent.test(keyword) && !informationalIntent.test(keyword)
}

function TreeDot({ tier }: { tier: string | null }) {
  if (tier === 'merge') return <div className="w-2.5 h-2.5 rounded-full bg-blue-500 shrink-0" />
  if (tier === 'subheading_group') return <div className="w-2.5 h-2.5 rounded-full bg-purple-500 shrink-0" />
  if (tier === 'related') return <div className="w-2.5 h-2.5 rounded-full bg-green-500 shrink-0" />
  return <div className="w-2.5 h-2.5 rounded-full bg-slate-300 dark:bg-slate-200 shrink-0" />
}

function TreeAnnotation({ tier, tierInfo }: { tier: string | null, tierInfo: TierMetadataEntry | null | undefined }) {
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
    return <span className="text-[12px] text-slate-500">[{tierInfo?.h_tags?.length || 0} related keywords included ▾]</span>
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
    .replace(/[^\w-]+/g, '')
    .replace(/--+/g, '-')
    .replace(/^-+/, '')
    .replace(/-+$/, '')
}

function TreeHub({
  hub,
  onWrite,
  tierMetadata,
  isSubSilo = false,
}: {
  hub: NewSchemaHub
  onWrite: (keyword: string, instruction: string, included?: string[]) => void
  tierMetadata: Record<string, TierMetadataEntry>
  isSubSilo?: boolean
}) {
  const layerEntries = Object.entries(hub.layers || {})
  
  // Clean hub title to extract target keyword if AI provided it in the string fallback
  const hubMatch = hub.hub_title.match(/(.*?)\s*[([]?Target Keyword:\s*([^)\]]+)[)\]]?/i)
  const displayHubTitle = hubMatch ? hubMatch[1].trim() : hub.hub_title.trim()
  const hubTargetKeyword = hub.target_keyword || (hubMatch ? hubMatch[2].trim() : null)

  // Clean hub title for slug (remove "MASTER HUB: " or similar prefixes if they exist)
  let cleanHubTitle = displayHubTitle.replace(/^.*?:\s*/, '').trim()
  
  // If it's a sub-silo formatted like "Category Name — Sub-Topic Overview", extract just the category
  if (cleanHubTitle.includes('—')) {
    cleanHubTitle = cleanHubTitle.split('—')[0].trim()
  }
  
  const hubSlugSource = hubTargetKeyword || cleanHubTitle
  const hubSlug = `/${slugify(hubSlugSource)}`

  return (
    <div className={`mb-12 font-mono text-sm max-w-[1000px] w-full ${isSubSilo ? 'ml-8 border-l-2 border-slate-200 dark:border-slate-700 pl-6 mt-8' : ''}`}>
      <div className="flex items-start justify-between mb-2">
        <div className="flex flex-col gap-1">
          <button type="button" onClick={() => onWrite(hubTargetKeyword || displayHubTitle, "hub page", hub.h2_keywords)} className="text-left text-slate-900 hover:text-cyan-700 dark:text-slate-100 dark:hover:text-cyan-300 uppercase tracking-wide whitespace-pre-wrap">
            {displayHubTitle}
          </button>
          <span className="text-[10px] text-emerald-600/80 dark:text-emerald-500/70 font-mono">
            {hubSlug}/
          </span>
        </div>
        <button 
          onClick={() => onWrite(hubTargetKeyword || displayHubTitle, "hub page", hub.h2_keywords)}
          className="text-xs text-cyan-600 hover:text-cyan-500 hover:underline font-mono ml-4 shrink-0 mt-0.5"
        >
          [ write hub ]
        </button>
      </div>
      <div className="border-b-[3px] border-double border-slate-300 dark:border-slate-600 mb-8 w-full"></div>

      {hub.h2_keywords && hub.h2_keywords.length > 0 && (
        <div className="mb-6 rounded-lg border border-cyan-200 bg-cyan-50 p-3 text-xs text-slate-700 dark:border-cyan-900 dark:bg-cyan-950/30 dark:text-slate-300">
          <span className="font-bold text-cyan-800 dark:text-cyan-300">Includes:</span> {hub.h2_keywords.join(' • ')}
        </div>
      )}

      <div className="flex flex-col gap-8">
        {layerEntries.map(([layerName, spokes], idx) => (
          <div key={idx} className="flex flex-col gap-2">
            <h4 className="text-slate-800 dark:text-slate-200 mb-2 whitespace-pre-wrap">{layerName}</h4>
            
            {(!spokes || spokes.length === 0) ? (
              <div className="text-slate-400 italic pl-4">No keywords in this layer.</div>
            ) : (
              spokes.map((spoke, sIdx) => {
                const match = spoke.match(/(.*?)\s*[([]?Target Keyword:\s*([^)\]]+)[)\]]?(?:\s*\[(.*?)\])?/i)
                const displayTitle = match ? match[1].trim() : spoke.trim()
                const targetKeyword = match ? match[2].trim() : null
                const extraTags = match && match[3] ? match[3].trim() : null
                const included = extraTags?.replace(/^include(?: h2)?:\s*/i, '').split(',').map((item) => item.trim()).filter(Boolean) || []

                const tierInfo = targetKeyword ? tierMetadata[targetKeyword.toLowerCase()] : null
                const tier = tierInfo?.tier || null
                
                const finalTitle = (tier === 'subheading_group' && tierInfo?.article_title) ? tierInfo.article_title : displayTitle
                const isSubheading = tier === 'subheading_group'
                
                const slugSource = targetKeyword || finalTitle
                const spokeSlug = `/${slugify(slugSource)}/`

                return (
                  <div key={sIdx} className="flex flex-col">
                    <div className="flex flex-wrap sm:flex-nowrap items-start sm:items-center justify-between group py-1 gap-2 sm:gap-4">
                      <div className="flex items-start gap-3 w-full sm:items-center">
                        <span className="text-slate-400 dark:text-slate-500 select-none shrink-0 mt-1 sm:mt-0">├──</span>
                        <div className="mt-1.5 sm:mt-0 shrink-0">
                          <TreeDot tier={tier} />
                        </div>
                        <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-baseline gap-x-3 gap-y-0.5 flex-1 min-w-0">
                          <div className="flex flex-col gap-0.5">
                            <button type="button" onClick={() => {
                              const isTool = displayTitle.toLowerCase().includes('[tool]') || spoke.toLowerCase().includes('[tool]')
                              onWrite(targetKeyword || finalTitle, isTool ? 'tool/app' : 'article', included)
                            }} className="text-left text-slate-700 dark:text-slate-300 group-hover:text-cyan-600 dark:group-hover:text-cyan-400 transition-colors break-words font-medium">
                              {isSubheading ? `"${finalTitle}"` : finalTitle}
                            </button>
                            {extraTags && extraTags.toLowerCase().startsWith('include') && (
                              <span className="text-xs text-amber-600 dark:text-amber-500 font-medium ml-2">
                                ↳ Includes: {extraTags.replace(/^include(?: h2)?:\s*/i, '')}
                              </span>
                            )}
                          </div>
                          <span className="text-[10px] text-emerald-600/80 dark:text-emerald-500/70 font-mono break-all">
                            {spokeSlug}
                          </span>
                        </div>
                      </div>
                      
                      <div className="flex items-center gap-4 ml-6 sm:ml-auto w-full sm:w-auto justify-end">
                        <button 
                          onClick={() => {
                            const isTool = displayTitle.toLowerCase().includes('[tool]') || spoke.toLowerCase().includes('[tool]')
                            const instruction = isTool 
                              ? "INSTRUCTION: This is a Spoke tool/app page supporting a main hub. It MUST be an interactive tool, calculator, or interactive component."
                              : "INSTRUCTION: This is a Spoke article supporting a main hub. Provide enough content to completely satisfy its unique intent, with no fixed word count or padding."
                            onWrite(targetKeyword || finalTitle, instruction, included)
                          }} 
                          className="sm:opacity-0 group-hover:opacity-100 text-[11px] text-cyan-600 hover:text-cyan-500 hover:underline transition-opacity shrink-0"
                        >
                          {(() => {
                            const isTool = displayTitle.toLowerCase().includes('[tool]') || spoke.toLowerCase().includes('[tool]')
                            return isTool ? '[ Make Tool ]' : '[ Write ]'
                          })()}
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
                            <span className="select-none text-slate-400 dark:text-slate-600">↳ Include:</span>
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
      
      {/* Render Sub-Silos Recursively */}
      {hub.sub_silos && hub.sub_silos.length > 0 && (
        <div className="flex flex-col mt-6">
          {hub.sub_silos.map((silo, i) => (
            <TreeHub key={i} hub={silo} onWrite={onWrite} tierMetadata={tierMetadata} isSubSilo={true} />
          ))}
        </div>
      )}
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

export function HubSpokeView({ projectId, search = '', type = '' }: HubSpokeViewProps) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const { data, isLoading } = useQuery({
    queryKey: ['hub-spoke', projectId],
    queryFn: () => api.get<{ clusters: ClusterData | null; tier_metadata?: Record<string, TierMetadataEntry> }>(`/projects/${projectId}/keywords/hub-spoke`),
  })

  const clusterMutation = useMutation({
    mutationFn: () => api.postAI<{ clusters: ClusterData }>(`/projects/${projectId}/keywords/hub-spoke`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hub-spoke', projectId] })
    },
  })

  const handleWrite = (keyword: string, instruction: string, included: string[] = []) => {
    const params = new URLSearchParams({ keyword, project_id: projectId })
    if (included.length) params.set('cluster', included.join('\n'))
    const isTool = shouldBuildTool(keyword)
      || instruction.includes('tool/app')
    navigate(`${isTool ? '/gap-page-prompts' : '/write-blog'}?${params.toString()}`)
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
  const generationError = clusterMutation.error
  const tierMetadata = data?.tier_metadata || {}

  if (!clusters || Object.keys(clusters).length === 0) {
    return (
      <div className="flex flex-col items-center justify-center px-4 py-16 text-center font-sans">
        {generationError && <p role="alert" className="mb-4 text-sm text-rose-600">{generationError.message}</p>}
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

  const filterHub = (hub: NewSchemaHub): NewSchemaHub | null => {
    let hasMatches = false;
    const filteredLayers: Record<string, string[]> = {};
    if (hub.layers) {
      Object.entries(hub.layers).forEach(([layerName, spokes]) => {
        const filteredSpokes = (spokes as string[]).filter(spoke => {
            const match = spoke.match(/(.*?)\s*[([]?Target Keyword:\s*([^)\]]+)[)\]]?(?:\s*\[(.*?)\])?/i)
            const targetKeyword = match ? match[2].trim().toLowerCase() : spoke.trim().toLowerCase()
            
            let pass = true
            if (search) {
              const searchTerms = search.toLowerCase().split(/\s+/)
              if (!searchTerms.every(term => targetKeyword.includes(term))) {
                pass = false
              }
            }
            if (pass && type) {
               const kwInfo = tierMetadata[targetKeyword]
               if (kwInfo && kwInfo.keyword_type !== type) {
                  pass = false
               } else if (!kwInfo) {
                  pass = false
               }
            }
            return pass
        })
        if (filteredSpokes.length > 0) {
           filteredLayers[layerName] = filteredSpokes
           hasMatches = true
        }
      })
    }
    
    const filteredSubSilos: NewSchemaHub[] = [];
    if (hub.sub_silos) {
       hub.sub_silos.forEach(silo => {
          const fs = filterHub(silo)
          if (fs) {
             filteredSubSilos.push(fs)
             hasMatches = true
          }
       })
    }
    
    // Also check if the hub title itself matches
    const hubMatch = hub.hub_title.match(/(.*?)\s*[([]?Target Keyword:\s*([^)\]]+)[)\]]?/i)
    const hubTargetKeyword = hub.target_keyword || (hubMatch ? hubMatch[2].trim() : null)
    let hubPasses = false
    if (hubTargetKeyword && search) {
       const searchTerms = search.toLowerCase().split(/\s+/)
       if (searchTerms.every(term => hubTargetKeyword.toLowerCase().includes(term))) {
          hubPasses = true
       }
    } else if (!search && !type) {
       hubPasses = true
    }
    
    if (hasMatches || hubPasses) {
       return {
          ...hub,
          layers: filteredLayers,
          sub_silos: filteredSubSilos.length > 0 ? filteredSubSilos : undefined
       }
    }
    return null
  }

  let displayClusters = clusters;
  if (isNewSchema && (search || type)) {
      const newHubs = (clusters as NewSchema).hubs.map(filterHub).filter(Boolean) as NewSchemaHub[];
      displayClusters = { ...clusters, hubs: newHubs } as NewSchema;
  }

  return (
    <div className="p-4 md:p-8 bg-slate-50 dark:bg-slate-900/50 min-h-[500px] font-mono rounded-lg border border-slate-200 dark:border-slate-800/60 shadow-inner">
      {generationError && <p role="alert" className="mb-4 text-sm text-rose-600">{generationError.message}</p>}
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
          <Button 
            variant="secondary" 
            size="sm" 
            onClick={() => {
              if (!clusters) return
              
              let text = 'Topical Map\n===========\n\n'
              if (isNewSchema) {
                const renderHubText = (hub: NewSchemaHub, isSubSilo = false) => {
                  let txt = `${isSubSilo ? '  ' : ''}MASTER HUB: ${hub.hub_title}\n`
                  if (hub.layers) {
                    Object.entries(hub.layers).forEach(([layerName, spokes]) => {
                      txt += `\n${isSubSilo ? '    ' : '  '}${layerName}\n`
                      ;(spokes as string[]).forEach((spoke) => {
                        txt += `${isSubSilo ? '    ' : '  '}├── ${spoke}\n`
                      })
                    })
                  }
                  if (hub.sub_silos) {
                    hub.sub_silos.forEach((silo) => {
                      txt += '\n' + renderHubText(silo, true)
                    })
                  }
                  return txt
                }

                ;(clusters as NewSchema).hubs.forEach((hub) => {
                  text += renderHubText(hub)
                  text += '\n------------------------\n\n'
                })
              } else {
                text += JSON.stringify(clusters, null, 2)
              }

              const blob = new Blob([text], { type: 'text/plain' })
              const url = window.URL.createObjectURL(blob)
              const anchor = document.createElement('a')
              anchor.href = url
              anchor.download = `hub-spoke-map-${projectId}.txt`
              document.body.appendChild(anchor)
              anchor.click()
              anchor.remove()
              window.URL.revokeObjectURL(url)
            }}
          >
            <Download className="mr-2 h-3 w-3" />
            Save Map
          </Button>
        </div>
      </div>

      <div className="flex flex-col overflow-x-auto pb-8">
        {isNewSchema ? (
          <div className="flex flex-col gap-4">
            {(displayClusters as NewSchema).hubs.map((hub, i) => (
              <TreeHub key={i} hub={hub} onWrite={handleWrite} tierMetadata={tierMetadata} />
            ))}
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {Object.entries(displayClusters as OldSchema).map(([category, hubMap]) => {
              if (Array.isArray(hubMap)) {
                return <OldTreeHub key={category} hub={category} spokes={hubMap} />
              } else {
                return Object.entries(hubMap as Record<string, string[]>).map(([hub, spokes]) => (
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
