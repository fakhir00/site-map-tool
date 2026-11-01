import { useMemo, useRef, useState } from 'react'
import { ArrowDown, ArrowRight, CheckCircle2, Download, FileText, Link2, Wrench, X } from 'lucide-react'
import { Button } from './ui/Button'
import { Card } from './ui/Card'
import { Input } from './ui/Input'
import { Badge } from './ui/Badge'
import { downloadText, isExistingPage, isToolPage, keywordCoverage, pageKeywords, pageEditor, pageActionLabel, type Mapping, type PageDetail, type MapLink } from '../lib/hubSpoke'

type Props = { mapping: Mapping; onOpen: (page: PageDetail) => void }
const tabHelp = {
  map: { title: 'See how your topics fit together', text: 'The hub is your main topic. Spokes are supporting pages grouped by topic. Select a card to read its brief, or use Create tool, Create blog or Create page to open the right editor with the plan filled in.' },
  pages: { title: 'Choose what to create or improve', text: 'Work through your content plan here. Create tool opens Build Page; Create blog opens Blog Writer; Create page opens the page builder. Pages already on your site are marked Existing page. Improve them at their current URL instead of creating duplicates.' },
  links: { title: 'Connect related pages on your site', text: 'Each arrow shows which page should link to another. Add the link within relevant content using the suggested anchor text (the clickable words). Select a destination to read its brief, or export the link list.' },
  keywords: { title: 'Understand where each keyword belongs', text: 'Main keyword is the primary topic of a page. Include on page means cover it within that page, without creating another URL. Not included means it does not need a page in this plan. Select a destination to see its brief.' },
}
const label = (page: PageDetail) => page.article_title || page.target_keyword || 'Untitled page'
const evidence = (page: PageDetail) => page.evidence_type === 'editorial_proposal' ? 'Research idea' : 'Supplied keyword'
const safeUrl = (value?: string | null) => value && /^https?:\/\//i.test(value) ? value : undefined

function fallbackLinks(pages: PageDetail[]): MapLink[] {
  return pages.flatMap(page => (page.internal_links || []).flatMap(target => {
    const other = pages.find(candidate => candidate.target_keyword === target)
    return other ? [{ source: page.id || page.target_keyword!, target: other.id || target, source_keyword: page.target_keyword!, target_keyword: target, source_url: page.existing_url || page.slug || '/', target_url: other.existing_url || other.slug || '/', anchor_text: label(other), relationship: 'related', reason: 'Link recorded in this saved plan.' }] : []
  }))
}

const truncate = (value: string, max: number) => value.length > max ? `${value.slice(0, max - 1)}…` : value

/* ------------------------------------------------------------------
   NodeGraph — hub-and-spoke technical drawing on the blueprint grid.
   Solid amber discs = existing pages. Dashed amber outlines with a
   "+" markup flag = pages to build. Faint construction-ring
   boundaries group the pillar clusters, with R/θ dimension labels.
   ------------------------------------------------------------------ */
function NodeGraph({
  hub, spokes, sectors, selectedTarget, onSelect,
}: {
  hub: PageDetail | null
  spokes: PageDetail[]
  sectors: { name: string; from: number; to: number; mid: number; count: number }[]
  selectedTarget: string | null
  onSelect: (target: string) => void
}) {
  const W = 1000, H = 640, cx = W / 2, cy = H / 2 - 14, R = 200, NODE_R = 15, HUB_R = 30
  const n = spokes.length
  const pt = (r: number, deg: number): [number, number] => {
    const rad = ((deg - 90) * Math.PI) / 180
    return [cx + r * Math.cos(rad), cy + r * Math.sin(rad)]
  }
  const degOf = (i: number) => (i / Math.max(n, 1)) * 360
  const arc = (r: number, from: number, to: number) => {
    const [x1, y1] = pt(r, from)
    const [x2, y2] = pt(r, to)
    return `M ${x1.toFixed(1)} ${y1.toFixed(1)} A ${r} ${r} 0 ${to - from > 180 ? 1 : 0} 1 ${x2.toFixed(1)} ${y2.toFixed(1)}`
  }
  const [rx, ry] = pt(R, 42)
  const hubExists = hub ? isExistingPage(hub) : false

  return (
    <div className="relative">
      <div className="pointer-events-none absolute left-4 top-3 z-10"><p className="annotation">SHEET 01 — TOPICAL ARCHITECTURE</p></div>
      <div className="pointer-events-none absolute right-4 top-3 z-10"><p className="annotation annotation--leading">SCALE — / REV A</p></div>
      <svg viewBox={`0 0 ${W} ${H}`} className="block w-full" role="img" aria-label="Hub and spoke architecture drawing">
        {/* construction crosshairs */}
        <line x1={cx} y1={16} x2={cx} y2={H - 16} stroke="rgba(147,168,196,0.18)" strokeDasharray="6 6" strokeWidth={1} />
        <line x1={16} y1={cy} x2={W - 16} y2={cy} stroke="rgba(147,168,196,0.18)" strokeDasharray="6 6" strokeWidth={1} />
        {/* radius construction ring */}
        {n > 0 && <>
          <circle cx={cx} cy={cy} r={R} fill="none" stroke="rgba(147,168,196,0.28)" strokeDasharray="3 5" strokeWidth={1} />
          <text x={rx} y={ry} textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize={10} fill="#93A8C4" stroke="#0A1628" strokeWidth={3} paintOrder="stroke">R={R}</text>
        </>}
        {/* pillar-cluster sector boundaries */}
        {sectors.map(sector => {
          const [lx, ly] = pt(R + 62, sector.mid)
          return (
            <g key={sector.name}>
              <path d={arc(R + 38, sector.from, sector.to)} fill="none" stroke="rgba(245,165,36,0.35)" strokeDasharray="2 5" strokeWidth={1.5} />
              <text x={lx} y={ly} textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize={11} fill="#93A8C4" stroke="#0A1628" strokeWidth={3} paintOrder="stroke">
                {truncate(sector.name.toUpperCase(), 26)} · {sector.count}
              </text>
            </g>
          )
        })}
        {/* spokes */}
        {spokes.map((page, i) => {
          const deg = degOf(i)
          const [x, y] = pt(R, deg)
          const exists = isExistingPage(page)
          const research = !exists && page.evidence_type === 'editorial_proposal'
          const isSelected = selectedTarget === page.target_keyword
          const status = exists ? 'existing page' : research ? 'research idea' : 'page to build'
          return (
            <g key={page.target_keyword} onClick={() => onSelect(page.target_keyword || '')} className="cursor-pointer" role="button" aria-label={`${label(page)} — ${status}`}>
              <title>{label(page)} — {status}</title>
              <line x1={cx} y1={cy} x2={x} y2={y} stroke={exists ? 'rgba(56,189,248,0.5)' : 'rgba(245,165,36,0.4)'} strokeWidth={1} strokeDasharray={exists ? undefined : '4 4'} />
              {isSelected && <circle cx={x} cy={y} r={NODE_R + 8} fill="none" stroke="#F5A524" strokeWidth={1.5} strokeDasharray="3 3" />}
              <circle
                cx={x} cy={y} r={NODE_R}
                fill={exists ? '#F5A524' : research ? 'rgba(56,189,248,0.06)' : 'rgba(245,165,36,0.07)'}
                stroke={exists ? '#F5A524' : research ? '#38BDF8' : '#F5A524'}
                strokeWidth={exists ? 0 : 2}
                strokeDasharray={exists ? undefined : '5 4'}
              />
              {exists
                ? <text x={x} y={y + 3.5} textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize={10} fontWeight={600} fill="#0A1628">{String(i + 1).padStart(2, '0')}</text>
                : <g>
                    <circle cx={x + 11} cy={y - 11} r={7} fill="#F5A524" />
                    <text x={x + 11} y={y - 7.5} textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize={10} fontWeight={700} fill="#0A1628">+</text>
                  </g>}
              <text x={x} y={y + NODE_R + 15} textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize={9} fill="#93A8C4" stroke="#0A1628" strokeWidth={3} paintOrder="stroke">θ={Math.round(deg)}°</text>
            </g>
          )
        })}
        {/* hub */}
        {hub && (
          <g onClick={() => onSelect(hub.target_keyword || '')} className="cursor-pointer" role="button" aria-label={`Main hub — ${label(hub)}`}>
            <title>{label(hub)} — main hub</title>
            {selectedTarget === hub.target_keyword && <circle cx={cx} cy={cy} r={HUB_R + 10} fill="none" stroke="#F5A524" strokeWidth={1.5} strokeDasharray="3 3" />}
            <circle
              cx={cx} cy={cy} r={HUB_R}
              fill={hubExists ? '#F5A524' : 'rgba(245,165,36,0.07)'}
              stroke="#F5A524" strokeWidth={hubExists ? 0 : 2.5} strokeDasharray={hubExists ? undefined : '6 4'}
            />
            {hubExists
              ? <text x={cx} y={cy + 5} textAnchor="middle" fontFamily="Space Grotesk, sans-serif" fontSize={13} fontWeight={700} fill="#0A1628">HUB</text>
              : <g>
                  <text x={cx} y={cy + 5} textAnchor="middle" fontFamily="Space Grotesk, sans-serif" fontSize={13} fontWeight={700} fill="#F5A524">HUB</text>
                  <circle cx={cx + 22} cy={cy - 22} r={8} fill="#F5A524" />
                  <text x={cx + 22} y={cy - 18} textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize={11} fontWeight={700} fill="#0A1628">+</text>
                </g>}
            <text x={cx} y={cy + HUB_R + 20} textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize={12} fill="#EAF2FB" stroke="#0A1628" strokeWidth={4} paintOrder="stroke">
              {truncate((hub.target_keyword || '').toUpperCase(), 34)}
            </text>
          </g>
        )}
      </svg>
      <div className="flex flex-wrap items-center gap-x-8 gap-y-2 border-t border-line px-4 py-3">
        <span className="flex items-center gap-2 font-mono text-[11px] text-muted"><span className="inline-block h-3 w-3 rounded-full bg-amber" /> EXISTING PAGE</span>
        <span className="flex items-center gap-2 font-mono text-[11px] text-muted"><span className="inline-block h-3 w-3 rounded-full border-2 border-dashed border-amber bg-amber/10" /> TO BUILD</span>
        <span className="flex items-center gap-2 font-mono text-[11px] text-muted"><span className="inline-block h-3 w-3 rounded-full border-2 border-dashed border-sky bg-sky/10" /> RESEARCH IDEA</span>
        <span className="ml-auto font-mono text-[11px] text-muted">θ = SPOKE ANGLE · R = CLUSTER RADIUS</span>
      </div>
    </div>
  )
}

function statusStamp(page: PageDetail) {
  if (isExistingPage(page)) return <span className="stamp stamp-green">Existing</span>
  if (page.evidence_type === 'editorial_proposal') return <span className="stamp stamp-muted">Research</span>
  return <span className="stamp stamp-amber">P0 · New</span>
}

export function TopicalAuthorityMap({ mapping, onOpen }: Props) {
  const [tab, setTab] = useState<'map' | 'pages' | 'links' | 'keywords'>('map')
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const [selectedTarget, setSelectedTarget] = useState<string | null>(mapping.master_hub?.target_keyword || null)
  const briefRef = useRef<HTMLElement>(null)
  const pages = useMemo(() => [mapping.master_hub, ...(mapping.spokes || [])].filter((page): page is PageDetail => Boolean(page?.target_keyword)), [mapping])
  const coverage = useMemo(() => keywordCoverage(mapping), [mapping])
  const selected = pages.find(page => page.target_keyword === selectedTarget)
  const researchIncomplete = mapping.authority_coverage?.discovery_status === 'unavailable'
  const links = mapping.link_plan || fallbackLinks(pages)
  const matches = (page: PageDetail) => `${label(page)} ${page.target_keyword} ${page.spoke_category || ''} ${(page.targeted_keywords || []).join(' ')}`.toLowerCase().includes(query.toLowerCase()) && (filter === 'all' || (filter === 'research' ? page.evidence_type === 'editorial_proposal' : filter === 'update' ? isExistingPage(page) : filter === 'create' ? !isExistingPage(page) && page.action === 'create' : filter === 'article' ? pageEditor(page) === 'blog' : pageEditor(page) === 'page'))
  const visible = pages.filter(matches)
  const hubKey = mapping.master_hub?.target_keyword
  const graphSpokes = useMemo(() => visible.filter(page => page.target_keyword !== hubKey).slice(0, 48), [visible, hubKey])
  const graphOverflow = visible.filter(page => page.target_keyword !== hubKey).length - graphSpokes.length
  const sectors = useMemo(() => {
    const n = graphSpokes.length
    if (!n) return []
    const keyOf = (page: PageDetail) => page.spoke_category || 'Supporting topics'
    const out: { name: string; from: number; to: number; mid: number; count: number }[] = []
    let start = 0
    for (let i = 1; i <= n; i++) {
      if (i === n || keyOf(graphSpokes[i]) !== keyOf(graphSpokes[start])) {
        const step = 360 / n
        out.push({ name: keyOf(graphSpokes[start]), from: (start - 0.45) * step, to: (i - 1 + 0.45) * step, mid: ((start + i - 1) / 2) * step, count: i - start })
        start = i
      }
    }
    return out
  }, [graphSpokes])
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

  const existingCount = pages.filter(isExistingPage).length
  const authority = mapping.authority_coverage
  const plateExisting = authority ? authority.existing_spokes : existingCount
  const plateNew = authority ? authority.new_spokes : pages.length - existingCount
  const plateTotal = authority ? authority.actual_spokes : pages.length
  const coveragePct = coverage.total > 0 ? Math.round((coverage.used / coverage.total) * 100) : 0

  const card = (page: PageDetail) => (
    <div key={page.target_keyword} className="space-y-2"><button type="button" aria-pressed={selectedTarget === page.target_keyword} onClick={() => selectPage(page)} className={`w-full rounded-xl border p-4 text-left transition ${selectedTarget === page.target_keyword ? 'border-amber bg-amber/5 shadow-[0_0_0_1px_#F5A524]' : 'border-line bg-panel hover:border-amber/50'}`}>
      <span className="mb-2 flex items-center justify-between gap-2 font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-muted">
        <span className="flex items-center gap-1.5">{isToolPage(page) ? <Wrench className="h-3.5 w-3.5" /> : <FileText className="h-3.5 w-3.5" />}{isToolPage(page) ? 'Tool' : pageEditor(page) === 'blog' ? 'Blog' : 'Page'}</span>
        <span className={isExistingPage(page) ? 'text-sky' : 'text-amber'}>{isExistingPage(page) ? 'Existing page' : page.action === 'create' ? 'New page' : 'Review page'}</span>
      </span>
      <span className="block font-display text-sm font-semibold leading-5 text-text">{label(page)}</span>
      <span className="mt-1 block break-all font-mono text-[11px] text-muted">{page.existing_url || page.slug || '/'}</span>
      <span className="mt-2 block font-mono text-[11px] text-muted">{pageKeywords(page).length} keywords covered · {(page.targeted_keywords || []).length} supporting</span>
      <span className="mt-3"><Badge variant={page.evidence_type === 'editorial_proposal' ? 'amber' : 'slate'}>{evidence(page)}</Badge></span>
    </button><Button size="sm" variant="secondary" className="w-full" onClick={() => onOpen(page)}>{pageActionLabel(page)}<ArrowRight className="h-4 w-4" /></Button></div>
  )

  return <section className="space-y-4" aria-label="Topical authority map">
    {/* drafting-sheet header */}
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <p className="annotation">▸ TOPICAL AUTHORITY — DRAFT 01</p>
        <h3 className="mt-2 font-display text-2xl font-bold tracking-tight text-text">Architecture drawing</h3>
        <p className="mt-1 text-sm text-muted">Select a node to pull its spec sheet, or draft it straight into the editor.</p>
      </div>
      <Button variant="secondary" onClick={() => downloadText('topical-authority-map.json', JSON.stringify(mapping, null, 2))}><Download className="h-4 w-4" />Export map</Button>
    </div>

    {/* stamped spec-plate arithmetic strip — all values live from the mapping */}
    <div className="spec-plate" aria-label="Site coverage summary">
      <div className="grid grid-cols-3 gap-4">
        <div><p className="spec-label">Existing pages</p><p className="spec-value text-sky">{plateExisting.toLocaleString()}</p></div>
        <div><p className="spec-label">Pages to build</p><p className="spec-value text-amber">{plateNew.toLocaleString()}</p></div>
        <div><p className="spec-label">Total planned</p><p className="spec-value">{plateTotal.toLocaleString()}</p></div>
      </div>
      <p className="annotation mt-3">Your site: {plateExisting.toLocaleString()} pages → {plateNew.toLocaleString()} missing pages drafted · {plateTotal.toLocaleString()} total</p>
    </div>

    {/* keyword coverage as a drafting instrument */}
    <div className="rounded-xl border border-line bg-panel p-4" aria-label="Keyword coverage">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-display text-sm font-semibold text-text">{coverage.used.toLocaleString()} of {coverage.total.toLocaleString()} keywords drafted · {coveragePct}%</p>
        <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted">Coverage gauge</p>
      </div>
      <div className="dashed-amber mt-3 h-3 rounded-full p-[2px]" aria-hidden="true">
        <div className="h-full rounded-full bg-amber transition-all" style={{ width: `${coveragePct}%` }} />
      </div>
      <p className="mt-2 text-xs text-muted">{coverage.supporting.toLocaleString()} supporting keywords are included within page content. Related phrases can share a page; each page covers one distinct reader task.</p>
      {coverage.excluded > 0 && <button type="button" onClick={() => { setTab('keywords'); setQuery(''); setFilter('all') }} className="mt-2 font-mono text-xs font-medium text-amber underline underline-offset-2">{coverage.excluded} keywords excluded · Review keyword decisions</button>}
      {coverage.unassigned > 0 && <p className="annotation mt-2 !text-amber">{coverage.unassigned} {coverage.unassigned === 1 ? 'keyword has' : 'keywords have'} no recorded placement in this saved map. Rebuild to review coverage.</p>}
    </div>

    {/* intent review as a drafted check plate */}
    <Card className="p-4">
      <div className="flex flex-wrap items-center gap-3 text-sm font-semibold text-text">
        <CheckCircle2 className={`h-4 w-4 ${!researchIncomplete && mapping._semantic_audit_status === 'passed' ? 'text-green' : 'text-amber'}`} />
        <span className="font-mono text-xs uppercase tracking-[0.14em]">{researchIncomplete ? 'Topic research incomplete' : mapping._semantic_audit_status === 'passed' ? 'Intent review passed' : 'Intent review needed'}</span>
        {!researchIncomplete && mapping._semantic_audit_status === 'passed'
          ? <span className="stamp stamp-green">Pass</span>
          : <span className="stamp stamp-amber">Check</span>}
        <span className="font-normal text-muted">{researchIncomplete ? '· Partial map from supplied keywords' : '· Editorial plan; validate demand before publishing'}</span>
      </div>
      {mapping.authority_coverage && <div className="mt-3 space-y-1 text-sm"><p className="font-semibold text-text">{mapping.spokes?.length ?? mapping.authority_coverage.actual_spokes} spokes</p><p className="text-muted">There is no fixed number of pages. Add a page only when it answers a different question or helps the reader do a different task.</p>{researchIncomplete && <p role="status" className="text-amber">Topic research did not finish. Use Build topical map above to retry. Zero spokes here does not mean your site has no useful supporting topics.</p>}</div>}
      {mapping.map_warnings?.map(warning => <p key={warning} className="annotation mt-2 !text-amber">{warning}</p>)}
      {mapping._planning_thought && <details className="mt-3 text-sm"><summary className="cursor-pointer font-mono text-xs uppercase tracking-[0.14em] text-muted">Planning rationale</summary><p className="mt-2 leading-relaxed text-muted">{mapping._planning_thought}</p></details>}
      {!!mapping.intent_consolidations?.length && <details className="mt-3 text-sm"><summary className="cursor-pointer font-semibold text-text">Consolidated intent overlaps ({mapping.intent_consolidations.length})</summary><p className="mt-2 text-muted">These keywords share an existing task. Keep them on the assigned page instead of creating extra URLs.</p><ul className="mt-3 space-y-3">{mapping.intent_consolidations.map(item => <li key={item.from_keyword} className="break-words text-text"><p className="font-medium">{item.from_keyword} → {item.to_keyword}</p><p className="mt-1 text-xs text-muted">{item.risk_type === 'doorway' ? 'Near-duplicate page risk' : 'Same user need'}: {item.reason}</p></li>)}</ul></details>}
    </Card>

    {/* drawing board: tabs + graph/list + spec sheet */}
    <Card className="overflow-hidden p-0">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-4">
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="Map views">{(['pages', 'map', 'links', 'keywords'] as const).map(view => <button key={view} type="button" id={`map-tab-${view}`} role="tab" tabIndex={tab === view ? 0 : -1} aria-controls="map-panel" aria-selected={tab === view} onKeyDown={event => {
          const views = ['pages', 'map', 'links', 'keywords'] as const
          const index = views.indexOf(view)
          const next = event.key === 'ArrowRight' ? (index + 1) % views.length : event.key === 'ArrowLeft' ? (index + views.length - 1) % views.length : event.key === 'Home' ? 0 : event.key === 'End' ? views.length - 1 : -1
          if (next >= 0) { event.preventDefault(); setTab(views[next]); document.getElementById(`map-tab-${views[next]}`)?.focus() }
        }} onClick={() => setTab(view)} className={`rounded-lg px-3 py-2 font-mono text-xs font-semibold uppercase tracking-[0.14em] ${tab === view ? 'bg-amber text-ink' : 'text-muted hover:bg-raised hover:text-text'}`}>{view === 'keywords' ? 'Keyword decisions' : view === 'links' ? `Links (${links.length})` : view === 'pages' ? 'Pages' : 'Map'}</button>)}</div>
        <div className="flex flex-wrap gap-2">
          <label className="flex items-center gap-2"><span className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted">▸ Find</span><Input aria-label="Search map" placeholder="Find a topic or page…" value={query} onChange={event => setQuery(event.target.value)} className="w-44" /></label>
          <label className="flex items-center gap-2"><span className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted">▸ Filter</span><select aria-label="Filter pages" value={filter} onChange={event => setFilter(event.target.value)} className="h-10 rounded-lg border border-line bg-ink px-2 font-mono text-sm text-text focus:border-amber/70 focus:outline-none"><option value="all">All pages</option><option value="create">New pages to create</option><option value="article">Blogs</option><option value="tool">Pages and tools</option><option value="update">Existing pages</option><option value="research">Research ideas</option></select></label>
        </div>
      </div>
      <div className={`grid ${selected ? 'xl:grid-cols-[minmax(0,1fr)_360px]' : ''}`}>
        <div id="map-panel" role="tabpanel" aria-labelledby={`map-tab-${tab}`} className="bg-blueprint min-w-0 p-4 sm:p-6">
          <div className="mb-5"><p className="annotation">{tabHelp[tab].title}</p><p className="mt-1 pl-4 text-sm leading-relaxed text-muted">{tabHelp[tab].text}</p></div>
          {tab === 'map' && <>
            {mapping.master_hub?.target_keyword && matches(mapping.master_hub)
              ? <div className="overflow-hidden rounded-xl border border-line bg-ink/60">
                  <NodeGraph hub={mapping.master_hub} spokes={graphSpokes} sectors={sectors} selectedTarget={selectedTarget} onSelect={selectTarget} />
                  {graphOverflow > 0 && <p className="annotation border-t border-line px-4 py-3">+{graphOverflow} more pages off-sheet — narrow the search to inspect them.</p>}
                </div>
              : <div className="rounded-xl border-2 border-dashed border-line bg-ink/60 p-10 text-center">
                  <div className="node-missing mx-auto h-16 w-16"><span className="text-2xl">+</span></div>
                  <p className="annotation mx-auto mt-4 max-w-xs">No distinct supporting pages were identified. Add evidence for more reader tasks and rebuild.</p>
                </div>}
            {pages.length > 0 && visible.length === 0 && <p className="annotation py-8 text-center">No pages match these filters.</p>}
            {groups.length > 0 && <div className="mt-6 grid items-start gap-4 md:grid-cols-2 2xl:grid-cols-3">{groups.map(([name, members]) => { const filtered = members.filter(matches); return filtered.length > 0 && <div key={name} className="rounded-xl border border-line bg-panel p-3"><div className="mb-3 flex items-center justify-between gap-2 border-b border-dashed border-line pb-2"><h4 className="font-mono text-xs font-bold uppercase tracking-[0.14em] text-text">{name}</h4><span className="font-mono text-xs text-muted">{filtered.length}</span></div><div className="space-y-2">{filtered.map(card)}</div></div> })}</div>}
          </>}
          {tab === 'pages' && <div className="space-y-2">{visible.map(page => <div key={page.target_keyword} className="flex flex-wrap items-start justify-between gap-4 rounded-xl border border-line bg-panel p-4"><div className="min-w-0 flex-1 basis-48"><p className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-amber">{isExistingPage(page) ? 'Existing page · improve in place' : 'New page'} · {isToolPage(page) ? 'Tool' : pageEditor(page) === 'blog' ? 'Blog' : 'Page'}</p><h4 className="mt-1 font-display text-sm font-semibold text-text">{label(page)}</h4><p className="mt-1 text-xs text-muted">{page.search_intent || page.content_brief}</p><p className="mt-2 break-all font-mono text-xs text-muted">{page.existing_url || page.slug}</p><details className="mt-3 text-xs"><summary className="cursor-pointer font-mono text-[11px] uppercase tracking-[0.14em] text-amber">{pageKeywords(page).length} keywords covered</summary><p className="mt-2 text-muted">Main keyword: {page.target_keyword}</p><div className="mt-2 flex flex-wrap gap-1.5">{page.targeted_keywords?.map(keyword => <span key={keyword} className="rounded bg-raised px-2 py-1 font-mono text-[11px] text-muted">{keyword}</span>)}</div></details></div><div className="flex flex-wrap gap-2"><Button size="sm" variant="secondary" onClick={() => selectPage(page)} aria-label={`View brief for ${label(page)}`}>View brief</Button><Button size="sm" onClick={() => onOpen(page)} aria-label={`${pageActionLabel(page)}: ${label(page)}`}>{pageActionLabel(page)}<ArrowRight className="h-4 w-4" /></Button></div></div>)}{!visible.length && <p className="annotation p-6">No pages match these filters.</p>}</div>}
          {tab === 'links' && <div className="space-y-3"><p className="annotation">Directed links to implement in relevant page content. Suggested anchors can be adapted naturally.</p><Button variant="secondary" onClick={() => downloadText('internal-links.csv', ['Source URL,Target URL,Anchor text,Relationship', ...links.map(link => [link.source_url, link.target_url, link.anchor_text, link.relationship].map(value => `"${value.replace(/"/g, '""')}"`).join(','))].join('\n'))}><Download className="h-4 w-4" />Export links</Button>{visibleLinks.map(link => <div key={`${link.source}-${link.target}`} className="rounded-xl border border-line bg-panel p-4 text-sm"><p className="break-words font-medium text-text">{link.source_keyword}<ArrowRight className="mx-2 inline h-4 w-4 text-amber" /><button type="button" onClick={() => selectTarget(link.target_keyword)} className="text-amber underline underline-offset-2">{link.target_keyword}</button></p><p className="mt-2 break-all font-mono text-xs text-muted">{link.source_url} → {link.target_url}</p><p className="mt-2 text-xs text-muted">Anchor: {link.anchor_text} · {link.reason}</p></div>)}{!visibleLinks.length && <p className="annotation p-6">No links match these filters.</p>}</div>}
          {tab === 'keywords' && <div className="space-y-2"><p className="annotation mb-4">Every keyword gets one destination or a documented reason for exclusion.</p>{(mapping.keyword_assignments || []).filter(item => `${item.keyword} ${item.assigned_to || ''}`.toLowerCase().includes(query.toLowerCase()) && (filter === 'all' || visible.some(page => page.target_keyword === item.assigned_to))).map(item => <div key={item.keyword} className="rounded-xl border border-line bg-panel p-4 text-sm"><div className="flex flex-wrap justify-between gap-2"><strong className="text-text">{item.keyword}</strong><Badge variant={item.disposition === 'page_target' ? 'amber' : item.disposition === 'supporting' ? 'cyan' : 'slate'}>{{ page_target: 'Main keyword', supporting: 'Include on page', discard: 'Not included' }[item.disposition]}</Badge></div>{item.assigned_to && <button type="button" onClick={() => selectTarget(item.assigned_to!)} className="mt-1 font-mono text-xs text-amber underline underline-offset-2">{item.assigned_to} {item.placement ? `· ${item.placement}` : ''}</button>}<p className="mt-2 text-xs text-muted">{item.reason}</p></div>)}{!mapping.keyword_assignments?.length && <p className="annotation">This saved plan has no recorded keyword decisions.</p>}</div>}
        </div>

        {/* drafted spec sheet for the selected node */}
        {selected && <aside ref={briefRef} aria-label="Page brief" className="border-t border-line bg-panel p-5 xl:border-l xl:border-t-0">
          <div className="xl:sticky xl:top-6 xl:max-h-[calc(100vh-3rem)] xl:overflow-y-auto">
            <div className="flex items-start justify-between gap-3">
              <p className="annotation">SPEC SHEET — NODE {pages.findIndex(page => page.target_keyword === selectedTarget) + 1}/{pages.length}</p>
              <button type="button" aria-label="Close page brief" onClick={() => setSelectedTarget(null)} className="rounded p-1 text-muted hover:bg-raised hover:text-text"><X className="h-4 w-4" /></button>
            </div>
            <div className="mt-3">{statusStamp(selected)}</div>
            <h4 className="mt-3 font-display text-lg font-bold text-text">{label(selected)}</h4>
            <p className="mt-1 break-all font-mono text-xs text-muted">{selected.existing_url || selected.slug || '/'}</p>
            <p className="mt-3 font-mono text-[11px] uppercase tracking-[0.14em] text-amber">{evidence(selected)} · {isExistingPage(selected) ? 'Already on your site' : selected.action === 'create' ? (isToolPage(selected) ? 'Create tool' : 'Create page') : 'Review page'}</p>
            {safeUrl(selected.existing_url) && <a href={safeUrl(selected.existing_url)} target="_blank" rel="noreferrer" className="mt-2 block break-all font-mono text-xs text-amber underline underline-offset-2">Open existing page ↗</a>}
            <div className="mt-4 space-y-2">
              <Button className="w-full" onClick={() => onOpen(selected)}>{pageActionLabel(selected)}<ArrowRight className="h-4 w-4" /></Button>
              <p className="text-xs leading-relaxed text-muted">{isExistingPage(selected) ? 'This page already exists. The editor will receive its current URL and instructions to improve it in place.' : `Opens ${isToolPage(selected) ? 'Build Page' : pageEditor(selected) === 'blog' ? 'Blog Writer' : 'the page builder'} with this keyword and brief ready to use.`}</p>
            </div>
            <div className="mt-5 space-y-5 text-sm">
              <div><p className="spec-label mb-1 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">Reader task</p><p className="text-muted">{selected.reader_outcome || selected.search_intent || selected.content_brief || 'Review the purpose of this page before writing.'}</p></div>
              {selected.user_problem && <div><p className="mb-1 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">User problem</p><p className="text-muted">{selected.user_problem}</p></div>}
              {selected.entity_topic && <div><p className="mb-1 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">Entity/topic</p><p className="text-muted">{selected.entity_topic}</p></div>}
              <div><p className="mb-1 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">Content requirements</p><p className="text-muted">Enough content to completely satisfy this page’s unique intent. No fixed word count.</p>{!!selected.content_requirements?.length && <ul className="mt-2 list-disc space-y-1 pl-4 text-muted">{selected.content_requirements.map(requirement => <li key={requirement}>{requirement}</li>)}</ul>}</div>
              {selected.url_decision_reason && <div><p className="mb-1 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">URL decision</p><p className="text-muted">{selected.url_decision_reason}</p></div>}
              {selected.unique_page_value && <div><p className="mb-1 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">Unique page value</p><p className="text-muted">{selected.unique_page_value}</p></div>}
              {selected.content_brief && <div><p className="mb-1 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">Coverage</p><p className="leading-relaxed text-muted">{selected.content_brief}</p></div>}
              {!!selected.scope_out?.length && <div><p className="mb-1 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">Leave to other pages</p><ul className="list-disc space-y-1 pl-4 text-muted">{selected.scope_out.map(scope => <li key={scope}>{scope}</li>)}</ul></div>}
              <div><p className="mb-1 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">Primary keyword</p><p className="font-mono text-sm text-amber">{selected.target_keyword}</p><p className="mt-2 font-mono text-xs text-muted">Volume: {selected.search_volume?.toLocaleString() ?? 'Unknown'} · Difficulty: {selected.difficulty ?? 'Unknown'}</p></div>
              {selected.evidence_type === 'editorial_proposal' && <div className="rounded-lg border border-dashed border-amber/50 bg-amber/5 p-3 font-mono text-xs leading-relaxed text-amber">Proposed from: {selected.support_phrase || 'site context'}. {selected.evidence_rationale || 'Confirm relevance and demand with research.'} No measured demand is implied.</div>}
              {!!selected.targeted_keywords?.length && <div><p className="mb-2 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">Supporting keywords</p><div className="flex flex-wrap gap-1.5">{selected.targeted_keywords.map(keyword => <span key={keyword} className="rounded bg-raised px-2 py-1 font-mono text-xs text-muted">{keyword}</span>)}</div></div>}
              {!!selected.h2_sections?.length && <div><p className="mb-2 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">Section outline</p><ol className="list-decimal space-y-2 pl-4 text-muted">{selected.h2_sections.map((section, index) => <li key={index}><span className="font-medium text-text">{section.h2_heading}</span>{section.section_definition && <p className="mt-0.5 text-xs">{section.section_definition}</p>}{!!section.targeted_keywords_placed_here?.length && <p className="mt-1 font-mono text-xs">Include: {section.targeted_keywords_placed_here.join(', ')}</p>}</li>)}</ol></div>}
              {!!selected.faq_schema_questions?.length && <div><p className="mb-2 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">Questions to answer</p>{selected.faq_schema_questions.map((faq, index) => <div key={index} className="mt-1 text-muted"><p>{faq.question}</p>{!!faq.targeted_keywords_placed_here?.length && <p className="mt-1 font-mono text-xs">Include: {faq.targeted_keywords_placed_here.join(', ')}</p>}</div>)}</div>}
              {!!selected.tool_functions?.length && <div><p className="mb-2 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">Tool requirements</p><ul className="list-disc pl-4 text-muted">{selected.tool_functions.map(item => <li key={item}>{item}</li>)}</ul></div>}
              <div><p className="mb-2 flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.14em] text-muted"><Link2 className="h-4 w-4" />Link to</p><div className="space-y-2">{links.filter(link => link.source_keyword === selected.target_keyword).map(link => <button key={link.target} type="button" onClick={() => selectTarget(link.target_keyword)} className="block text-left font-mono text-xs text-amber hover:underline">{link.target_keyword} <span className="text-muted">({link.relationship})</span></button>)}</div></div>
            </div>
          </div>
        </aside>}
      </div>
    </Card>

    {/* sheet footer */}
    <div className="flex items-center justify-between">
      <p className="annotation">END OF SHEET — {pages.length} NODES DRAFTED</p>
      <button type="button" onClick={() => { setSelectedTarget(null); setQuery(''); setFilter('all'); setTab('map') }} className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted hover:text-amber"><ArrowDown className="mr-1 inline h-3 w-3" />Reset board</button>
    </div>
  </section>
}
