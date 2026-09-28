import { queryOptions } from '@tanstack/react-query'
import { api, type Project, type User } from './api'

// One bounded request per attempt. Do not multiply api.get retries by query retries.
const connectionOptions = {
  retry: false,
  staleTime: 30_000,
  refetchInterval: (query: { state: { error: Error | null } }) => query.state.error ? 15_000 : false as const,
}

export const accountQuery = queryOptions({
  ...connectionOptions,
  queryKey: ['user'],
  queryFn: ({ signal }) => api.fetch<User>('/auth/me', { method: 'GET', timeoutMs: 15_000, signal }),
})

export const projectsQuery = queryOptions({
  ...connectionOptions,
  queryKey: ['projects'],
  queryFn: ({ signal }) => api.fetch<Project[]>('/projects', { method: 'GET', timeoutMs: 15_000, signal }),
})
