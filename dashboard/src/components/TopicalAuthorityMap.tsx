import { useMemo, useRef, useState } from 'react'
import { ArrowDown, ArrowRight, CheckCircle2, Download, FileText, Link2, Network, Search, Wrench, X } from 'lucide-react'
import { Button } from './ui/Button'
import { Card } from './ui/Card'
import { PAGE_COUNT_POLICY, downloadText, type Mapping, type PageDetail, type MapLink } from '../lib/hubSpoke'

type Props = { mapping: Mapping; onOpen: (page: PageDetail) => void }
const colors = ['border-cyan-400', 'border-violet-400', 'border-emerald-400', 'border-amber-400', 'border-rose-400', 'border-blue-400']
const label = (page: PageDetail) => page.article_title || page.target_keyword || 'Untitled page'
const evidence = (page: PageDetail) => page.evidence_type === 'editorial_proposal' ? 'Research idea' : 'Supplied keyword'
const safeUrl = (value?: string | null) => value && /^https?:\/\//i.test(value) ? value : undefined

function fallbackLinks(pages: PageDetail[]): MapLink[] {
  return pages.flatMap(page => (page.internal_links || []).flatMap(target => {
    const other = pages.find(candidate => candidate.target_keyword === target)
    return other ? [{ source: page.id || page.target_keyword!, target: other.id || target, source_keyword: page.target_keyword!, target_keyword: target, source_url: page.existing_url || page.slug || '/', target_url: other.existing_url || other.slug || '/', anchor_text: label(other), relationship: 'related', reason: 'Link recorded in this saved plan.' }] : []
  }))
}

export function TopicalAuthorityMap({ mapping, onOpen }: Props) {
  const briefRef = useRef<HTMLElement>(null)
  const [tab, setTab] = useState<'map' | 'pages' | 'links' | 'keywords'>('map')
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const [selectedTarget, setSelectedTarget] = useState<string | null>(mapping.master_hub?.target_keyword || null)
  const pages = useMemo(() => [mapping.master_hub, ...(mapping.spokes || [])].filter((page): page is PageDetail => Boolean(page?.target_keyword)), [mapping])
  const selected = pages.find(page => page.target_keyword === selectedTarget)
  const links = mapping.link_plan || fallbackLinks(pages)
  const matches = (page: PageDetail) => `${label(page)} ${page.target_keyword} ${page.spoke_category || ''} ${(page.targeted_keywords || []).join(' ')}`.toLowerCase().includes(query.toLowerCase()) && (filter === 'all' || (filter === 'research' ? page.evidence_type === 'editorial_proposal' : filter === 'update' ? page.action === 'update' : page.page_type === filter))
  const visible = pages.filter(matches)
  const groups = useMemo(() => {
    if (mapping.topic_clusters?.length) {
      const byId = new Map((mapping.spokes || []).map(page => [page.id, page]))
      return mapping.topic_clusters.map(group => [group.name, group.page_ids.flatMap(id => byId.has(id) ? [byId.get(id)!] : [])] as [string, PageDetail[]])
    }
    const result = new Map<string, PageDetail[]>()
    for (const page of mapping.spokes || []) {
      const name = page.spoke_category || 'Supporting topics'
      result.set(name, [...(result.get(name) || []), page])
    }
    return [...result.entries()]
  }, [mapping])
  const visibleLinks = links.filter(link => `${link.source_keyword} ${link.target_keyword} ${link.source_url} ${link.target_url}`.toLowerCase().includes(query.toLowerCase()) && (filter === 'all' || visible.some(page => page.target_keyword === link.source_keyword || page.target_keyword === link.target_keyword)))
  const selectTarget = (target: string) => {
    setSelectedTarget(target)
    if (window.matchMedia('(max-width: 1279px)').matches) {
      window.requestAnimationFrame(() => briefRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
    }
  }
  const selectPage = (page: PageDetail) => selectTarget(page.target_keyword || '')
  const card = (page: PageDetail) => (
    <button key={page.target_keyword} type="button" aria-pressed={selectedTarget === page.target_keyword} onClick={() => selectPage(page)} className={`w-full rounded-xl border p-4 text-left transition hover:border-cyan-500 hover:shadow-md ${selectedTarget === page.target_keyword ? 'border-cyan-500 bg-cyan-50 ring-1 ring-cyan-500 dark:bg-cyan-950/40' : 'border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900'}`}>
      <span className="mb-2 flex items-center justify-between gap-2 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
        <span className="flex items-center gap-1.5">{page.page_type === 'tool' ? <Wrench className="h-3.5 w-3.5" /> : <FileText className="h-3.5 w-3.5" />}{page.page_type || 'article'}</span>
        <span>{page.action === 'update' ? 'Improve existing' : page.action === 'create' ? 'New page' : 'Review page'}</span>
      </span>
      <span className="block text-sm font-semibold leading-5">{label(page)}</span>
      <span className="mt-1 block break-all font-mono text-[11px] text-slate-500">{page.slug || '/'}</span>
      <span className={`mt-3 inline-flex rounded-md px-2 py-1 text-[10px] font-medium ${page.evidence_type === 'editorial_proposal' ? 'bg-amber-50 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300' : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'}`}>{evidence(page)}</span>
    </button>
  )

  return <section className="space-y-4" aria-label="Topical authority map">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h3 className="text-xl font-bold">Your topical authority map</h3><p className="mt-1 text-sm text-slate-500">Select a page to inspect its purpose, keyword coverage and connections.</p></div>
      <Button variant="secondary" onClick={() => downloadText('topical-authority-map.json', JSON.stringify(mapping, null, 2))}><Download className="h-4 w-4" />Export map</Button>
    </div>
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {[['Pages', pages.length], ['Topic groups', groups.length], ['Existing pages', pages.filter(p => p.action === 'update').length], ['Ideas to research', pages.filter(p => p.evidence_type === 'editorial_proposal').length]].map(([name, value]) => <Card key={name} className="p-4"><p className="text-xs text-slate-500">{name}</p><p className="mt-1 text-2xl font-bold">{value}</p></Card>)}
    </div>
    <Card className="p-4">
      <div className="flex flex-wrap items-center gap-2 text-sm font-semibold"><CheckCircle2 className={`h-4 w-4 ${mapping._semantic_audit_status === 'passed' ? 'text-emerald-600' : 'text-amber-600'}`} />{mapping._semantic_audit_status === 'passed' ? 'Intent review passed' : 'Intent review needed'}<span className="font-normal text-slate-500">· Editorial plan; validate demand before publishing</span></div>
      {mapping.authority_coverage && <div className="mt-3 space-y-1 text-sm"><p className="font-semibold">{mapping.spokes?.length ?? mapping.authority_coverage.actual_spokes} spokes</p><p className="text-slate-500">{PAGE_COUNT_POLICY}</p>{mapping.authority_coverage.discovery_status === 'unavailable' && <p className="text-amber-700 dark:text-amber-300">Topic discovery was unavailable; this map uses the supplied inventory.</p>}</div>}
      {mapping.map_warnings?.map(warning => <p key={warning} className="mt-2 text-sm text-amber-700 dark:text-amber-300">{warning}</p>)}
      {mapping._planning_thought && <details className="mt-3 text-sm"><summary className="cursor-pointer text-slate-500">Planning rationale</summary><p className="mt-2 leading-relaxed">{mapping._planning_thought}</p></details>}
      {!!mapping.intent_consolidations?.length && <details className="mt-3 text-sm"><summary className="cursor-pointer font-semibold">Consolidated intent overlaps ({mapping.intent_consolidations.length})</summary><p className="mt-2 text-slate-500">These keywords share an existing task. Keep them on the assigned page instead of creating extra URLs.</p><ul className="mt-3 space-y-3">{mapping.intent_consolidations.map(item => <li key={item.from_keyword} className="break-words"><p className="font-medium">{item.from_keyword} → {item.to_keyword}</p><p className="mt-1 text-xs text-slate-500">{item.risk_type === 'doorway' ? 'Near-duplicate page risk' : 'Same user need'}: {item.reason}</p></li>)}</ul></details>}
    </Card>
    <Card className="overflow-hidden p-0">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 p-4 dark:border-slate-800">
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="Map views">{(['map', 'pages', 'links', 'keywords'] as const).map(view => <button key={view} type="button" id={`map-tab-${view}`} role="tab" tabIndex={tab === view ? 0 : -1} aria-controls="map-panel" aria-selected={tab === view} onKeyDown={event => {
          const views = ['map', 'pages', 'links', 'keywords'] as const
          const index = views.indexOf(view)
          const next = event.key === 'ArrowRight' ? (index + 1) % 4 : event.key === 'ArrowLeft' ? (index + 3) % 4 : event.key === 'Home' ? 0 : event.key === 'End' ? 3 : -1
          if (next >= 0) { event.preventDefault(); setTab(views[next]); document.getElementById(`map-tab-${views[next]}`)?.focus() }
        }} onClick={() => setTab(view)} className={`rounded-lg px-3 py-2 text-sm font-semibold capitalize ${tab === view ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900' : 'text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800'}`}>{view === 'keywords' ? 'Keyword decisions' : view === 'links' ? `Links (${links.length})` : view}</button>)}</div>
        <div className="flex flex-wrap gap-2"><label className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 dark:border-slate-700"><Search className="h-4 w-4 text-slate-400" /><input aria-label="Search map" placeholder="Find a topic or page…" value={query} onChange={event => setQuery(event.target.value)} className="w-40 bg-transparent py-2 text-sm outline-none" /></label><select aria-label="Filter pages" value={filter} onChange={event => setFilter(event.target.value)} className="rounded-lg border border-slate-200 bg-white px-2 text-sm dark:border-slate-700 dark:bg-slate-900"><option value="all">All pages</option><option value="article">Articles</option><option value="tool">Tools</option><option value="update">Existing pages</option><option value="research">Research ideas</option></select></div>
      </div>
      <div className={`grid ${selected ? 'xl:grid-cols-[minmax(0,1fr)_340px]' : ''}`}>
        <div id="map-panel" role="tabpanel" aria-labelledby={`map-tab-${tab}`} className="min-w-0 bg-slate-50/70 p-4 dark:bg-slate-950/40 sm:p-6">
          {tab === 'map' && <>
            {mapping.master_hub?.target_keyword && <div className="mx-auto max-w-sm"><div className="mb-2 flex items-center justify-center gap-2 text-xs font-semibold uppercase tracking-wider text-cyan-700 dark:text-cyan-300"><Network className="h-4 w-4" />Main hub</div>{card(mapping.master_hub)}</div>}
            {groups.length > 0 && <><div className="flex justify-center py-3 text-slate-300 dark:text-slate-600"><ArrowDown className="h-6 w-6" /></div><p className="mb-4 text-center text-xs text-slate-500">Topic groups organize the pages below. Open Links for the actual page connections.</p><div className="grid items-start gap-4 md:grid-cols-2 2xl:grid-cols-3">{groups.map(([name, members], index) => { const filtered = members.filter(matches); return filtered.length > 0 && <div key={name} className={`rounded-xl border-t-4 bg-slate-100/70 p-3 dark:bg-slate-800/40 ${colors[index % colors.length]}`}><div className="mb-3 flex items-center justify-between gap-2"><h4 className="text-sm font-bold">{name}</h4><span className="text-xs text-slate-500">{filtered.length}</span></div><div className="space-y-2">{filtered.map(card)}</div></div> })}</div></>}
            {!mapping.spokes?.length && <p className="py-8 text-center text-sm text-slate-500">No distinct supporting pages were identified. Add evidence for more reader tasks and rebuild.</p>}
            {pages.length > 0 && visible.length === 0 && <p className="py-8 text-center text-sm text-slate-500">No pages match these filters.</p>}
          </>}
          {tab === 'pages' && <div className="space-y-2">{visible.map(page => <button key={page.target_keyword} type="button" onClick={() => selectPage(page)} className="flex w-full items-start justify-between gap-4 rounded-xl border border-slate-200 bg-white p-4 text-left hover:border-cyan-500 dark:border-slate-700 dark:bg-slate-900"><span className="min-w-0"><span className="block text-sm font-semibold">{label(page)}</span><span className="mt-1 block text-xs text-slate-500">{page.search_intent || page.content_brief}</span><span className="mt-2 block break-all font-mono text-xs text-slate-500">{page.existing_url || page.slug}</span></span><span className="shrink-0 text-xs text-slate-500">{page.action === 'update' ? 'Improve' : page.action === 'create' ? 'Create' : 'Review'}<ArrowRight className="mt-2 h-4 w-4" /></span></button>)}{!visible.length && <p className="p-6 text-sm text-slate-500">No pages match these filters.</p>}</div>}
          {tab === 'links' && <div className="space-y-3"><p className="text-sm text-slate-500">Directed links to implement in relevant page content. Suggested anchors can be adapted naturally.</p><Button variant="secondary" onClick={() => downloadText('internal-links.csv', ['Source URL,Target URL,Anchor text,Relationship', ...links.map(link => [link.source_url, link.target_url, link.anchor_text, link.relationship].map(value => `"${value.replace(/"/g, '""')}"`).join(','))].join('\n'))}><Download className="h-4 w-4" />Export links</Button>{visibleLinks.map(link => <div key={`${link.source}-${link.target}`} className="rounded-xl border border-slate-200 bg-white p-4 text-sm dark:border-slate-700 dark:bg-slate-900"><p className="break-words font-medium">{link.source_keyword}<ArrowRight className="mx-2 inline h-4 w-4 text-slate-400" /><button type="button" onClick={() => selectTarget(link.target_keyword)} className="text-cyan-700 underline underline-offset-2 dark:text-cyan-300">{link.target_keyword}</button></p><p className="mt-2 break-all font-mono text-xs text-slate-500">{link.source_url} → {link.target_url}</p><p className="mt-2 text-xs text-slate-500">Anchor: {link.anchor_text} · {link.reason}</p></div>)}{!visibleLinks.length && <p className="p-6 text-sm text-slate-500">No links match these filters.</p>}</div>}
          {tab === 'keywords' && <div className="space-y-2"><p className="mb-4 text-sm text-slate-500">Every keyword gets one destination or a documented reason for exclusion.</p>{(mapping.keyword_assignments || []).filter(item => `${item.keyword} ${item.assigned_to || ''}`.toLowerCase().includes(query.toLowerCase()) && (filter === 'all' || visible.some(page => page.target_keyword === item.assigned_to))).map(item => <div key={item.keyword} className="rounded-xl border border-slate-200 bg-white p-4 text-sm dark:border-slate-700 dark:bg-slate-900"><div className="flex flex-wrap justify-between gap-2"><strong>{item.keyword}</strong><span className="text-xs text-slate-500">{item.disposition.replace('_', ' ')}</span></div>{item.assigned_to && <button type="button" onClick={() => selectTarget(item.assigned_to!)} className="mt-1 text-xs text-cyan-700 underline dark:text-cyan-300">{item.assigned_to} {item.placement ? `· ${item.placement}` : ''}</button>}<p className="mt-2 text-xs text-slate-500">{item.reason}</p></div>)}{!mapping.keyword_assignments?.length && <p className="text-sm text-slate-500">This saved plan has no recorded keyword decisions.</p>}</div>}
        </div>
        {selected && <aside ref={briefRef} aria-label="Page brief" className="border-t border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900 xl:border-l xl:border-t-0">
          <div className="xl:sticky xl:top-6 xl:max-h-[calc(100vh-3rem)] xl:overflow-y-auto">
          <div className="flex items-start justify-between gap-3"><p className="text-xs font-bold uppercase tracking-wider text-slate-400">Page brief</p><button type="button" aria-label="Close page brief" onClick={() => setSelectedTarget(null)} className="rounded p-1 hover:bg-slate-100 dark:hover:bg-slate-800"><X className="h-4 w-4" /></button></div>
          <h4 className="mt-3 text-lg font-bold">{label(selected)}</h4><p className="mt-1 break-all font-mono text-xs text-slate-500">{selected.slug || '/'}</p>
          <p className="mt-3 text-xs font-medium text-cyan-700 dark:text-cyan-300">{evidence(selected)} · {selected.action === 'update' ? 'Improve existing page' : selected.action === 'create' ? 'Create page' : 'Review page'}</p>
          {safeUrl(selected.existing_url) && <a href={safeUrl(selected.existing_url)} target="_blank" rel="noreferrer" className="mt-2 block break-all text-xs text-cyan-700 underline dark:text-cyan-300">Open existing page ↗</a>}
          <div className="mt-5 space-y-5 text-sm">
            <div><p className="mb-1 font-semibold">Reader task</p><p className="text-slate-500">{selected.reader_outcome || selected.search_intent || selected.content_brief || 'Review the purpose of this page before writing.'}</p></div>
            {selected.user_problem && <div><p className="mb-1 font-semibold">User problem</p><p className="text-slate-500">{selected.user_problem}</p></div>}
            {selected.entity_topic && <div><p className="mb-1 font-semibold">Entity/topic</p><p className="text-slate-500">{selected.entity_topic}</p></div>}
            <div><p className="mb-1 font-semibold">Content requirements</p><p className="text-slate-500">Enough content to completely satisfy this page’s unique intent. No fixed word count.</p>{!!selected.content_requirements?.length && <ul className="mt-2 list-disc space-y-1 pl-4 text-slate-500">{selected.content_requirements.map(requirement => <li key={requirement}>{requirement}</li>)}</ul>}</div>
            {selected.url_decision_reason && <div><p className="mb-1 font-semibold">URL decision</p><p className="text-slate-500">{selected.url_decision_reason}</p></div>}
            {selected.unique_page_value && <div><p className="mb-1 font-semibold">Unique page value</p><p className="text-slate-500">{selected.unique_page_value}</p></div>}
            {selected.content_brief && <div><p className="mb-1 font-semibold">Coverage</p><p className="leading-relaxed text-slate-500">{selected.content_brief}</p></div>}
            {!!selected.scope_out?.length && <div><p className="mb-1 font-semibold">Leave to other pages</p><ul className="list-disc space-y-1 pl-4 text-slate-500">{selected.scope_out.map(scope => <li key={scope}>{scope}</li>)}</ul></div>}
            <div><p className="mb-1 font-semibold">Primary keyword</p><p className="text-slate-500">{selected.target_keyword}</p><p className="mt-2 text-xs text-slate-400">Volume: {selected.search_volume?.toLocaleString() ?? 'Unknown'} · Difficulty: {selected.difficulty ?? 'Unknown'}</p></div>
            {selected.evidence_type === 'editorial_proposal' && <div className="rounded-lg bg-amber-50 p-3 text-xs leading-relaxed text-amber-800 dark:bg-amber-950/40 dark:text-amber-200">Proposed from: {selected.support_phrase || 'site context'}. {selected.evidence_rationale || 'Confirm relevance and demand with research.'} No measured demand is implied.</div>}
            {!!selected.targeted_keywords?.length && <div><p className="mb-2 font-semibold">Supporting keywords</p><div className="flex flex-wrap gap-1.5">{selected.targeted_keywords.map(keyword => <span key={keyword} className="rounded bg-slate-100 px-2 py-1 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">{keyword}</span>)}</div></div>}
            {!!selected.h2_sections?.length && <div><p className="mb-2 font-semibold">Section outline</p><ol className="list-decimal space-y-2 pl-4 text-slate-500">{selected.h2_sections.map((section, index) => <li key={index}><span className="font-medium">{section.h2_heading}</span>{section.section_definition && <p className="mt-0.5 text-xs">{section.section_definition}</p>}</li>)}</ol></div>}
            {!!selected.faq_schema_questions?.length && <div><p className="mb-2 font-semibold">Questions to answer</p>{selected.faq_schema_questions.map((faq, index) => <p key={index} className="mt-1 text-slate-500">{faq.question}</p>)}</div>}
            {!!selected.tool_functions?.length && <div><p className="mb-2 font-semibold">Tool requirements</p><ul className="list-disc pl-4 text-slate-500">{selected.tool_functions.map(item => <li key={item}>{item}</li>)}</ul></div>}
            <div><p className="mb-2 flex items-center gap-2 font-semibold"><Link2 className="h-4 w-4" />Link to</p><div className="space-y-2">{links.filter(link => link.source_keyword === selected.target_keyword).map(link => <button key={link.target} type="button" onClick={() => selectTarget(link.target_keyword)} className="block text-left text-xs text-cyan-700 hover:underline dark:text-cyan-300">{link.target_keyword} <span className="text-slate-400">({link.relationship})</span></button>)}</div></div>
            <Button className="w-full" onClick={() => onOpen(selected)}>{selected.page_type === 'tool' ? 'Build tool' : selected.action === 'update' ? 'Improve page' : 'Write page'}<ArrowRight className="h-4 w-4" /></Button>
          </div>
          </div>
        </aside>}
      </div>
    </Card>
  </section>
}
