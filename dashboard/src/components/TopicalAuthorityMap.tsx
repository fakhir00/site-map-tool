import { useMemo, useRef, useState } from 'react'
import { ArrowDown, ArrowRight, CheckCircle2, Download, FileText, Link2, Network, Search, Wrench, X } from 'lucide-react'
import { Button } from './ui/Button'
import { Card } from './ui/Card'
import { downloadText, isExistingPage, isToolPage, keywordCoverage, pageKeywords, pageEditor, pageActionLabel, type Mapping, type PageDetail, type MapLink } from '../lib/hubSpoke'

type Props = { mapping: Mapping; onOpen: (page: PageDetail) => void }
const tabHelp = {
  map: { title: 'See how your topics fit together', text: 'The hub is your main topic. Spokes are supporting pages grouped by topic. Select a card to read its brief, or use Create tool, Create blog or Create page to open the right editor with the plan filled in.' },
  pages: { title: 'Choose what to create or improve', text: 'Work through your content plan here. Create tool opens Build Page; Create blog opens Blog Writer; Create page opens the page builder. Pages already on your site are marked Existing page. Improve them at their current URL instead of creating duplicates.' },
  links: { title: 'Connect related pages on your site', text: 'Each arrow shows which page should link to another. Add the link within relevant content using the suggested anchor text (the clickable words). Select a destination to read its brief, or export the link list.' },
  keywords: { title: 'Understand where each keyword belongs', text: 'Main keyword is the primary topic of a page. Include on page means cover it within that page, without creating another URL. Not included means it does not need a page in this plan. Select a destination to see its brief.' },
}
/** Pillar group accents cycle through the Blueprint roles. */
const groupAccents = [
  'border-t-sky-400 dark:border-t-site-sky',
  'border-t-amber-400 dark:border-t-signal-amber',
  'border-t-emerald-400 dark:border-t-built-green',
  'border-t-slate-300 dark:border-t-line',
]
const label = (page: PageDetail) => page.article_title || page.target_keyword || 'Untitled page'
const evidence = (page: PageDetail) => page.evidence_type === 'editorial_proposal' ? 'Research idea' : 'Supplied keyword'
const safeUrl = (value?: string | null) => value && /^https?:\/\//i.test(value) ? value : undefined

/** Locked node legend: existing = solid Site Sky, to create = dashed Amber, built = Built Green. */
const nodeStatus = (page: PageDetail): 'built' | 'existing' | 'missing' =>
  page.action === 'built' ? 'built' : isExistingPage(page) ? 'existing' : 'missing'
const nodeBorder = (page: PageDetail) =>
  nodeStatus(page) === 'built'
    ? 'border-emerald-400 dark:border-built-green'
    : nodeStatus(page) === 'existing'
      ? 'border-sky-400 dark:border-site-sky'
      : 'border-dashed border-amber-400 dark:border-signal-amber'
const nodeStatusLabel = (page: PageDetail) =>
  nodeStatus(page) === 'built' ? 'Built' : isExistingPage(page) ? 'Existing page' : page.action === 'create' ? 'New page' : 'Review page'
const nodeStatusTone = (page: PageDetail) =>
  nodeStatus(page) === 'built'
    ? 'text-emerald-600 dark:text-built-green'
    : nodeStatus(page) === 'existing'
      ? 'text-sky-700 dark:text-site-sky'
      : 'text-amber-700 dark:text-signal-amber'

function fallbackLinks(pages: PageDetail[]): MapLink[] {
  return pages.flatMap(page => (page.internal_links || []).flatMap(target => {
    const other = pages.find(candidate => candidate.target_keyword === target)
    return other ? [{ source: page.id || page.target_keyword!, target: other.id || target, source_keyword: page.target_keyword!, target_keyword: target, source_url: page.existing_url || page.slug || '/', target_url: other.existing_url || other.slug || '/', anchor_text: label(other), relationship: 'related', reason: 'Link recorded in this saved plan.' }] : []
  }))
}

export function TopicalAuthorityMap({ mapping, onOpen }: Props) {
  const briefRef = useRef<HTMLElement>(null)
  const [tab, setTab] = useState<'map' | 'pages' | 'links' | 'keywords'>('pages')
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const [selectedTarget, setSelectedTarget] = useState<string | null>(mapping.master_hub?.target_keyword || null)
  const pages = useMemo(() => [mapping.master_hub, ...(mapping.spokes || [])].filter((page): page is PageDetail => Boolean(page?.target_keyword)), [mapping])
  const coverage = useMemo(() => keywordCoverage(mapping), [mapping])
  const selected = pages.find(page => page.target_keyword === selectedTarget)
  const researchIncomplete = mapping.authority_coverage?.discovery_status === 'unavailable'
  const links = mapping.link_plan || fallbackLinks(pages)
  const existingCount = pages.filter(page => isExistingPage(page)).length
  const missingCount = pages.filter(page => !isExistingPage(page)).length
  const matches = (page: PageDetail) => `${label(page)} ${page.target_keyword} ${page.spoke_category || ''} ${(page.targeted_keywords || []).join(' ')}`.toLowerCase().includes(query.toLowerCase()) && (filter === 'all' || (filter === 'research' ? page.evidence_type === 'editorial_proposal' : filter === 'update' ? isExistingPage(page) : filter === 'create' ? !isExistingPage(page) && page.action === 'create' : filter === 'article' ? pageEditor(page) === 'blog' : pageEditor(page) === 'page'))
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
    <div key={page.target_keyword} className="space-y-2"><button type="button" aria-pressed={selectedTarget === page.target_keyword} onClick={() => selectPage(page)} className={`w-full rounded-xl border-2 p-4 text-left transition hover:shadow-md ${selectedTarget === page.target_keyword ? 'border-sky-500 bg-sky-50 ring-1 ring-sky-500 dark:border-site-sky dark:bg-site-sky/10 dark:ring-site-sky' : `${nodeBorder(page)} bg-white dark:bg-raised`}`}>
      <span className="mb-2 flex items-center justify-between gap-2 text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-muted">
        <span className="flex items-center gap-1.5">{isToolPage(page) ? <Wrench className="h-3.5 w-3.5" /> : <FileText className="h-3.5 w-3.5" />}{isToolPage(page) ? 'Tool' : pageEditor(page) === 'blog' ? 'Blog' : 'Page'}</span>
        <span className={nodeStatusTone(page)}>{nodeStatusLabel(page)}</span>
      </span>
      <span className="block text-sm font-semibold leading-5 text-slate-900 dark:text-text">{label(page)}</span>
      <span className="mt-1 block break-all font-mono text-[11px] text-slate-500 dark:text-muted">{page.existing_url || page.slug || '/'}</span>
      <span className="mt-2 block font-mono text-xs text-slate-500 dark:text-muted">{pageKeywords(page).length} keywords covered · {(page.targeted_keywords || []).length} supporting</span>
      <span className={`mt-3 inline-flex rounded-md px-2 py-1 text-[10px] font-medium ${page.evidence_type === 'editorial_proposal' ? 'bg-amber-50 text-amber-800 dark:bg-signal-amber/10 dark:text-signal-amber' : 'bg-slate-100 text-slate-600 dark:bg-blueprint-deep dark:text-muted'}`}>{evidence(page)}</span>
    </button><Button size="sm" variant="secondary" className="w-full" onClick={() => onOpen(page)}>{pageActionLabel(page)}<ArrowRight className="h-4 w-4" /></Button></div>
  )
  const statCards: Array<[string, number, string]> = [
    ['Pages', pages.length, 'text-slate-900 dark:text-text'],
    ['Topic groups', groups.length, 'text-slate-900 dark:text-text'],
    ['Existing pages', existingCount, 'text-sky-700 dark:text-site-sky'],
    ['Ideas to research', pages.filter(p => p.evidence_type === 'editorial_proposal').length, 'text-amber-700 dark:text-signal-amber'],
  ]

  return <section className="space-y-4" aria-label="Topical authority map">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-display text-xl font-bold text-slate-950 dark:text-text">Your topical authority map</h3>
          {mapping.site_domain && <span className="rounded-md border border-slate-200 bg-slate-100 px-2 py-0.5 font-mono text-xs text-slate-600 dark:border-line dark:bg-raised dark:text-muted">{mapping.site_domain}</span>}
        </div>
        <p className="mt-1 text-sm text-slate-500 dark:text-muted">Select a page to inspect its purpose, keyword coverage and connections.</p>
      </div>
      <Button variant="secondary" onClick={() => downloadText('topical-authority-map.json', JSON.stringify(mapping, null, 2))}><Download className="h-4 w-4" />Export map</Button>
    </div>
    <div className="flex flex-wrap items-center gap-x-8 gap-y-4 rounded-2xl border border-slate-200 bg-white p-4 dark:border-line dark:bg-panel" aria-label="Site coverage summary">
      <div>
        <p className="text-xs text-slate-500 dark:text-muted">Your site</p>
        <p className="mt-1 font-mono text-2xl font-semibold text-sky-700 dark:text-site-sky">{existingCount.toLocaleString()} <span className="text-sm font-normal">pages</span></p>
      </div>
      <ArrowRight className="h-5 w-5 shrink-0 text-slate-300 dark:text-line" aria-hidden />
      <div>
        <p className="text-xs text-slate-500 dark:text-muted">Missing pages</p>
        <p className="mt-1 font-mono text-2xl font-semibold text-amber-700 dark:text-signal-amber">{missingCount.toLocaleString()} <span className="text-sm font-normal">to create</span></p>
      </div>
      <div className="ml-auto">
        <p className="text-xs text-slate-500 dark:text-muted">Planned total</p>
        <p className="mt-1 text-right font-mono text-2xl font-semibold text-slate-700 dark:text-text">{pages.length.toLocaleString()}</p>
      </div>
    </div>
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {statCards.map(([name, value, tone]) => <Card key={name} className="p-4"><p className="text-xs text-slate-500 dark:text-muted">{name}</p><p className={`mt-1 font-mono text-2xl font-semibold ${tone}`}>{value.toLocaleString()}</p></Card>)}
    </div>
    <div aria-label="Keyword coverage" className="rounded-xl border border-sky-200 bg-sky-50 p-4 text-sm dark:border-line dark:bg-raised">
      <p className="font-semibold text-slate-900 dark:text-text"><span className="font-mono text-sky-700 dark:text-site-sky">{coverage.used}</span> of <span className="font-mono">{coverage.total}</span> keywords used across <span className="font-mono">{pages.length}</span> pages</p>
      <p className="mt-1 text-slate-600 dark:text-muted">{coverage.supporting} supporting keywords are included within page content. Related phrases can share a page; each page covers one distinct reader task.</p>
      {coverage.excluded > 0 && <button type="button" onClick={() => { setTab('keywords'); setQuery(''); setFilter('all') }} className="mt-2 font-mono text-xs font-medium text-sky-800 underline dark:text-site-sky">{coverage.excluded} keywords excluded · Review keyword decisions</button>}
      {coverage.unassigned > 0 && <p className="mt-2 font-mono text-xs text-amber-800 dark:text-signal-amber">{coverage.unassigned} {coverage.unassigned === 1 ? 'keyword has' : 'keywords have'} no recorded placement in this saved map. Rebuild to review coverage.</p>}
    </div>
    <Card className="p-4">
      <div className="flex flex-wrap items-center gap-2 text-sm font-semibold text-slate-900 dark:text-text"><CheckCircle2 className={`h-4 w-4 ${!researchIncomplete && mapping._semantic_audit_status === 'passed' ? 'text-emerald-600 dark:text-built-green' : 'text-amber-600 dark:text-signal-amber'}`} />{researchIncomplete ? 'Topic research incomplete' : mapping._semantic_audit_status === 'passed' ? 'Intent review passed' : 'Intent review needed'}<span className="font-normal text-slate-500 dark:text-muted">{researchIncomplete ? '· Partial map from supplied keywords' : '· Editorial plan; validate demand before publishing'}</span></div>
      {mapping.authority_coverage && <div className="mt-3 space-y-1 text-sm"><p className="font-mono font-semibold text-slate-900 dark:text-text">{mapping.spokes?.length ?? mapping.authority_coverage.actual_spokes} spokes</p><p className="text-slate-500 dark:text-muted">There is no fixed number of pages. Add a page only when it answers a different question or helps the reader do a different task.</p>{researchIncomplete && <p role="status" className="text-amber-700 dark:text-signal-amber">Topic research did not finish. Use Build topical map above to retry. Zero spokes here does not mean your site has no useful supporting topics.</p>}</div>}
      {mapping.map_warnings?.map(warning => <p key={warning} className="mt-2 text-sm text-amber-700 dark:text-signal-amber">{warning}</p>)}
      {mapping._planning_thought && <details className="mt-3 text-sm"><summary className="cursor-pointer text-slate-500 dark:text-muted">Planning rationale</summary><p className="mt-2 leading-relaxed text-slate-600 dark:text-muted">{mapping._planning_thought}</p></details>}
      {!!mapping.intent_consolidations?.length && <details className="mt-3 text-sm"><summary className="cursor-pointer font-semibold text-slate-900 dark:text-text">Consolidated intent overlaps ({mapping.intent_consolidations.length})</summary><p className="mt-2 text-slate-500 dark:text-muted">These keywords share an existing task. Keep them on the assigned page instead of creating extra URLs.</p><ul className="mt-3 space-y-3">{mapping.intent_consolidations.map(item => <li key={item.from_keyword} className="break-words"><p className="font-mono font-medium text-slate-800 dark:text-text">{item.from_keyword} → {item.to_keyword}</p><p className="mt-1 text-xs text-slate-500 dark:text-muted">{item.risk_type === 'doorway' ? 'Near-duplicate page risk' : 'Same user need'}: {item.reason}</p></li>)}</ul></details>}
    </Card>
    <Card className="overflow-hidden p-0">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 p-4 dark:border-line">
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="Map views">{(['pages', 'map', 'links', 'keywords'] as const).map(view => <button key={view} type="button" id={`map-tab-${view}`} role="tab" tabIndex={tab === view ? 0 : -1} aria-controls="map-panel" aria-selected={tab === view} onKeyDown={event => {
          const views = ['pages', 'map', 'links', 'keywords'] as const
          const index = views.indexOf(view)
          const next = event.key === 'ArrowRight' ? (index + 1) % views.length : event.key === 'ArrowLeft' ? (index + views.length - 1) % views.length : event.key === 'Home' ? 0 : event.key === 'End' ? views.length - 1 : -1
          if (next >= 0) { event.preventDefault(); setTab(views[next]); document.getElementById(`map-tab-${views[next]}`)?.focus() }
        }} onClick={() => setTab(view)} className={`rounded-lg px-3 py-2 text-sm font-semibold ${tab === view ? 'border border-line bg-slate-900 text-white dark:bg-raised dark:text-text' : 'text-slate-500 hover:bg-slate-100 dark:text-muted dark:hover:bg-raised/70 dark:hover:text-text'}`}>{view === 'keywords' ? 'Keyword decisions' : view === 'links' ? `Links (${links.length})` : view === 'pages' ? 'Pages' : 'Map'}</button>)}</div>
        <div className="flex flex-wrap gap-2"><label className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 dark:border-line dark:bg-raised"><Search className="h-4 w-4 text-slate-400 dark:text-muted" /><input aria-label="Search map" placeholder="Find a topic or page…" value={query} onChange={event => setQuery(event.target.value)} className="w-40 bg-transparent py-2 text-sm text-slate-900 outline-none placeholder:text-slate-400 dark:text-text dark:placeholder:text-muted/70" /></label><select aria-label="Filter pages" value={filter} onChange={event => setFilter(event.target.value)} className="rounded-lg border border-slate-200 bg-white px-2 text-sm text-slate-700 dark:border-line dark:bg-raised dark:text-text"><option value="all">All pages</option><option value="create">New pages to create</option><option value="article">Blogs</option><option value="tool">Pages and tools</option><option value="update">Existing pages</option><option value="research">Research ideas</option></select></div>
      </div>
      <div className={`grid ${selected ? 'xl:grid-cols-[minmax(0,1fr)_340px]' : ''}`}>
        <div id="map-panel" role="tabpanel" aria-labelledby={`map-tab-${tab}`} className={`min-w-0 p-4 sm:p-6 ${tab === 'map' ? 'bg-slate-50/70 dark:bg-blueprint-deep dark:[background-image:linear-gradient(rgba(30,58,95,0.08)_1px,transparent_1px),linear-gradient(90deg,rgba(30,58,95,0.08)_1px,transparent_1px)] dark:[background-size:28px_28px]' : 'bg-slate-50/70 dark:bg-blueprint-deep/60'}`}>
          <div className="mb-5 rounded-xl border border-sky-200 bg-sky-50 p-4 dark:border-line dark:bg-raised"><h4 className="font-display text-sm font-semibold text-slate-900 dark:text-text">{tabHelp[tab].title}</h4><p className="mt-1 text-sm leading-relaxed text-slate-600 dark:text-muted">{tabHelp[tab].text}</p></div>
          {tab === 'map' && <>
            <div className="mb-5 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-xs text-slate-500 dark:text-muted" aria-label="Map legend">
              <span className="flex items-center gap-2"><span className="h-3 w-3 rounded-full bg-sky-400 dark:bg-site-sky" aria-hidden />Existing page</span>
              <span className="flex items-center gap-2"><span className="h-3 w-3 rounded-full border-2 border-dashed border-amber-400 dark:border-signal-amber" aria-hidden />To create</span>
              <span className="flex items-center gap-2"><span className="h-3 w-3 rounded-full bg-emerald-400 dark:bg-built-green" aria-hidden />Built</span>
            </div>
            {mapping.master_hub?.target_keyword && matches(mapping.master_hub) && <div className="mx-auto max-w-sm"><div className="mb-2 flex items-center justify-center gap-2 text-xs font-semibold uppercase tracking-wider text-sky-700 dark:text-site-sky"><Network className="h-4 w-4" />Main hub</div>{card(mapping.master_hub)}</div>}
            {groups.length > 0 && <><div className="flex justify-center py-3 text-slate-300 dark:text-line"><ArrowDown className="h-6 w-6" /></div><p className="mb-4 text-center text-xs text-slate-500 dark:text-muted">Topic groups organize the pages below. Open Links for the actual page connections.</p><div className="grid items-start gap-4 md:grid-cols-2 2xl:grid-cols-3">{groups.map(([name, members], index) => { const filtered = members.filter(matches); return filtered.length > 0 && <div key={name} className={`rounded-xl border border-slate-200 border-t-4 bg-white p-3 dark:border-line dark:bg-raised ${groupAccents[index % groupAccents.length]}`}><div className="mb-3 flex items-center justify-between gap-2"><h4 className="font-display text-sm font-bold text-slate-900 dark:text-text">{name}</h4><span className="font-mono text-xs text-slate-500 dark:text-muted">{filtered.length}</span></div><div className="space-y-2">{filtered.map(card)}</div></div> })}</div></>}
            {!mapping.spokes?.length && <p className="py-8 text-center text-sm text-slate-500 dark:text-muted">No distinct supporting pages were identified. Add evidence for more reader tasks and rebuild.</p>}
            {pages.length > 0 && visible.length === 0 && <p className="py-8 text-center text-sm text-slate-500 dark:text-muted">No pages match these filters.</p>}
          </>}
          {tab === 'pages' && <div className="space-y-2">{visible.map(page => <div key={page.target_keyword} className="flex flex-wrap items-start justify-between gap-4 rounded-xl border border-slate-200 bg-white p-4 dark:border-line dark:bg-panel"><div className="min-w-0 flex-1 basis-48"><p className={`font-mono text-xs font-medium ${isExistingPage(page) ? 'text-sky-700 dark:text-site-sky' : 'text-amber-700 dark:text-signal-amber'}`}>{isExistingPage(page) ? 'Existing page · improve in place' : 'New page'} · {isToolPage(page) ? 'Tool' : pageEditor(page) === 'blog' ? 'Blog' : 'Page'}</p><h4 className="mt-1 text-sm font-semibold text-slate-900 dark:text-text">{label(page)}</h4><p className="mt-1 text-xs text-slate-500 dark:text-muted">{page.search_intent || page.content_brief}</p><p className="mt-2 break-all font-mono text-xs text-slate-500 dark:text-muted">{page.existing_url || page.slug}</p><details className="mt-3 text-xs"><summary className="cursor-pointer font-medium text-sky-700 dark:text-site-sky">{pageKeywords(page).length} keywords covered</summary><p className="mt-2 font-mono text-slate-500 dark:text-muted">Main keyword: {page.target_keyword}</p><div className="mt-2 flex flex-wrap gap-1.5">{page.targeted_keywords?.map(keyword => <span key={keyword} className="rounded bg-slate-100 px-2 py-1 font-mono dark:bg-raised dark:text-muted">{keyword}</span>)}</div></details></div><div className="flex flex-wrap gap-2"><Button size="sm" variant="secondary" onClick={() => selectPage(page)} aria-label={`View brief for ${label(page)}`}>View brief</Button><Button size="sm" variant="secondary" onClick={() => onOpen(page)} aria-label={`${pageActionLabel(page)}: ${label(page)}`}>{pageActionLabel(page)}<ArrowRight className="h-4 w-4" /></Button></div></div>)}{!visible.length && <p className="p-6 text-sm text-slate-500 dark:text-muted">No pages match these filters.</p>}</div>}
          {tab === 'links' && <div className="space-y-3"><p className="text-sm text-slate-500 dark:text-muted">Directed links to implement in relevant page content. Suggested anchors can be adapted naturally.</p><Button variant="secondary" onClick={() => downloadText('internal-links.csv', ['Source URL,Target URL,Anchor text,Relationship', ...links.map(link => [link.source_url, link.target_url, link.anchor_text, link.relationship].map(value => `"${value.replace(/"/g, '""')}"`).join(','))].join('\n'))}><Download className="h-4 w-4" />Export links</Button>{visibleLinks.map(link => <div key={`${link.source}-${link.target}`} className="rounded-xl border border-slate-200 bg-white p-4 text-sm dark:border-line dark:bg-panel"><p className="break-words font-medium text-slate-900 dark:text-text">{link.source_keyword}<ArrowRight className="mx-2 inline h-4 w-4 text-slate-400 dark:text-muted" /><button type="button" onClick={() => selectTarget(link.target_keyword)} className="text-sky-700 underline underline-offset-2 dark:text-site-sky">{link.target_keyword}</button></p><p className="mt-2 break-all font-mono text-xs text-slate-500 dark:text-muted">{link.source_url} → {link.target_url}</p><p className="mt-2 font-mono text-xs text-slate-500 dark:text-muted">Anchor: {link.anchor_text} · {link.relationship}</p><p className="mt-1 text-xs text-slate-500 dark:text-muted">{link.reason}</p></div>)}{!visibleLinks.length && <p className="p-6 text-sm text-slate-500 dark:text-muted">No links match these filters.</p>}</div>}
          {tab === 'keywords' && <div className="space-y-2"><p className="mb-4 text-sm text-slate-500 dark:text-muted">Every keyword gets one destination or a documented reason for exclusion.</p>{(mapping.keyword_assignments || []).filter(item => `${item.keyword} ${item.assigned_to || ''}`.toLowerCase().includes(query.toLowerCase()) && (filter === 'all' || visible.some(page => page.target_keyword === item.assigned_to))).map(item => <div key={item.keyword} className="rounded-xl border border-slate-200 bg-white p-4 text-sm dark:border-line dark:bg-panel"><div className="flex flex-wrap justify-between gap-2"><strong className="font-mono text-slate-900 dark:text-text">{item.keyword}</strong><span className="text-xs text-slate-500 dark:text-muted">{{ page_target: 'Main keyword', supporting: 'Include on page', discard: 'Not included' }[item.disposition]}</span></div>{item.assigned_to && <button type="button" onClick={() => selectTarget(item.assigned_to!)} className="mt-1 font-mono text-xs text-sky-700 underline dark:text-site-sky">{item.assigned_to} {item.placement ? `· ${item.placement}` : ''}</button>}<p className="mt-2 text-xs text-slate-500 dark:text-muted">{item.reason}</p></div>)}{!mapping.keyword_assignments?.length && <p className="text-sm text-slate-500 dark:text-muted">This saved plan has no recorded keyword decisions.</p>}</div>}
        </div>
        {selected && <aside ref={briefRef} aria-label="Page brief" className="border-t border-slate-200 bg-white p-5 dark:border-line dark:bg-panel xl:border-l xl:border-t-0">
          <div className="xl:sticky xl:top-6 xl:max-h-[calc(100vh-3rem)] xl:overflow-y-auto">
          <div className="flex items-start justify-between gap-3"><p className="text-xs font-bold uppercase tracking-wider text-slate-400 dark:text-muted">Page brief</p><button type="button" aria-label="Close page brief" onClick={() => setSelectedTarget(null)} className="rounded p-1 text-slate-500 hover:bg-slate-100 dark:text-muted dark:hover:bg-raised"><X className="h-4 w-4" /></button></div>
          <h4 className="mt-3 font-display text-lg font-bold text-slate-950 dark:text-text">{label(selected)}</h4><p className="mt-1 break-all font-mono text-xs text-slate-500 dark:text-muted">{selected.existing_url || selected.slug || '/'}</p>
          <p className={`mt-3 font-mono text-xs font-medium ${isExistingPage(selected) ? 'text-sky-700 dark:text-site-sky' : 'text-amber-700 dark:text-signal-amber'}`}>{evidence(selected)} · {isExistingPage(selected) ? 'Already on your site' : selected.action === 'create' ? (isToolPage(selected) ? 'Create tool' : 'Create page') : 'Review page'}</p>
          {safeUrl(selected.existing_url) && <a href={safeUrl(selected.existing_url)} target="_blank" rel="noreferrer" className="mt-2 block break-all font-mono text-xs text-sky-700 underline dark:text-site-sky">Open existing page ↗</a>}
          <div className="mt-4 space-y-2"><Button className="w-full" onClick={() => onOpen(selected)}>{pageActionLabel(selected)}<ArrowRight className="h-4 w-4" /></Button><p className="text-xs leading-relaxed text-slate-500 dark:text-muted">{isExistingPage(selected) ? 'This page already exists. The editor will receive its current URL and instructions to improve it in place.' : `Opens ${isToolPage(selected) ? 'Build Page' : pageEditor(selected) === 'blog' ? 'Blog Writer' : 'the page builder'} with this keyword and brief ready to use.`}</p></div>
          <div className="mt-5 space-y-5 text-sm">
            <div><p className="mb-1 font-semibold text-slate-900 dark:text-text">Reader task</p><p className="text-slate-500 dark:text-muted">{selected.reader_outcome || selected.search_intent || selected.content_brief || 'Review the purpose of this page before writing.'}</p></div>
            {selected.user_problem && <div><p className="mb-1 font-semibold text-slate-900 dark:text-text">User problem</p><p className="text-slate-500 dark:text-muted">{selected.user_problem}</p></div>}
            {selected.entity_topic && <div><p className="mb-1 font-semibold text-slate-900 dark:text-text">Entity/topic</p><p className="text-slate-500 dark:text-muted">{selected.entity_topic}</p></div>}
            <div><p className="mb-1 font-semibold text-slate-900 dark:text-text">Content requirements</p><p className="text-slate-500 dark:text-muted">Enough content to completely satisfy this page’s unique intent. No fixed word count.</p>{!!selected.content_requirements?.length && <ul className="mt-2 list-disc space-y-1 pl-4 text-slate-500 dark:text-muted">{selected.content_requirements.map(requirement => <li key={requirement}>{requirement}</li>)}</ul>}</div>
            {selected.url_decision_reason && <div><p className="mb-1 font-semibold text-slate-900 dark:text-text">URL decision</p><p className="text-slate-500 dark:text-muted">{selected.url_decision_reason}</p></div>}
            {selected.unique_page_value && <div><p className="mb-1 font-semibold text-slate-900 dark:text-text">Unique page value</p><p className="text-slate-500 dark:text-muted">{selected.unique_page_value}</p></div>}
            {selected.content_brief && <div><p className="mb-1 font-semibold text-slate-900 dark:text-text">Coverage</p><p className="leading-relaxed text-slate-500 dark:text-muted">{selected.content_brief}</p></div>}
            {!!selected.scope_out?.length && <div><p className="mb-1 font-semibold text-slate-900 dark:text-text">Leave to other pages</p><ul className="list-disc space-y-1 pl-4 text-slate-500 dark:text-muted">{selected.scope_out.map(scope => <li key={scope}>{scope}</li>)}</ul></div>}
            <div><p className="mb-1 font-semibold text-slate-900 dark:text-text">Primary keyword</p><p className="font-mono text-slate-800 dark:text-text">{selected.target_keyword}</p><p className="mt-2 font-mono text-xs text-slate-400 dark:text-muted">Volume: {selected.search_volume?.toLocaleString() ?? 'Unknown'} · Difficulty: {selected.difficulty ?? 'Unknown'}</p></div>
            {selected.evidence_type === 'editorial_proposal' && <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs leading-relaxed text-amber-800 dark:border-signal-amber/30 dark:bg-signal-amber/10 dark:text-signal-amber">Proposed from: {selected.support_phrase || 'site context'}. {selected.evidence_rationale || 'Confirm relevance and demand with research.'} No measured demand is implied.</div>}
            {!!selected.targeted_keywords?.length && <div><p className="mb-2 font-semibold text-slate-900 dark:text-text">Supporting keywords</p><div className="flex flex-wrap gap-1.5">{selected.targeted_keywords.map(keyword => <span key={keyword} className="rounded bg-slate-100 px-2 py-1 font-mono text-xs text-slate-600 dark:bg-raised dark:text-muted">{keyword}</span>)}</div></div>}
            {!!selected.h2_sections?.length && <div><p className="mb-2 font-semibold text-slate-900 dark:text-text">Section outline</p><ol className="list-decimal space-y-2 pl-4 text-slate-500 dark:text-muted">{selected.h2_sections.map((section, index) => <li key={index}><span className="font-medium text-slate-700 dark:text-text">{section.h2_heading}</span>{section.section_definition && <p className="mt-0.5 text-xs">{section.section_definition}</p>}{!!section.targeted_keywords_placed_here?.length && <p className="mt-1 font-mono text-xs">Include: {section.targeted_keywords_placed_here.join(', ')}</p>}</li>)}</ol></div>}
            {!!selected.faq_schema_questions?.length && <div><p className="mb-2 font-semibold text-slate-900 dark:text-text">Questions to answer</p>{selected.faq_schema_questions.map((faq, index) => <div key={index} className="mt-1 text-slate-500 dark:text-muted"><p>{faq.question}</p>{!!faq.targeted_keywords_placed_here?.length && <p className="mt-1 font-mono text-xs">Include: {faq.targeted_keywords_placed_here.join(', ')}</p>}</div>)}</div>}
            {!!selected.tool_functions?.length && <div><p className="mb-2 font-semibold text-slate-900 dark:text-text">Tool requirements</p><ul className="list-disc pl-4 text-slate-500 dark:text-muted">{selected.tool_functions.map(item => <li key={item}>{item}</li>)}</ul></div>}
            <div><p className="mb-2 flex items-center gap-2 font-semibold text-slate-900 dark:text-text"><Link2 className="h-4 w-4" />Link to</p><div className="space-y-2">{links.filter(link => link.source_keyword === selected.target_keyword).map(link => <button key={link.target} type="button" onClick={() => selectTarget(link.target_keyword)} className="block text-left font-mono text-xs text-sky-700 hover:underline dark:text-site-sky">{link.target_keyword} <span className="text-slate-400 dark:text-muted">({link.relationship})</span></button>)}</div></div>
          </div>
          </div>
        </aside>}
      </div>
    </Card>
  </section>
}
