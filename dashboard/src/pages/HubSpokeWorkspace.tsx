import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Clock3, Download, FileText, FileUp, Layers3, Loader2, Network, Sparkles, Wrench, X } from 'lucide-react'
import { api } from '../lib/api'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'

type LayerMap = Record<string, string[]>
type Silo = { hub_title: string; target_keyword: string; h2_keywords?: string[]; layers: LayerMap }
type Hub = Silo & { sub_silos?: Silo[] }
type SectionDetail = { h2_heading: string; section_definition?: string; targeted_keywords_placed_here?: string[] }
type FaqDetail = { question: string; targeted_keywords_placed_here?: string[] }
type KeywordMetric = { phrase: string; keyword_type?: string; search_volume?: number | null; difficulty?: number | null; frequency?: number }
type PageDetail = { article_title?: string; target_keyword?: string; slug?: string; page_type?: string; ranking_role?: string; search_volume?: number | null; difficulty?: number | null; word_count_suggestion?: number; content_brief?: string; targeted_keywords?: string[]; tool_functions?: string[]; writing_instructions?: string; h2_sections?: SectionDetail[]; faq_schema_questions?: FaqDetail[]; entity_terms?: string[]; internal_links?: string[]; tool_economics?: { qualifies: boolean; reason: string; minimum_volume: number; search_volume?: number | null; difficulty?: number | null } }
type SpokeDetail = PageDetail & { article_title: string; target_keyword: string; spoke_category?: string }
type DeduplicationCheck = { unique_target_keywords?: string; unique_titles?: string; unique_slugs?: string; semantic_intents?: string; duplicates_removed?: number }
type KeywordDecision = { keyword: string; disposition: 'page_target' | 'supporting' | 'discard'; assigned_to?: string | null; placement?: string | null; reason: string }
type Mapping = { hubs: Hub[]; site_domain?: string; _planning_thought?: string; _deduplication_check?: DeduplicationCheck; _keyword_metrics?: KeywordMetric[]; master_hub?: PageDetail; spokes?: SpokeDetail[]; interlinking_strategy?: string; filtered_irrelevant_keywords?: string[]; discarded_keywords?: { keyword: string; reason: string }[]; keyword_assignments?: KeywordDecision[]; deferred_spoke_keywords?: string[]; writing_standards?: string[] }
type HistorySummary = { id: string; project_id: string | null; title: string; keyword_count: number; created_at: string }
type HistoryDetail = { id: string; project_id: string | null; title: string; context: string; keywords: string[]; cleaned_keywords: string[]; clusters: Mapping; created_at: string }
type ProjectImport = { project_id: string; project_name: string; keywords: string[]; keyword_data?: KeywordMetric[]; context: string }

const toolIntent = /\b(tool|software|calculator|generator|maker|builder|creator|checker|converter|app)\b/i
const informationalIntent = /^(how|what|why|when|where|can|does)\b|\b(guide|tutorial|examples|symbols|definition|meaning|tips|troubleshooting|review|comparison|alternatives|vs|terms(?: and conditions)?|privacy(?: policy)?|disclaimer|legal|about us|contact us|cookie policy|refund policy|editorial policy|accessibility|support|faq)\b/i
const shouldBuildTool = (keyword: string) => toolIntent.test(keyword) && !informationalIntent.test(keyword)
const slugify = (value: string) => value.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
const pageSlug = (keyword: string, supplied?: string) => supplied || `/${slugify(keyword)}/`

const parseSpoke = (spoke: string) => {
  const target = spoke.match(/\(Target Keyword:\s*(.*?)\)/i)?.[1]?.trim() || spoke.trim()
  const title = spoke.split(/\(Target Keyword:/i)[0].replace('[Tool]', '').trim() || target
  const includedText = spoke.match(/\[Include(?: H2)?:\s*(.*?)\]/i)?.[1] || ''
  return { title, target, included: includedText.split(',').map((item) => item.trim()).filter(Boolean) }
}

const parseCsvRow = (line: string) => {
  const cells: string[] = []
  let value = ''
  let quoted = false
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index]
    if (char === '"' && quoted && line[index + 1] === '"') { value += '"'; index += 1 }
    else if (char === '"') quoted = !quoted
    else if (char === ',' && !quoted) { cells.push(value.trim()); value = '' }
    else value += char
  }
  cells.push(value.trim())
  return cells
}

const parseFile = (text: string) => {
  const rows = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).map(parseCsvRow)
  if (!rows.length) return { keywords: [], keywordData: [] }
  const header = rows[0].map((cell) => cell.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim())
  const keywordIndex = header.findIndex((cell) => cell === 'keyword' || cell === 'keyword gap' || cell === 'phrase')
  const volumeIndex = header.findIndex((cell) => cell === 'search volume' || cell === 'volume')
  const difficultyIndex = header.findIndex((cell) => cell === 'difficulty' || cell === 'keyword difficulty' || cell === 'kd')
  const typeIndex = header.findIndex((cell) => cell === 'type' || cell === 'keyword type')
  const hasHeader = keywordIndex >= 0
  const dataRows = hasHeader ? rows.slice(1) : rows
  const seen = new Set<string>()
  const keywordData = dataRows.flatMap((row) => {
    const phrase = (row[hasHeader ? keywordIndex : 0] || '').trim().toLowerCase()
    if (!phrase || seen.has(phrase)) return []
    seen.add(phrase)
    const volume = volumeIndex >= 0 && row[volumeIndex] !== '' ? Number(row[volumeIndex]) : null
    const difficulty = difficultyIndex >= 0 && row[difficultyIndex] !== '' ? Number(row[difficultyIndex]) : null
    return [{
      phrase,
      keyword_type: typeIndex >= 0 ? row[typeIndex] || 'long-tail' : 'long-tail',
      search_volume: Number.isFinite(volume) ? volume : null,
      difficulty: Number.isFinite(difficulty) ? difficulty : null,
    }]
  })
  return { keywords: keywordData.map((item) => item.phrase), keywordData }
}

const downloadText = (name: string, content: string) => {
  const url = URL.createObjectURL(new Blob([content], { type: 'text/plain;charset=utf-8' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = name
  anchor.click()
  URL.revokeObjectURL(url)
}

const grandArchitecturePrompt = (mapping: Mapping, context: string) => {
  const lines = ['# GRAND WEBSITE ARCHITECTURE BUILD PROMPT', '', 'Build the complete website architecture below. Follow every page specification and preserve the assigned keyword placements.', '']
  if (context.trim()) lines.push('## Website context', context.trim(), '')
  if (mapping._deduplication_check) lines.push('## Mechanical SEO validation', `- Duplicate targets, titles, slugs, and semantic intents: checked`, `- Cannibalizing pages removed: ${mapping._deduplication_check.duplicates_removed || 0}`, '')
  lines.push('## Global writing standards')
  ;(mapping.writing_standards || []).forEach((rule) => lines.push(`- ${rule}`))
  lines.push('', '## Required deliverables', '- Build every article and interactive tool in this plan as a production-ready page.', '- For each article, provide the title, meta title, meta description, H1, complete body copy, FAQ schema, and internal links.', '- For each tool, provide the working interface and logic, helpful explanatory copy, accessibility labels, validation, result states, and requested export actions.', '', '## Execution rules', '- Build exactly the pages specified below.', '- Use each target keyword for only its assigned URL and keep every slug exactly as written.', '- Treat the suggested word count as a useful depth target; satisfy intent without padding.', '- Use H2 keywords only in their assigned substantive sections, FAQ keywords only in the FAQ block and FAQ schema, and entity terms naturally in the copy.', '- Never turn an entity or FAQ variation into an extra indexable page.', '- Implement every listed tool function on pages marked as tool.', '- Add the specified internal links and keep anchor text natural and descriptive.', '')

  const addPage = (label: string, page: PageDetail) => {
    const target = page.target_keyword || ''
    const heading = label === 'MASTER HUB' ? `MASTER HUB: ${mapping.site_domain || page.article_title || target}` : `${label}: ${page.article_title || target}`
    lines.push(`## ${heading}`, `- Ranking role: ${page.ranking_role || (label === 'MASTER HUB' ? 'master_hub' : 'supporting_spoke')}`, `- Page type: ${page.page_type || (shouldBuildTool(target) ? 'tool' : 'article')}`, `- ${label === 'MASTER HUB' ? 'Primary keyword' : 'Target keyword'}: ${target}`, `- Slug: ${pageSlug(target, page.slug)}`, `- Search volume: ${page.search_volume ?? 'unknown'}`, `- Keyword difficulty: ${page.difficulty ?? 'unknown'}`, `- Suggested word count: ${page.word_count_suggestion || 2000}`, `- Content brief: ${page.content_brief || 'Fully satisfy the target search intent for the website audience.'}`)
    if (page.targeted_keywords?.length) lines.push(`- Additional hub keywords: ${page.targeted_keywords.join(', ')}`)
    if (page.tool_functions?.length) { lines.push('- Required tool functions:'); page.tool_functions.forEach((item) => lines.push(`  - ${item}`)) }
    if (page.h2_sections?.length) { lines.push('- H2 plan:'); page.h2_sections.forEach((section) => lines.push(`  - ${section.h2_heading}: ${section.section_definition || 'Cover this section directly.'}${section.targeted_keywords_placed_here?.length ? ` Keywords: ${section.targeted_keywords_placed_here.join(', ')}` : ''}`)) }
    if (page.faq_schema_questions?.length) { lines.push('- FAQ schema:'); page.faq_schema_questions.forEach((faq) => lines.push(`  - ${faq.question}${faq.targeted_keywords_placed_here?.length ? ` Keywords: ${faq.targeted_keywords_placed_here.join(', ')}` : ''}`)) }
    if (page.entity_terms?.length) lines.push(`- Entities to use naturally: ${page.entity_terms.join(', ')}`)
    if (page.internal_links?.length) lines.push(`- Required internal links to these target pages: ${page.internal_links.join(', ')}`)
    if (page.writing_instructions) lines.push(`- Writing instructions: ${page.writing_instructions}`)
    lines.push('')
  }

  if (mapping.master_hub) addPage('MASTER HUB', mapping.master_hub)
  ;(mapping.spokes || []).forEach((spoke, index) => addPage(`SPOKE ${index + 1} — ${spoke.spoke_category || 'Strategic article'}`, spoke))
  lines.push('## Interlinking strategy', mapping.interlinking_strategy || 'Every spoke links to the Master Hub and to the most relevant next-step spoke.', '')
  if (mapping.filtered_irrelevant_keywords?.length) lines.push('## Do not target these filtered keywords', ...mapping.filtered_irrelevant_keywords.map((keyword) => `- ${keyword}`), '')
  lines.push('Begin by creating the Master Hub, then build each spoke in order. Return production-ready pages and tools that follow this architecture.')
  return lines.join('\n')
}

export function HubSpokeWorkspace() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [searchParams] = useSearchParams()
  const inputRef = useRef<HTMLInputElement>(null)
  const importedKeyRef = useRef('')
  const [keywords, setKeywords] = useState<string[]>([])
  const [keywordData, setKeywordData] = useState<KeywordMetric[]>([])
  const [cleaned, setCleaned] = useState<string[]>([])
  const [contextOpen, setContextOpen] = useState(false)
  const [context, setContext] = useState('')
  const [mapping, setMapping] = useState<Mapping | null>(null)
  const [busy, setBusy] = useState<'build' | 'load' | null>(null)
  const [error, setError] = useState('')
  const [sourceProjectId, setSourceProjectId] = useState<string | null>(null)
  const [activeHistoryId, setActiveHistoryId] = useState<string | null>(null)
  const importProjectId = searchParams.get('project_id') || ''
  const importKeyword = searchParams.get('keyword') || ''

  const { data: history = [] } = useQuery({
    queryKey: ['hub-spoke-history'],
    queryFn: () => api.get<HistorySummary[]>('/hub-spoke/history'),
  })

  const deleteHistoryMutation = useMutation({
    mutationFn: (id: string) => api.delete<null>(`/hub-spoke/history/${id}`),
    onSuccess: (_data, id) => {
      queryClient.setQueryData<HistorySummary[]>(['hub-spoke-history'], (items = []) =>
        items.filter((item) => item.id !== id),
      )
      if (activeHistoryId === id) {
        setActiveHistoryId(null)
      }
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : 'Could not delete the saved architecture')
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['hub-spoke-history'] })
    },
  })

  const deleteHistory = (item: HistorySummary) => {
    if (!window.confirm(`Permanently delete “${item.title}”? This cannot be undone.`)) return
    setError('')
    deleteHistoryMutation.mutate(item.id)
  }

  const projectImport = useQuery({
    queryKey: ['hub-spoke-project-import', importProjectId, importKeyword],
    queryFn: () => api.get<ProjectImport>(`/hub-spoke/project-import/${importProjectId}?primary_keyword=${encodeURIComponent(importKeyword)}`),
    enabled: Boolean(importProjectId),
    retry: false,
  })
  const importError = projectImport.error instanceof Error
    ? projectImport.error.message
    : projectImport.error
      ? 'Could not import this Gap Hunter scan'
      : ''
  const visibleError = error || importError

  useEffect(() => {
    if (!projectImport.data) return
    const importKey = `${projectImport.data.project_id}:${importKeyword}`
    if (importedKeyRef.current === importKey) return
    importedKeyRef.current = importKey
    setKeywords(projectImport.data.keywords)
    setKeywordData(projectImport.data.keyword_data || [])
    setCleaned([])
    setContext(projectImport.data.context)
    setContextOpen(true)
    setMapping(null)
    setSourceProjectId(projectImport.data.project_id)
    setActiveHistoryId(null)
    setError('')
  }, [importKeyword, projectImport.data])

  const loadFile = async (file?: File) => {
    if (!file) return
    if (file.size > 5_000_000) {
      setError('Use a CSV or TXT file smaller than 5 MB.')
      return
    }
    const parsed = parseFile(await file.text())
    setKeywords(parsed.keywords)
    setKeywordData(parsed.keywordData)
    setCleaned([])
    setMapping(null)
    setSourceProjectId(null)
    setActiveHistoryId(null)
    setError('')
  }

  const build = async () => {
    setBusy('build'); setError('')
    try {
      const result = await api.postAI<{ keywords: string[]; clusters: Mapping; history_id: string }>('/hub-spoke/build', {
        keywords,
        keyword_data: keywordData,
        context,
        project_id: sourceProjectId,
      })
      setCleaned(result.keywords)
      setMapping(result.clusters)
      setActiveHistoryId(result.history_id)
      queryClient.invalidateQueries({ queryKey: ['hub-spoke-history'] })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Hub-spoke generation failed')
    } finally { setBusy(null) }
  }

  const loadHistory = async (id: string) => {
    setBusy('load'); setError('')
    importedKeyRef.current = `${importProjectId}:${importKeyword}`
    try {
      const saved = await api.get<HistoryDetail>(`/hub-spoke/history/${id}`)
      setKeywords(saved.keywords)
      setKeywordData(saved.clusters?._keyword_metrics || [])
      setCleaned(saved.cleaned_keywords)
      setContext(saved.context)
      setContextOpen(Boolean(saved.context))
      setMapping(saved.clusters)
      setSourceProjectId(saved.project_id)
      setActiveHistoryId(saved.id)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load the saved architecture')
    } finally { setBusy(null) }
  }

  const openTarget = (keyword: string, included: string[] = [], pageType?: string) => {
    const params = new URLSearchParams({ keyword })
    if (included.length) params.set('cluster', included.join('\n'))
    const isTool = pageType === 'tool' && !informationalIntent.test(keyword)
    navigate(`${isTool ? '/gap-page-prompts' : '/write-blog'}?${params.toString()}`)
  }

  const renderPage = (spoke: string) => {
    const page = parseSpoke(spoke)
    const detail = mapping?.spokes?.find((item) => item.target_keyword.toLowerCase() === page.target.toLowerCase())
    const isTool = detail?.page_type === 'tool' && !informationalIntent.test(`${page.title} ${page.target}`)
    const Icon = isTool ? Wrench : FileText
    return (
      <button key={spoke} type="button" onClick={() => openTarget(page.target, page.included, detail?.page_type)} className="group w-full rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-cyan-400 hover:shadow-md dark:border-slate-700 dark:bg-slate-900 dark:hover:border-cyan-600">
        <div className="flex items-start gap-3">
          <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${isTool ? 'bg-violet-100 text-violet-700 dark:bg-violet-950 dark:text-violet-300' : 'bg-cyan-100 text-cyan-700 dark:bg-cyan-950 dark:text-cyan-300'}`}><Icon className="h-4 w-4" /></span>
          <span className="min-w-0 flex-1">
            <span className="block font-semibold text-slate-900 dark:text-slate-100">{page.title}</span>
            <span className="mt-0.5 block text-xs text-slate-500">Target: {page.target}</span>
            <span className="mt-0.5 block font-mono text-xs text-emerald-700 dark:text-emerald-400">Slug: {pageSlug(page.target, detail?.slug)}</span>
            {(detail?.search_volume != null || detail?.difficulty != null) && <span className="mt-2 flex flex-wrap gap-2 text-[11px] font-semibold"><span className="rounded-full bg-emerald-100 px-2 py-1 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">Volume {detail.search_volume?.toLocaleString() ?? '—'}</span><span className="rounded-full bg-violet-100 px-2 py-1 text-violet-800 dark:bg-violet-950 dark:text-violet-300">KD {detail.difficulty != null ? Math.round(detail.difficulty) : '—'}</span>{detail.ranking_role === 'easy_win_spoke' && <span className="rounded-full bg-amber-100 px-2 py-1 text-amber-800 dark:bg-amber-950 dark:text-amber-300">Easy-win spoke</span>}</span>}
            {detail?.content_brief && <span className="mt-2 block text-sm leading-relaxed text-slate-600 dark:text-slate-300">{detail.content_brief}</span>}
            {detail?.tool_economics?.reason && <span className="mt-2 block text-xs text-slate-500">Format decision: {detail.tool_economics.reason}</span>}
            {(detail?.word_count_suggestion || detail?.h2_sections?.length) && <span className="mt-2 block text-xs text-slate-400">{detail.word_count_suggestion?.toLocaleString()} words{detail.h2_sections?.length ? ` • ${detail.h2_sections.length} planned sections` : ''}</span>}
            {page.included.length > 0 && <span className="mt-3 block rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:bg-amber-950/40 dark:text-amber-200"><strong>Includes:</strong> {page.included.join(' • ')}</span>}
          </span>
          <span className="flex items-center gap-1 text-xs font-semibold text-cyan-700 opacity-70 group-hover:opacity-100 dark:text-cyan-300">{isTool ? 'Build tool' : 'Write page'}<ArrowRight className="h-3.5 w-3.5" /></span>
        </div>
      </button>
    )
  }

  const renderLayers = (layers: LayerMap) => Object.entries(layers || {}).filter(([, spokes]) => spokes?.length).map(([name, spokes]) => (
    <div key={name} className="space-y-3">
      <div className="flex items-center gap-2"><Layers3 className="h-4 w-4 text-slate-400" /><p className="text-xs font-bold uppercase tracking-wider text-slate-500">{name}</p><span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-500 dark:bg-slate-800">{spokes.length} pages</span></div>
      <div className="grid gap-3 lg:grid-cols-2">{spokes.map(renderPage)}</div>
    </div>
  ))

  const renderH2s = (keywords?: string[]) => keywords?.length ? (
    <div className="mt-3 rounded-lg bg-cyan-50 p-3 dark:bg-cyan-950/30">
      <p className="mb-1 text-xs font-bold uppercase tracking-wide text-cyan-700 dark:text-cyan-300">Includes</p>
      <ul className="space-y-1 text-sm text-slate-700 dark:text-slate-300">
        {keywords.map((keyword) => <li key={keyword}>• {keyword}</li>)}
      </ul>
    </div>
  ) : null

  return (
    <div className="space-y-6">
      <section>
        <h2 className="text-2xl font-bold">Hub Spoke</h2>
        <p className="mt-1 text-sm text-slate-500">Give the SEO architecture specialist your site context and keyword research. It will use, consolidate, or discard every keyword and build a cannibalization-safe plan.</p>
      </section>

      {history.length > 0 && (
        <Card className="p-5">
          <div className="flex items-center justify-between gap-4">
            <div><h3 className="font-bold">Previous Hub Spoke plans</h3><p className="mt-1 text-sm text-slate-500">Open any saved architecture and continue where you left off.</p></div>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">{history.length} saved</span>
          </div>
          <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            {history.map((item) => (
              <div key={item.id} className={`relative rounded-xl border transition hover:border-cyan-400 hover:bg-cyan-50/50 dark:hover:border-cyan-700 dark:hover:bg-cyan-950/20 ${activeHistoryId === item.id ? 'border-cyan-500 bg-cyan-50 dark:border-cyan-700 dark:bg-cyan-950/30' : 'border-slate-200 dark:border-slate-700'}`}>
                <button type="button" disabled={busy !== null || deleteHistoryMutation.isPending} onClick={() => loadHistory(item.id)} className="block w-full p-3 pr-11 text-left disabled:opacity-60">
                  <span className="block truncate text-sm font-semibold text-slate-900 dark:text-slate-100">{item.title}</span>
                  <span className="mt-1 flex items-center gap-2 text-xs text-slate-500"><Clock3 className="h-3.5 w-3.5" />{new Date(item.created_at).toLocaleString()} • {item.keyword_count.toLocaleString()} keywords</span>
                </button>
                <button
                  type="button"
                  aria-label={`Permanently delete ${item.title}`}
                  title="Permanently delete plan"
                  disabled={busy !== null || deleteHistoryMutation.isPending}
                  onClick={() => deleteHistory(item)}
                  className="absolute right-2 top-2 flex h-7 w-7 items-center justify-center rounded-lg text-slate-400 transition hover:bg-rose-100 hover:text-rose-700 disabled:opacity-50 dark:hover:bg-rose-950/50 dark:hover:text-rose-300"
                >
                  {deleteHistoryMutation.isPending && deleteHistoryMutation.variables === item.id
                    ? <Loader2 className="h-4 w-4 animate-spin" />
                    : <X className="h-4 w-4" />}
                </button>
              </div>
            ))}
          </div>
        </Card>
      )}

      {projectImport.isLoading && <Card className="p-4 text-sm text-slate-500">Loading keywords and audit context from Gap Hunter…</Card>}

      <Card className="space-y-5 p-6">
        <input ref={inputRef} className="hidden" type="file" accept=".csv,.txt,text/csv,text/plain" onChange={(event) => loadFile(event.target.files?.[0])} />
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => { event.preventDefault(); loadFile(event.dataTransfer.files?.[0]) }}
          className="flex min-h-52 w-full flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-300 bg-slate-50 px-6 text-center hover:border-cyan-500 dark:border-slate-700 dark:bg-slate-900/50"
        >
          <FileUp className="mb-3 h-9 w-9 text-cyan-700 dark:text-cyan-400" />
          <span className="font-semibold">Drop a CSV or TXT keyword list here</span>
          <span className="mt-1 text-sm text-slate-500">or click to add from your computer</span>
        </button>

        {keywords.length > 0 && <p className="text-sm font-medium text-emerald-700 dark:text-emerald-400">Loaded {keywords.length.toLocaleString()} keywords{sourceProjectId ? ' from Gap Hunter' : ''}</p>}

        <div className="flex flex-wrap gap-3">
          <Button variant="secondary" onClick={() => setContextOpen((value) => !value)}><Sparkles className="h-4 w-4" />Add context</Button>
          <Button disabled={!keywords.length || busy !== null} onClick={build}><Network className="h-4 w-4" />{busy === 'build' ? 'SEO specialist is planning…' : 'Build specialist architecture'}</Button>
        </div>

        {contextOpen && (
          <div>
            <label className="mb-2 block text-sm font-semibold">Website and audience context</label>
            <textarea
              className="min-h-40 w-full rounded-lg border border-slate-300 bg-white p-3 text-sm outline-none focus:ring-2 focus:ring-cyan-500 dark:border-slate-700 dark:bg-slate-900"
              value={context}
              onChange={(event) => setContext(event.target.value)}
              placeholder="Describe the site, product, audience, business goals, real capabilities, existing pages, and hard topic boundaries. The specialist will infer and separate search intents."
            />
          </div>
        )}

        {visibleError && <p className="rounded-lg bg-rose-50 p-3 text-sm text-rose-700 dark:bg-rose-900/30 dark:text-rose-300">{visibleError}</p>}
      </Card>

      {cleaned.length > 0 && (
        <Card className="p-6">
          <div className="flex items-center justify-between gap-4">
            <div><h3 className="font-bold">Keywords used by the specialist</h3><p className="text-sm text-slate-500">{cleaned.length.toLocaleString()} keywords became page targets or supporting terms</p></div>
            <Button variant="secondary" onClick={() => downloadText('usable-keywords.txt', cleaned.join('\n'))}><Download className="h-4 w-4" />Download usable keywords</Button>
          </div>
          <div className="mt-4 max-h-64 overflow-auto rounded-lg bg-slate-50 p-4 text-sm dark:bg-slate-900/60">{cleaned.map((keyword) => <div key={keyword}>{keyword}</div>)}</div>
        </Card>
      )}

      {mapping && (
        <section className="space-y-4">
          <div className="flex items-center justify-between gap-4">
            <div><h3 className="text-xl font-bold">Content architecture</h3><p className="mt-1 text-sm text-slate-500">Each card is one indexable page. Includes are reserved for true same-intent variants; valuable easy wins stay as separate spokes.</p>{mapping._deduplication_check && <p className="mt-2 inline-flex rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300">Cannibalization check passed{mapping._deduplication_check.duplicates_removed ? ` • ${mapping._deduplication_check.duplicates_removed} duplicates merged` : ''}</p>}{activeHistoryId && <p className="mt-1 text-xs font-semibold text-emerald-700 dark:text-emerald-400">Saved in Hub Spoke history</p>}{mapping._planning_thought && <p className="mt-2 max-w-3xl text-sm text-slate-600 dark:text-slate-300">{mapping._planning_thought}</p>}</div>
            <Button onClick={() => downloadText('grand-website-architecture-prompt.md', grandArchitecturePrompt(mapping, context))}><Download className="h-4 w-4" />Download architecture prompt</Button>
          </div>
          {mapping.hubs.map((hub) => (
            <Card key={hub.target_keyword} className="overflow-hidden p-0">
              <button type="button" onClick={() => openTarget(hub.target_keyword, hub.h2_keywords, mapping.master_hub?.page_type)} className="group flex w-full items-start gap-4 bg-gradient-to-r from-cyan-700 to-blue-700 p-6 text-left text-white">
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-white/15"><Network className="h-5 w-5" /></span>
                <span className="min-w-0 flex-1"><span className="block text-xl font-bold">MASTER HUB: {mapping.site_domain || hub.target_keyword}</span><span className="mt-1 block text-sm text-cyan-100">Primary keyword: {hub.target_keyword}</span></span>
              </button>
              <div className="space-y-7 p-6">
                {mapping.master_hub?.content_brief && <div className="rounded-xl border border-blue-100 bg-blue-50 p-4 text-sm leading-relaxed text-blue-950 dark:border-blue-900 dark:bg-blue-950/30 dark:text-blue-100"><strong>Content focus:</strong> {mapping.master_hub.content_brief}{mapping.master_hub.word_count_suggestion ? ` • ${mapping.master_hub.word_count_suggestion.toLocaleString()} suggested words` : ''}</div>}
                {renderH2s(hub.h2_keywords)}
                {Object.keys(hub.layers || {}).length > 0 && <div className="space-y-6">{renderLayers(hub.layers)}</div>}
                {(hub.sub_silos || []).length > 0 && <div className="space-y-5 border-t border-slate-200 pt-6 dark:border-slate-800">
                  <div><p className="text-xs font-bold uppercase tracking-wider text-slate-500">Supporting topic clusters</p><p className="mt-1 text-sm text-slate-500">Pillar pages with their own focused supporting content.</p></div>
                  {(hub.sub_silos || []).map((silo) => <div key={silo.target_keyword} className="rounded-2xl border border-slate-200 bg-slate-50/70 p-5 dark:border-slate-700 dark:bg-slate-900/60"><button type="button" onClick={() => openTarget(silo.target_keyword, silo.h2_keywords)} className="group flex w-full items-center justify-between gap-4 text-left"><span><span className="font-bold text-slate-900 dark:text-slate-100">{silo.hub_title}</span><span className="mt-0.5 block text-xs text-slate-500">Target: {silo.target_keyword}</span></span><span className="flex items-center gap-1 text-xs font-semibold text-cyan-700 dark:text-cyan-300">Open pillar <ArrowRight className="h-3.5 w-3.5" /></span></button>{renderH2s(silo.h2_keywords)}<div className="mt-5 space-y-6">{renderLayers(silo.layers)}</div></div>)}
                </div>}
              </div>
            </Card>
          ))}
          {mapping.interlinking_strategy && <Card className="border-emerald-200 bg-emerald-50/70 p-5 dark:border-emerald-900 dark:bg-emerald-950/20"><p className="text-xs font-bold uppercase tracking-wider text-emerald-700 dark:text-emerald-300">Interlinking strategy</p><p className="mt-2 text-sm leading-relaxed text-slate-700 dark:text-slate-300">{mapping.interlinking_strategy}</p></Card>}
          {mapping.discarded_keywords && mapping.discarded_keywords.length > 0 && <Card className="p-5"><p className="text-xs font-bold uppercase tracking-wider text-slate-500">Discarded by the SEO specialist</p><p className="mt-1 text-sm text-slate-500">These queries do not need a page or supporting placement in this architecture.</p><div className="mt-3 max-h-72 space-y-2 overflow-auto">{mapping.discarded_keywords.map((item) => <div key={item.keyword} className="rounded-lg bg-slate-50 px-3 py-2 text-sm dark:bg-slate-900"><span className="font-semibold">{item.keyword}</span><span className="ml-2 text-slate-500">— {item.reason}</span></div>)}</div></Card>}
        </section>
      )}
    </div>
  )
}
