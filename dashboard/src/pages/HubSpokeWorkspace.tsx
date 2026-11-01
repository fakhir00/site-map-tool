import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Clock3, Download, FileUp, Loader2, Network, Plus, X } from 'lucide-react'
import { api, type Project } from '../lib/api'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { TopicalAuthorityMap } from '../components/TopicalAuthorityMap'
import { downloadText, grandArchitecturePrompt, pageArchitectureBrief, pageEditor, normalizeSavedMapping, parseFile, type Mapping, type KeywordMetric, type HistorySummary, type HistoryDetail, type ProjectImport, type PageDetail } from '../lib/hubSpoke'

function primaryFromContext(context: string, fallback: string) {
  try { return String(JSON.parse(context).primary_keyword || fallback) } catch { return fallback }
}

export function HubSpokeWorkspace() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const inputRef = useRef<HTMLInputElement>(null)
  const importedKeyRef = useRef('')
  const [keywords, setKeywords] = useState<string[]>([])
  const [keywordText, setKeywordText] = useState('')
  const [primaryKeyword, setPrimaryKeyword] = useState('')
  const [keywordData, setKeywordData] = useState<KeywordMetric[]>([])
  const [cleaned, setCleaned] = useState<string[]>([])
  const [context, setContext] = useState('')
  const [existingUrls, setExistingUrls] = useState('')
  const [mapping, setMapping] = useState<Mapping | null>(null)
  const [mapContext, setMapContext] = useState('')
  const [mapProjectId, setMapProjectId] = useState<string | null>(null)
  const [busy, setBusy] = useState<'build' | 'load' | null>(null)
  const [error, setError] = useState('')
  const [sourceProjectId, setSourceProjectId] = useState<string | null>(null)
  const [activeHistoryId, setActiveHistoryId] = useState<string | null>(null)
  const [dirty, setDirty] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const importProjectId = searchParams.get('project_id') || ''
  const importKeyword = searchParams.get('keyword') || ''
  const { data: history = [], error: historyError } = useQuery({ queryKey: ['hub-spoke-history'], queryFn: () => api.get<HistorySummary[]>('/hub-spoke/history') })
  const { data: projects = [] } = useQuery({ queryKey: ['projects'], queryFn: () => api.get<Project[]>('/projects') })
  const projectImport = useQuery({
    queryKey: ['hub-spoke-project-import', importProjectId, importKeyword],
    queryFn: () => api.get<ProjectImport>(`/hub-spoke/project-import/${importProjectId}?primary_keyword=${encodeURIComponent(importKeyword)}`),
    enabled: Boolean(importProjectId), retry: false,
  })
  const researchSummary = sourceProjectId === projectImport.data?.project_id ? projectImport.data?.research_summary : undefined
  const totalInputKeywords = new Set([...keywords, primaryKeyword.trim().toLowerCase()].filter(Boolean)).size
  const locked = busy !== null || projectImport.isFetching
  const visibleError = error || (projectImport.error instanceof Error ? projectImport.error.message : '')

  useEffect(() => {
    if (busy !== 'build') return
    const started = Date.now()
    const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000)
    return () => window.clearInterval(timer)
  }, [busy])

  useEffect(() => {
    if (!projectImport.data) return
    const key = `${projectImport.data.project_id}:${importKeyword}`
    if (importedKeyRef.current === key) return
    importedKeyRef.current = key
    const data = projectImport.data
    setKeywords(data.keywords); setKeywordText(data.keywords.join('\n')); setKeywordData(data.keyword_data || [])
    setPrimaryKeyword(primaryFromContext(data.context, data.keywords[0] || ''))
    setContext(data.context); setExistingUrls(''); setSourceProjectId(data.project_id); setError(''); setDirty(true)
  }, [importKeyword, projectImport.data])

  const deleteHistoryMutation = useMutation({
    mutationFn: (id: string) => api.delete<null>(`/hub-spoke/history/${id}`),
    onSuccess: (_data, id) => {
      queryClient.setQueryData<HistorySummary[]>(['hub-spoke-history'], (items = []) => items.filter(item => item.id !== id))
      if (activeHistoryId === id) setActiveHistoryId(null)
    },
    onError: err => setError(err instanceof Error ? err.message : 'Could not delete the saved map'),
    onSettled: () => { queryClient.invalidateQueries({ queryKey: ['hub-spoke-history'] }) },
  })
  const detachImport = () => {
    importedKeyRef.current = ''
    setSearchParams({})
    setSourceProjectId(null)
  }
  const loadFile = async (file?: File) => {
    if (!file || locked) return
    if (file.size > 5_000_000) { setError('Use a CSV or TXT file smaller than 5 MB.'); return }
    setBusy('load')
    try {
      const text = await file.text()
      const parsed = parseFile(text)
      if (!parsed.keywords.length) throw new Error('This file contains no readable keywords. Use one keyword per line or a Keyword column.')
      if (parsed.keywords.length > 5000) throw new Error('Use at most 5,000 keywords in one map.')
      detachImport()
      setKeywords(parsed.keywords); setKeywordText(parsed.keywords.join('\n')); setKeywordData(parsed.keywordData)
      setPrimaryKeyword(parsed.keywords[0] || ''); setContext(''); setExistingUrls(''); setDirty(true); setError('')
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not read this file') }
    finally { setBusy(null); if (inputRef.current) inputRef.current.value = '' }
  }
  const build = async () => {
    if (locked) return
    const urls = [...new Set(existingUrls.split(/\r?\n/).map(url => url.trim()).filter(Boolean))]
    if (urls.length > 100 || urls.some(url => { try { return !['http:', 'https:'].includes(new URL(url).protocol) } catch { return true } })) {
      setError('Add up to 100 valid existing page URLs, one per line, starting with https:// or http://.'); return
    }
    setBusy('build'); setError(''); setElapsed(0)
    try {
      const result = await api.postAI<{ keywords: string[]; clusters: Mapping; history_id: string }>('/hub-spoke/build', {
        keywords: keywords.length ? keywords : [primaryKeyword.trim()], keyword_data: keywordData, primary_keyword: primaryKeyword.trim(), existing_urls: urls, context, project_id: sourceProjectId,
      })
      setCleaned(result.keywords); setMapping(normalizeSavedMapping(result.clusters)); setActiveHistoryId(result.history_id)
      setMapContext(context); setMapProjectId(sourceProjectId); setDirty(false)
      queryClient.invalidateQueries({ queryKey: ['hub-spoke-history'] })
    } catch (err) { setError(err instanceof Error ? err.message : 'Map generation failed. Your previous map is still available.') }
    finally { setBusy(null) }
  }
  const loadHistory = async (id: string) => {
    setBusy('load'); setError('')
    try {
      const saved = await api.get<HistoryDetail>(`/hub-spoke/history/${id}`)
      detachImport()
      setKeywords(saved.keywords); setKeywordText(saved.keywords.join('\n')); setKeywordData(saved.clusters?._keyword_metrics || [])
      setPrimaryKeyword(saved.clusters.master_hub?.target_keyword || primaryFromContext(saved.context, saved.keywords[0] || ''))
      setCleaned(saved.cleaned_keywords); setContext(saved.context); setExistingUrls(''); setMapContext(saved.context); setMapping(normalizeSavedMapping(saved.clusters))
      setSourceProjectId(saved.project_id)
      setMapProjectId(saved.project_id); setActiveHistoryId(saved.id); setDirty(false)
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not load the saved map') }
    finally { setBusy(null) }
  }
  const reset = () => {
    detachImport(); setKeywords([]); setKeywordText(''); setKeywordData([]); setPrimaryKeyword(''); setContext(''); setMapping(null)
    setMapContext(''); setMapProjectId(null); setExistingUrls(''); setCleaned([]); setActiveHistoryId(null); setError(''); setDirty(false)
  }
  const openPage = (page: PageDetail) => {
    const params = new URLSearchParams({ keyword: page.target_keyword || '' })
    if (mapProjectId) params.set('project_id', mapProjectId)
    if (page.targeted_keywords?.length) params.set('cluster', page.targeted_keywords.join('\n'))
    navigate(`${pageEditor(page) === 'page' ? '/gap-page-prompts' : '/write-blog'}?${params.toString()}`, { state: { architectureBrief: mapping ? pageArchitectureBrief(page, mapping) : '' } })
  }
  const inputClass = 'mt-2 w-full rounded-lg border border-slate-300 bg-white p-3 text-sm text-slate-900 outline-none focus:ring-2 focus:ring-site-sky disabled:opacity-60 dark:border-line dark:bg-raised dark:text-text'

  return <div className="space-y-6">
    <header className="flex flex-wrap items-start justify-between gap-4"><div><p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-sky-700 dark:text-site-sky">Hub & spoke workspace</p><h2 className="font-display text-3xl font-bold tracking-tight text-slate-950 dark:text-text">Build your topical authority map</h2><p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-500 dark:text-muted">Turn keyword research into a connected content plan. Define the main topic, organize distinct reader tasks, and see what to create, improve and link.</p></div><Button variant="secondary" disabled={locked} onClick={reset}><Plus className="h-4 w-4" />Start fresh</Button></header>
    {historyError && <p role="alert" className="text-sm text-amber-700 dark:text-signal-amber">Saved maps could not be loaded. Refresh to try again.</p>}
    {history.length > 0 && <details className="rounded-xl border border-slate-200 bg-white p-4 dark:border-line dark:bg-panel"><summary className="cursor-pointer text-sm font-semibold text-slate-900 dark:text-text">Saved maps <span className="ml-2 font-mono text-slate-400 dark:text-muted">{history.length}</span></summary><div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-3">{history.map(item => <div key={item.id} className={`relative rounded-lg border ${activeHistoryId === item.id ? 'border-sky-500 bg-sky-50 dark:border-site-sky dark:bg-site-sky/10' : 'border-slate-200 dark:border-line'}`}><button type="button" disabled={locked || deleteHistoryMutation.isPending} onClick={() => loadHistory(item.id)} className="block w-full p-3 pr-10 text-left disabled:opacity-50"><span className="block truncate text-sm font-semibold text-slate-900 dark:text-text">{item.title}</span><span className="mt-1 flex items-center gap-2 text-xs text-slate-500 dark:text-muted"><Clock3 className="h-3 w-3" />{new Date(item.created_at).toLocaleDateString()} · {item.keyword_count} keywords</span></button><button type="button" aria-label={`Permanently delete ${item.title}`} disabled={locked || deleteHistoryMutation.isPending} onClick={() => { if (window.confirm(`Permanently delete “${item.title}”? This cannot be undone.`)) deleteHistoryMutation.mutate(item.id) }} className="absolute right-2 top-2 rounded p-1 text-slate-400 hover:text-rose-600 dark:text-muted dark:hover:text-signal-red"><X className="h-4 w-4" /></button></div>)}</div></details>}
    <Card className="p-5 sm:p-6">
      <div className="mb-5 flex items-center gap-3"><span className="flex h-8 w-8 items-center justify-center rounded-full bg-sky-100 font-mono text-sm font-bold text-sky-800 dark:bg-site-sky/15 dark:text-site-sky">1</span><div><h3 className="font-display font-bold text-slate-950 dark:text-text">Define your starting point</h3><p className="text-xs text-slate-500 dark:text-muted">Use a saved scan, upload research, or paste your keywords.</p></div></div>
      <fieldset disabled={locked} className="space-y-5 disabled:opacity-70">
        <div className="grid gap-5 lg:grid-cols-2">
          <div className="space-y-4">
            <label className="block text-sm font-medium">Import from Gap Scan<select aria-label="Import from Gap Scan" value={importProjectId} onChange={event => { importedKeyRef.current = ''; if (event.target.value) setSearchParams({ project_id: event.target.value }); else detachImport() }} className={inputClass}><option value="">Choose a scan…</option>{projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label>
            <div className="flex items-center gap-3"><input ref={inputRef} className="hidden" type="file" accept=".csv,.txt,text/csv,text/plain" onChange={event => loadFile(event.target.files?.[0])} /><Button variant="secondary" onClick={() => inputRef.current?.click()}><FileUp className="h-4 w-4" />Upload CSV / TXT</Button><span className="text-xs text-slate-500">Up to 5 MB · 300 keywords per map</span></div>
            <label className="block text-sm font-medium">Keyword research<textarea aria-label="Keyword research" className={`${inputClass} min-h-44 font-mono text-xs`} value={keywordText} onChange={event => {
              const text = event.target.value; const parsed = parseFile(text)
              const metrics = new Map(keywordData.map(item => [item.phrase, item]))
              setKeywordText(text); setKeywords(parsed.keywords); setKeywordData(parsed.keywordData.map(item => metrics.get(item.phrase) || item))
              if (!primaryKeyword) setPrimaryKeyword(parsed.keywords[0] || '')
              setDirty(true)
            }} placeholder={'One keyword per line, or paste a CSV with metrics.\nlunar age calculator\nhow to calculate lunar age\nlunar age vs western age'} /></label>
            <p className="text-xs text-slate-500">{keywords.length.toLocaleString()} keywords{sourceProjectId ? ' · Linked to a Gap Scan project; crawled pages will be checked for reuse.' : ' · Add existing URLs alongside your context to plan improvements.'}</p>
          </div>
          <div className="space-y-4">
            <label className="block text-sm font-medium">Main topic / homepage keyword<input aria-label="Main topic" list="map-keyword-options" maxLength={300} className={inputClass} value={primaryKeyword} onChange={event => { setPrimaryKeyword(event.target.value); setDirty(true) }} placeholder="e.g. lunar age calculator" /><datalist id="map-keyword-options">{keywords.slice(0, 300).map(keyword => <option key={keyword} value={keyword} />)}</datalist></label>
            <label className="block text-sm font-medium">Website and audience context<textarea aria-label="Website and audience context" maxLength={12000} className={`${inputClass} min-h-32`} value={context} onChange={event => { setContext(event.target.value); setDirty(true) }} placeholder="Your site URL, audience, what you offer, existing page URLs, and topics to exclude. Be specific about what your site can help people do." /></label>
            <label className="block text-sm font-medium">Existing page URLs <span className="font-normal text-slate-400">(optional)</span><textarea aria-label="Existing page URLs" className={`${inputClass} min-h-20 font-mono text-xs`} value={existingUrls} onChange={event => { setExistingUrls(event.target.value); setDirty(true) }} placeholder={'https://example.com/\nhttps://example.com/existing-guide/'} /><span className="mt-1 block text-xs font-normal text-slate-500">Add your existing pages so we can avoid suggesting them again. Linked scans include known site pages automatically. Use one URL per line.</span></label>
            <p className="text-sm leading-relaxed text-slate-500">There is no fixed number of pages. Add a page only when it answers a different question or helps the reader do a different task.</p>
          </div>
        </div>
      </fieldset>
      {researchSummary && <div role="status" className="mt-4 rounded-lg border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900 dark:border-site-sky/30 dark:bg-site-sky/10 dark:text-site-sky">
        <p className="font-mono">{researchSummary.new_gaps} new gaps · {researchSummary.planning_keywords} keywords imported for planning</p>
        <p className="mt-1 text-xs">The planning list includes useful research and existing topics. A low gap count does not prevent building your map.</p>
        {researchSummary.pending_review > 0 && <p className="mt-1 text-xs">{researchSummary.pending_review} research {researchSummary.pending_review === 1 ? 'candidate still needs' : 'candidates still need'} review. The planner checks them before assigning them to pages.</p>}
        {researchSummary.not_included > 0 && <p className="mt-1 text-xs">This map uses a balanced selection of 300 keywords. {researchSummary.not_included} additional keywords remain in your scan research.</p>}
      </div>}
      {projectImport.isFetching && <p role="status" className="mt-4 text-sm text-slate-500">Loading keywords and site context…</p>}
      <div className="mt-5 flex flex-wrap items-center justify-between gap-4 border-t border-slate-200 pt-5 dark:border-line"><p className="max-w-lg text-xs leading-relaxed text-slate-500 dark:text-muted">Start with your main topic, even if your scan found no new gaps. The planner uses existing pages and research, checks overlap, and explores missing topics.</p><Button disabled={locked || totalInputKeywords > 300 || !primaryKeyword.trim() || context.length > 12000} onClick={build}>{busy === 'build' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Network className="h-4 w-4" />}{busy === 'build' ? 'Building your map…' : 'Build topical map'}</Button></div>
      {totalInputKeywords > 300 && <p role="alert" className="mt-3 text-sm text-rose-700 dark:text-signal-red">Use at most 300 distinct keywords per map, including the main topic. Narrow the list to one focused subject.</p>}
      {busy === 'build' && <div role="status" className="mt-4 rounded-lg border border-sky-200 bg-sky-50 p-4 text-sm text-sky-900 dark:border-site-sky/30 dark:bg-site-sky/10 dark:text-site-sky"><p className="font-semibold">Planning your topic coverage · <span className="font-mono">{elapsed}s</span></p><p className="mt-1 text-xs">Discovery, page planning and intent review can take a few minutes. Keep this tab open; successful maps are saved automatically.</p></div>}
      {visibleError && <p role="alert" className="mt-4 rounded-lg bg-rose-50 p-3 text-sm text-rose-700 dark:bg-signal-red/10 dark:text-signal-red">{visibleError}</p>}
    </Card>
    {mapping && <>
      {dirty && <p role="status" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-signal-amber/30 dark:bg-signal-amber/10 dark:text-signal-amber">Inputs have changed. The map below is your previous result; build again to apply these changes.</p>}
      <div className="flex flex-wrap items-center justify-between gap-3"><p className="text-xs text-slate-500 dark:text-muted">{activeHistoryId ? 'Saved in your map history' : 'Map preview'} · <span className="font-mono">{cleaned.length}</span> keywords assigned</p><div className="flex flex-wrap gap-2"><Button variant="secondary" onClick={() => downloadText('usable-keywords.txt', cleaned.join('\n'))}><Download className="h-4 w-4" />Keywords</Button><Button variant="secondary" onClick={() => downloadText('grand-website-architecture-prompt.md', grandArchitecturePrompt(mapping, mapContext))}><Download className="h-4 w-4" />Architecture brief</Button></div></div>
      <TopicalAuthorityMap key={activeHistoryId || 'preview'} mapping={mapping} onOpen={openPage} />
    </>}
    {!mapping && <div className="rounded-2xl border border-dashed border-slate-300 p-8 text-center dark:border-line"><Network className="mx-auto h-9 w-9 text-slate-300 dark:text-line" /><h3 className="mt-4 font-display font-semibold text-slate-900 dark:text-text">A connected plan, from topic to page</h3><p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-slate-500 dark:text-muted">Your map will show the main hub, supporting topic groups, individual page briefs and internal links. Start with the topic you want your site to be known for.</p></div>}
  </div>
}
