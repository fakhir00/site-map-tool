import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Network, RefreshCw, BookOpen, Settings, DollarSign, FilePenLine, Loader2 } from 'lucide-react'
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

type OldSchema = Record<string, any>
type ClusterData = NewSchema | OldSchema

function LayerIcon({ name }: { name: string }) {
  if (name.includes('Zero') || name.includes('Quick-Wins')) return <DollarSign className="h-4 w-4 text-amber-500" />
  if (name.includes('Blog') || name.includes('Informational')) return <BookOpen className="h-4 w-4 text-indigo-500" />
  if (name.includes('Tool') || name.includes('Transactional')) return <Settings className="h-4 w-4 text-emerald-500" />
  if (name.includes('Foundation') || name.includes('Informational')) return <BookOpen className="h-4 w-4 text-indigo-500" />
  if (name.includes('Action') || name.includes('How-To')) return <Settings className="h-4 w-4 text-emerald-500" />
  if (name.includes('Money') || name.includes('Commercial')) return <DollarSign className="h-4 w-4 text-amber-500" />
  return <Network className="h-4 w-4 text-slate-400" />
}

function NewHubCard({ hub, onWrite, isWriting }: { hub: NewSchemaHub, onWrite: (keyword: string, instruction: string) => void, isWriting: boolean }) {
  const layerEntries = Object.entries(hub.layers || {})

  return (
    <div className="flex flex-col overflow-hidden rounded-xl border border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900/50 shadow-sm">
      <div className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 px-5 py-4">
        <div className="flex justify-between items-start">
          <div>
            <h5 className="text-lg font-bold text-slate-900 dark:text-slate-50">{hub.hub_title}</h5>
            <div className="mt-1 text-xs font-semibold text-cyan-600 dark:text-cyan-400 uppercase tracking-wider">SEO Hub / Pillar Page</div>
          </div>
          <Button 
            size="sm" 
            disabled={isWriting}
            onClick={() => onWrite(hub.hub_title, "INSTRUCTION: This is a Hub/Pillar page. It MUST be an extensive, comprehensive guide of 3000+ words. Cover the topic thoroughly.")}
          >
            {isWriting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FilePenLine className="mr-2 h-4 w-4" />}
            Write Hub
          </Button>
        </div>
      </div>
      <div className="flex-1 p-5">
        {layerEntries.length === 0 ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">No spokes generated for this hub.</p>
        ) : (
          <div className="flex flex-col gap-4">
            {layerEntries.map(([layerName, spokes], idx) => (
              <div key={idx} className="overflow-hidden rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 shadow-sm">
                <div className="flex items-center gap-2 border-b border-slate-100 bg-slate-50/80 dark:border-slate-800/50 dark:bg-slate-800/50 px-4 py-2.5">
                  <LayerIcon name={layerName} />
                  <h6 className="font-semibold text-slate-800 dark:text-slate-200 text-sm">{layerName}</h6>
                </div>
                <div className="p-3">
                  {(!spokes || spokes.length === 0) ? (
                    <p className="text-xs text-slate-400 dark:text-slate-500 italic px-2">No keywords in this layer.</p>
                  ) : (
                    <ul className="flex flex-col gap-1.5">
                      {spokes.map((spoke, sIdx) => {
                        const match = spoke.match(/(.*?)\s*\(Target Keyword:\s*(.*?)\)(?:\s*\[(Tool|Blog)\])?/i)
                        const displayTitle = match ? match[1].trim() : spoke.replace(/\[(Tool|Blog)\]/i, '').trim()
                        const targetKeyword = match ? match[2].trim() : null
                        const intentTag = match ? match[3] : (spoke.match(/\[(Tool|Blog)\]/i)?.[1] || null)

                        const isToolSpoke = intentTag 
                          ? intentTag.toLowerCase() === 'tool' 
                          : (layerName.toLowerCase().includes('tool') || layerName.toLowerCase().includes('transactional'))

                        return (
                          <li key={sIdx} className="flex items-center justify-between px-2 py-1.5 rounded-md hover:bg-slate-50 dark:hover:bg-slate-800/50">
                            <div className="flex flex-col items-start pr-4">
                              <span className="text-sm font-medium text-slate-700 dark:text-slate-300">{displayTitle}</span>
                              {targetKeyword && (
                                <span className="mt-0.5 inline-flex items-center rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                                  Keyword: {targetKeyword}
                                </span>
                              )}
                            </div>
                            <Button 
                              size="sm" 
                              variant="secondary" 
                              disabled={isWriting}
                              className="shrink-0"
                              onClick={() => onWrite(targetKeyword || displayTitle, isToolSpoke ? "INSTRUCTION: This is a Tool spoke. Write functional requirements and pseudo-code." : "INSTRUCTION: This is a Spoke article supporting a main hub. It MUST be a detailed, focused article of 1500+ words.")}
                            >
                              {isToolSpoke ? (
                                <>
                                  <Settings className="mr-2 h-4 w-4" />
                                  Build tool
                                </>
                              ) : (
                                <>
                                  <FilePenLine className="mr-2 h-4 w-4" />
                                  Write Blog
                                </>
                              )}
                            </Button>
                          </li>
                        )
                      })}
                    </ul>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function OldHubCard({ hub, spokes }: { hub: string; spokes: string[] }) {
  return (
    <div className="flex flex-col overflow-hidden rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 shadow-sm">
      <div className="border-b border-slate-100 bg-slate-50 dark:border-slate-800/50 dark:bg-slate-900/50 px-4 py-3">
        <h5 className="font-bold text-slate-900 dark:text-slate-50">{hub}</h5>
        <div className="mt-1 text-xs font-medium text-slate-500 dark:text-slate-400">Hub / Pillar Page</div>
      </div>
      <div className="flex-1 p-4">
        <ul className="flex flex-col gap-2">
          {spokes.map((spoke, idx) => (
            <li key={idx} className="flex items-start text-sm text-slate-700 dark:text-slate-300">
              <span className="mr-2 text-slate-300 dark:text-slate-600">↳</span>
              {spoke}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

export function HubSpokeView({ projectId }: HubSpokeViewProps) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const { data, isLoading } = useQuery({
    queryKey: ['hub-spoke', projectId],
    queryFn: () => api.get<{ clusters: ClusterData | null }>(`/projects/${projectId}/keywords/hub-spoke`),
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
      <div className="flex flex-col items-center justify-center py-16 text-slate-500 dark:text-slate-400">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-200 border-t-cyan-600 dark:border-slate-800 dark:border-t-cyan-400" />
        <p className="mt-4 text-sm font-medium">Loading clusters...</p>
      </div>
    )
  }

  const clusters = data?.clusters

  if (!clusters || Object.keys(clusters).length === 0) {
    return (
      <div className="flex flex-col items-center justify-center px-4 py-16 text-center">
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
    <div className="p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h4 className="text-lg font-bold text-slate-900 dark:text-slate-50">Content Architecture</h4>
          <p className="text-sm text-slate-500 dark:text-slate-400">Your keywords grouped by semantic categories</p>
        </div>
        <Button 
          variant="secondary" 
          size="sm" 
          onClick={() => clusterMutation.mutate()}
          disabled={clusterMutation.isPending}
        >
          <RefreshCw className={`mr-2 h-4 w-4 ${clusterMutation.isPending ? 'animate-spin' : ''}`} />
          {clusterMutation.isPending ? 'Re-generating...' : 'Re-generate'}
        </Button>
      </div>

      {isNewSchema ? (
        <div className="grid gap-6 md:grid-cols-2">
          {(clusters as NewSchema).hubs.map((hub, i) => (
            <NewHubCard key={i} hub={hub} onWrite={handleWrite} isWriting={manualMutation.isPending} />
          ))}
        </div>
      ) : (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {Object.entries(clusters).map(([category, hubMap]) => {
            if (Array.isArray(hubMap)) {
              return <OldHubCard key={category} hub={category} spokes={hubMap} />
            } else {
              return Object.entries(hubMap).map(([hub, spokes]) => (
                <OldHubCard key={`${category}-${hub}`} hub={hub} spokes={spokes as string[]} />
              ))
            }
          })}
        </div>
      )}
    </div>
  )
}
