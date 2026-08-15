import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Network, RefreshCw } from 'lucide-react'
import { api } from '../lib/api'
import { Button } from './ui/Button'

interface HubSpokeViewProps {
  projectId: string
}

export function HubSpokeView({ projectId }: HubSpokeViewProps) {
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['hub-spoke', projectId],
    queryFn: () => api.get<{ clusters: Record<string, string[]> | null }>(`/projects/${projectId}/keywords/hub-spoke`),
  })

  const clusterMutation = useMutation({
    mutationFn: () => api.post<{ clusters: Record<string, string[]> }>(`/projects/${projectId}/keywords/hub-spoke`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hub-spoke', projectId] })
    },
  })

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-slate-500">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-200 border-t-cyan-600" />
        <p className="mt-4 text-sm font-medium">Loading clusters...</p>
      </div>
    )
  }

  const clusters = data?.clusters

  if (!clusters || Object.keys(clusters).length === 0) {
    return (
      <div className="flex flex-col items-center justify-center px-4 py-16 text-center">
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-slate-100">
          <Network className="h-6 w-6 text-slate-400" />
        </div>
        <h3 className="mb-1 text-lg font-bold text-slate-950">No Hubs & Spokes Generated</h3>
        <p className="mb-6 max-w-sm text-sm text-slate-500">
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

  return (
    <div className="p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h4 className="text-lg font-bold text-slate-900">Content Architecture</h4>
          <p className="text-sm text-slate-500">Your keywords grouped by pillar topics</p>
        </div>
        <Button 
          variant="secondary" 
          size="sm" 
          onClick={() => clusterMutation.mutate()}
          disabled={clusterMutation.isPending}
        >
          <RefreshCw className={`mr-2 h-4 w-4 ${clusterMutation.isPending ? 'animate-spin' : ''}`} />
          Re-Cluster
        </Button>
      </div>

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {Object.entries(clusters).map(([hub, spokes]) => (
          <div key={hub} className="flex flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-100 bg-slate-50 px-4 py-3">
              <h5 className="font-bold text-slate-900">{hub}</h5>
              <div className="mt-1 text-xs font-medium text-slate-500">Hub / Pillar Page</div>
            </div>
            <div className="flex-1 p-4">
              <ul className="flex flex-col gap-2">
                {spokes.map((spoke, idx) => (
                  <li key={idx} className="flex items-start text-sm text-slate-700">
                    <span className="mr-2 text-slate-300">↳</span>
                    {spoke}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
