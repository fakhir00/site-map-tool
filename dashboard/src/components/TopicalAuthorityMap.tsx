import { useMemo, useRef, useState } from 'react'
import { ArrowDown, ArrowRight, CheckCircle2, Download, FileText, Hammer, Layers, Network, Search, Wrench, X } from 'lucide-react'
import { Button } from './ui/Button'
import { Card } from './ui/Card'
import { Badge } from './ui/Badge'
import { CountUp } from './CountUp'
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

const AMBER = '#F5A524'
const WARM_WHITE = '#F2F4F8'

function fallbackLinks(pages: PageDetail[]): MapLink[] {
  return pages.flatMap(page => (page.internal_links || []).flatMap(target => {
    const other = pages.find(candidate => candidate.target_keyword === target)
    return other ? [{ source: page.id || page.target_keyword!, target: other.id || target, source_keyword: page.target_keyword!, target_keyword: target, source_url: page.existing_url || page.slug || '/', target_url: other.existing_url || other.slug || '/', anchor_text: label(other), relationship: 'related', reason: 'Link recorded in this saved plan.' }] : []
  }))
}

type GraphNode = { x: number; y: number; name: string; count: number; toBuild: number; color: string }

function HubSpokeGraph({ hubLabel, hubExisting, groups, onSelectGroup, selectedGroup }: {
  hubLabel: string
  hubExisting: boolean
  groups: [string, PageDetail[]][]
  onSelectGroup: (name: string | null) => void
  selectedGroup: string | null
}) {
  const W = 900
  const H = 460
  const cx = W / 2
  const cy = H / 2 - 10
  const rx = 300
  const ry = 138
  const n = groups.length
  const hubColor = hubExisting ? WARM_WHITE : AMBER

  const nodes: GraphNode[] = groups.map(([name, pages], i) => {
    const angle = -Math.PI / 2 + (i * 2 * Math.PI) / Math.max(n, 1)
    const x = cx + rx * Math.cos(angle)
    const y = cy + ry * Math.sin(angle)
    const toBuild = pages.filter(page => !isExistingPage(page)).length
    return { x, y, name, count: pages.length, toBuild, color: toBuild > 0 ? AMBER : WARM_WHITE }
  })

  // Gentle curved spokes: quadratic bezier with a perpendicular offset on the control point
  const spokePath = (node: GraphNode) => {
    const dx = node.x - cx
    const dy = node.y - cy
    const dist = Math.hypot(dx, dy) || 1
    const startX = cx + (dx / dist) * 52
    const startY = cy + (dy / dist) * 52
    const endX = node.x - (dx / dist) * 30
    const endY = node.y - (dy / dist) * 30
    const mx = (startX + endX) / 2
    const my = (startY + endY) / 2
    const px = -dy / dist
    const py = dx / dist
    const bow = 34
    const qx = mx + px * bow
    const qy = my + py * bow
    return `M ${startX} ${startY} Q ${qx} ${qy} ${endX} ${endY}`
  }

  return (
    <div className="overflow-hidden">
      <style>{`
        .hsg-node { transform-box: fill-box; transform-origin: center; transition: transform 200ms ease; cursor: pointer; }
        .hsg-node:hover { transform: scale(1.1); }
      `}</style>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full select-none" role="img" aria-label="Hub and spoke topic graph">
        <defs>
          <filter id="hsg-glow-amber" x="-80%" y="-80%" width="260%" height="260%">
            <feGaussianBlur stdDeviation="10" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
          <filter id="hsg-glow-white" x="-80%" y="-80%" width="260%" height="260%">
            <feGaussianBlur stdDeviation="8" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
          <radialGradient id="hsg-hub" cx="40%" cy="35%" r="80%">
            <stop offset="0%" stopColor={hubColor} stopOpacity="0.95" />
            <stop offset="100%" stopColor={hubColor} stopOpacity="0.55" />
          </radialGradient>
        </defs>

        {nodes.map(node => (
          <path key={`spoke-${node.name}`} className="hsg-spoke-flow" d={spokePath(node)} fill="none"
            stroke={node.color === AMBER ? 'rgba(245,165,36,0.35)' : 'rgba(242,244,248,0.18)'}
            strokeWidth={2.5} strokeLinecap="round" />
        ))}

        {nodes.map((node, i) => (
          <g key={`node-${node.name}`} className="hsg-node" onClick={() => onSelectGroup(selectedGroup === node.name ? null : node.name)}>
            <title>{node.name} — {node.count} pages ({node.toBuild} to build)</title>
            <g className="hsg-float" style={{ animationDelay: `${-(i * 1.35).toFixed(2)}s` }}>
              {node.color === AMBER && (
                <circle cx={node.x} cy={node.y} r={26} fill="none" stroke={AMBER} strokeWidth={2} className="hsg-pulse-ring" />
              )}
              <circle cx={node.x} cy={node.y} r={26} fill={node.color} opacity={0.9}
                filter={node.color === AMBER ? 'url(#hsg-glow-amber)' : 'url(#hsg-glow-white)'} />
              {selectedGroup === node.name && (
                <circle cx={node.x} cy={node.y} r={34} fill="none" stroke={AMBER} strokeWidth={2} strokeDasharray="5 5" opacity={0.9} />
              )}
              <text x={node.x} y={node.y + 5} textAnchor="middle" fontSize={15} fontWeight={700} fill="#0B0E14" fontFamily="JetBrains Mono, monospace">{node.count}</text>
              <text x={node.x} y={node.y + 48} textAnchor="middle" fontSize={12.5} fill="#9AA3B2" fontFamily="Inter, sans-serif">
                {node.name.length > 26 ? `${node.name.slice(0, 25)}…` : node.name}
              </text>
              <text x={node.x} y={node.y + 65} textAnchor="middle" fontSize={10.5} fill={node.color === AMBER ? AMBER : '#9AA3B2'} fontFamily="JetBrains Mono, monospace">
                {node.toBuild > 0 ? `${node.toBuild} to build` : 'complete'}
              </text>
            </g>
          </g>
        ))}

        <g className="hsg-node" onClick={() => onSelectGroup(null)}>
          <title>{hubLabel} — main hub (click to clear filter)</title>
          <circle cx={cx} cy={cy} r={58} fill="#0B0E14" opacity={0.45} />
          <circle cx={cx} cy={cy} r={46} fill="url(#hsg-hub)" filter={hubColor === AMBER ? 'url(#hsg-glow-amber)' : 'url(#hsg-glow-white)'} />
          <text x={cx} y={cy - 2} textAnchor="middle" fontSize={13} fontWeight={700} fill="#0B0E14" fontFamily="Inter, sans-serif">HUB</text>
          <text x={cx} y={cy + 16} textAnchor="middle" fontSize={10.5} fill="#0B0E14" opacity={0.75} fontFamily="Inter, sans-serif">
            {hubLabel.length > 24 ? `${hubLabel.slice(0, 23)}…` : hubLabel}
          </text>
        </g>
      </svg>
      <div className="flex flex-wrap items-center justify-center gap-6 border-t border-line px-4 py-3.5 text-xs text-muted">
        <span className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full" style={{ background: AMBER, boxShadow: `0 0 10px ${AMBER}` }} />Pages to build</span>
        <span className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full" style={{ background: WARM_WHITE, boxShadow: `0 0 10px ${WARM_WHITE}` }} />Already on your site</span>
        <span className="font-mono">Click a node to filter the groups below</span>
      </div>
    </div>
  )
}

export function TopicalAuthorityMap({ mapping, onOpen }: Props) {
  const briefRef = useRef<HTMLElement>(null)
  const [tab, setTab] = useState<'map' | 'pages' | 'links' | 'keywords'>('pages')
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null)
  const [selectedTarget, setSelectedTarget] = useState<string | null>(mapping.master_hub?.target_keyword || null)
  const pages = useMemo(() => [mapping.master_hub, ...(mapping.spokes || [])].filter((page): page is PageDetail => Boolean(page?.target_keyword)), [mapping])
  const coverage = useMemo(() => keywordCoverage(mapping), [mapping])
  const selected = pages.find(page => page.target_keyword === selectedTarget)
  const researchIncomplete = mapping.authority_coverage?.discovery_status === 'unavailable'
  const links = mapping.link_plan || fallbackLinks(pages)
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
  const onSelectGroup = (name: string | null) => {
    setSelectedGroup(name)
    setQuery(name || '')
  }
  const coveragePercent = coverage.total > 0 ? Math.round((coverage.used / coverage.total) * 100) : 0
  const pagesToCreate = pages.filter(page => !isExistingPage(page)).length

  const pageStatusBadge = (page: PageDetail) => {
    if (isExistingPage(page)) return <Badge variant="green">Existing page</Badge>
    if (page.action === 'create') return <Badge variant="amber">New page</Badge>
    return <Badge variant="slate">Review page</Badge>
  }
  const pageTypeChip = (page: PageDetail) => (
    <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">
      {isToolPage(page) ? <Wrench className="h-3.5 w-3.5 text-glow-amber" /> : <FileText className="h-3.5 w-3.5 text-soft-violet" />}
      {isToolPage(page) ? 'Tool' : pageEditor(page) === 'blog' ? 'Blog' : 'Page'}
    </span>
  )
  const card = (page: PageDetail) => (
    <div key={page.target_keyword} className="flex flex-col gap-2.5">
      <button type="button" aria-pressed={selectedTarget === page.target_keyword} onClick={() => selectPage(page)}
        className={`card-lift w-full rounded-2xl border p-5 text-left ${selectedTarget === page.target_keyword ? 'border-glow-amber/70 bg-glow-amber/[0.05] shadow-[0_0_28px_rgba(245,165,36,0.14)]' : 'border-line bg-raised hover:border-white/15'}`}>
        <span className="mb-3 flex items-center justify-between gap-2">
          {pageTypeChip(page)}
          {pageStatusBadge(page)}
        </span>
        <span className="block text-[15px] font-semibold leading-6 text-ink">{label(page)}</span>
        <span className="mt-1 block break-all font-mono text-[11px] text-muted/80">{page.existing_url || page.slug || '/'}</span>
        <span className="mt-3 block text-xs text-muted">{pageKeywords(page).length} keywords covered · {(page.targeted_keywords || []).length} supporting</span>
        <span className={`mt-3 inline-flex w-fit rounded-full border px-2.5 py-0.5 text-[10px] font-semibold ${page.evidence_type === 'editorial_proposal' ? 'border-glow-amber/30 bg-glow-amber/10 text-glow-amber' : 'border-line bg-white/5 text-muted'}`}>{evidence(page)}</span>
      </button>
      <Button size="sm" variant="primary" className="w-full" onClick={() => onOpen(page)}>{pageActionLabel(page)}<ArrowRight className="h-4 w-4" /></Button>
    </div>
  )

  return <section className="space-y-6 animate-fade-up" aria-label="Topical authority map">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h3 className="font-display text-2xl font-bold tracking-tight text-ink">Your topical authority map</h3>
        <p className="mt-1.5 text-sm text-muted">Select a page to inspect its purpose, keyword coverage and connections.</p>
      </div>
      <Button variant="secondary" onClick={() => downloadText('topical-authority-map.json', JSON.stringify(mapping, null, 2))}><Download className="h-4 w-4" />Export map</Button>
    </div>

    {/* Stat strip — three calm focal points */}
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      {[
        { name: 'Pages in plan', value: pages.length, icon: <Layers className="h-4 w-4 text-glow-amber" /> },
        { name: 'Topic groups', value: groups.length, icon: <Network className="h-4 w-4 text-soft-violet" /> },
        { name: 'Pages to create', value: pagesToCreate, icon: <Hammer className="h-4 w-4 text-alive-green" /> },
      ].map((stat, i) => (
        <Card key={stat.name} className={`animate-fade-up p-5 stagger-${i + 1}`}>
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium uppercase tracking-wider text-muted">{stat.name}</p>
            {stat.icon}
          </div>
          <p className="mt-2 font-display text-4xl font-bold tracking-tight text-ink"><CountUp value={stat.value} /></p>
        </Card>
      ))}
    </div>

    {/* Keyword coverage — slim progress, not a shouty banner */}
    <Card className="p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-sm font-semibold text-ink">{coverage.used.toLocaleString()} <span className="font-normal text-muted">of {coverage.total.toLocaleString()} keywords placed</span></p>
        <p className="font-mono text-xs text-glow-amber">{coveragePercent}%</p>
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/5">
        <div className="h-full rounded-full bg-glow-amber shadow-[0_0_12px_rgba(245,165,36,0.5)] transition-all duration-700" style={{ width: `${coveragePercent}%` }} />
      </div>
      <p className="mt-3 text-xs leading-relaxed text-muted">{coverage.supporting} supporting keywords are included within page content. Related phrases can share a page; each page covers one distinct reader task.</p>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
        {coverage.excluded > 0 && <button type="button" onClick={() => { setTab('keywords'); setQuery(''); setFilter('all') }} className="font-medium text-soft-violet underline underline-offset-2 hover:text-ink">{coverage.excluded} keywords excluded · Review keyword decisions</button>}
        {coverage.unassigned > 0 && <p role="status" className="text-glow-amber">{coverage.unassigned} {coverage.unassigned === 1 ? 'keyword has' : 'keywords have'} no recorded placement. Rebuild to review coverage.</p>}
      </div>
    </Card>

    {/* Review status — single calm row */}
    <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-line bg-surface px-5 py-4">
      <CheckCircle2 className={`h-5 w-5 shrink-0 ${!researchIncomplete && mapping._semantic_audit_status === 'passed' ? 'text-alive-green' : 'text-glow-amber'}`} />
      <p className="text-sm font-semibold text-ink">{researchIncomplete ? 'Topic research incomplete' : mapping._semantic_audit_status === 'passed' ? 'Intent review passed' : 'Intent review needed'}</p>
      <p className="text-xs text-muted">{researchIncomplete ? '· Partial map from supplied keywords' : '· Editorial plan; validate demand before publishing'}</p>
      {mapping.authority_coverage && <span className="ml-auto font-mono text-xs text-muted">{mapping.spokes?.length ?? mapping.authority_coverage.actual_spokes} spokes</span>}
    </div>

    {(mapping.map_warnings?.length || mapping._planning_thought || (mapping.intent_consolidations?.length ?? 0) > 0) && (
      <details className="rounded-2xl border border-line bg-surface p-5 text-sm">
        <summary className="cursor-pointer list-none font-semibold text-ink [&::-webkit-details-marker]:hidden">Plan notes <span className="ml-1 font-normal text-muted">— warnings, rationale and merged intents</span></summary>
        <div className="disclosure"><div>
        <div className="mt-4 space-y-4">
          {mapping.map_warnings?.map(warning => <p key={warning} className="text-sm text-glow-amber">{warning}</p>)}
          {mapping._planning_thought && <div><p className="mb-1 font-semibold text-ink">Planning rationale</p><p className="leading-relaxed text-muted">{mapping._planning_thought}</p></div>}
          {!!mapping.intent_consolidations?.length && <div><p className="mb-1 font-semibold text-ink">Consolidated intent overlaps ({mapping.intent_consolidations.length})</p><p className="text-muted">These keywords share an existing task. Keep them on the assigned page instead of creating extra URLs.</p>
            <ul className="mt-3 space-y-3">{mapping.intent_consolidations.map(item => <li key={item.from_keyword} className="break-words text-ink"><p className="font-medium">{item.from_keyword} → {item.to_keyword}</p><p className="mt-1 text-xs text-muted">{item.risk_type === 'doorway' ? 'Near-duplicate page risk' : 'Same user need'}: {item.reason}</p></li>)}</ul></div>}
        </div>
        </div></div>
      </details>
    )}

    <Card className="overflow-hidden p-0" lift={false}>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-4">
        <div className="flex flex-wrap gap-1 rounded-full border border-line bg-raised p-1" role="tablist" aria-label="Map views">
          {(['pages', 'map', 'links', 'keywords'] as const).map(view => (
            <button key={view} type="button" id={`map-tab-${view}`} role="tab" tabIndex={tab === view ? 0 : -1} aria-controls="map-panel" aria-selected={tab === view} onKeyDown={event => {
              const views = ['pages', 'map', 'links', 'keywords'] as const
              const index = views.indexOf(view)
              const next = event.key === 'ArrowRight' ? (index + 1) % views.length : event.key === 'ArrowLeft' ? (index + views.length - 1) % views.length : event.key === 'Home' ? 0 : event.key === 'End' ? views.length - 1 : -1
              if (next >= 0) { event.preventDefault(); setTab(views[next]); document.getElementById(`map-tab-${views[next]}`)?.focus() }
            }} onClick={() => setTab(view)}
              className={`rounded-full px-4 py-2 text-sm font-semibold transition-all ${tab === view ? 'bg-glow-amber text-abyss shadow-[0_0_18px_rgba(245,165,36,0.35)]' : 'text-muted hover:text-ink'}`}>
              {view === 'keywords' ? 'Keyword decisions' : view === 'links' ? `Links (${links.length})` : view === 'pages' ? 'Pages' : 'Map'}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          <label className="flex items-center gap-2 rounded-xl border border-line bg-raised px-3 focus-within:border-glow-amber/60">
            <Search className="h-4 w-4 text-muted" />
            <input aria-label="Search map" placeholder="Find a topic or page…" value={query} onChange={event => { setQuery(event.target.value); setSelectedGroup(null) }} className="w-40 bg-transparent py-2 text-sm text-ink outline-none placeholder:text-muted/60" />
          </label>
          <select aria-label="Filter pages" value={filter} onChange={event => setFilter(event.target.value)} className="cursor-pointer rounded-xl border border-line bg-raised px-3 text-sm text-ink outline-none focus:border-glow-amber/60">
            <option value="all">All pages</option>
            <option value="create">New pages to create</option>
            <option value="article">Blogs</option>
            <option value="tool">Pages and tools</option>
            <option value="update">Existing pages</option>
            <option value="research">Research ideas</option>
          </select>
        </div>
      </div>

      <div className={`grid ${selected ? 'xl:grid-cols-[minmax(0,1fr)_360px]' : ''}`}>
        <div id="map-panel" role="tabpanel" aria-labelledby={`map-tab-${tab}`} className="min-w-0 bg-abyss/60 p-4 sm:p-6">
          <div className="mb-6 rounded-2xl border border-soft-violet/25 bg-soft-violet/[0.06] p-4">
            <h4 className="text-sm font-semibold text-ink">{tabHelp[tab].title}</h4>
            <p className="mt-1 text-sm leading-relaxed text-muted">{tabHelp[tab].text}</p>
          </div>

          {tab === 'map' && <>
            {groups.length > 0 && (
              <Card className="mb-6 overflow-hidden p-0" lift={false}>
                <HubSpokeGraph
                  hubLabel={mapping.master_hub ? label(mapping.master_hub) : 'Main hub'}
                  hubExisting={!!mapping.master_hub && isExistingPage(mapping.master_hub)}
                  groups={selectedGroup ? groups.filter(([name]) => name === selectedGroup) : groups}
                  onSelectGroup={onSelectGroup}
                  selectedGroup={selectedGroup}
                />
              </Card>
            )}
            {groups.length > 0 && <div className="mb-5 flex justify-center text-muted/40"><ArrowDown className="h-6 w-6" /></div>}
            {groups.length > 0 && <div className="grid items-start gap-5 md:grid-cols-2 2xl:grid-cols-3">
              {groups.filter(([name]) => !selectedGroup || name === selectedGroup).map(([name, members], gi) => {
                const filtered = members.filter(matches)
                if (!filtered.length) return null
                const toBuild = filtered.filter(page => !isExistingPage(page)).length
                return (
                  <div key={name} className={`animate-fade-up rounded-2xl border border-line bg-raised p-4 stagger-${Math.min(gi + 1, 8)}`}>
                    <div className="mb-4 flex items-center justify-between gap-2">
                      <h4 className="flex items-center gap-2 text-sm font-bold text-ink">
                        <span className="h-2.5 w-2.5 rounded-full" style={{ background: toBuild > 0 ? AMBER : WARM_WHITE, boxShadow: `0 0 10px ${toBuild > 0 ? AMBER : WARM_WHITE}` }} />
                        {name}
                      </h4>
                      <span className="font-mono text-xs text-muted">{filtered.length}</span>
                    </div>
                    <div className="space-y-3">{filtered.map(card)}</div>
                  </div>
                )
              })}
            </div>}
            {!mapping.spokes?.length && <p className="py-10 text-center text-sm text-muted">No distinct supporting pages were identified. Add evidence for more reader tasks and rebuild.</p>}
            {pages.length > 0 && visible.length === 0 && <p className="py-10 text-center text-sm text-muted">No pages match these filters.</p>}
          </>}

          {tab === 'pages' && <div className="space-y-3">
            {visible.map((page, pi) => (
              <div key={page.target_keyword} className={`card-lift animate-fade-up flex flex-wrap items-start justify-between gap-4 rounded-2xl border border-line bg-raised p-5 stagger-${Math.min(pi + 1, 8)}`}>
                <div className="min-w-0 flex-1 basis-56">
                  <p className="flex items-center gap-2 text-xs font-medium">{pageTypeChip(page)}<span className="text-muted">·</span>{pageStatusBadge(page)}</p>
                  <h4 className="mt-2 text-[15px] font-semibold text-ink">{label(page)}</h4>
                  <p className="mt-1 text-xs leading-relaxed text-muted">{page.search_intent || page.content_brief}</p>
                  <p className="mt-2 break-all font-mono text-xs text-muted/80">{page.existing_url || page.slug}</p>
                  <details className="mt-3 text-xs">
                    <summary className="cursor-pointer font-medium text-soft-violet hover:text-ink">{pageKeywords(page).length} keywords covered</summary>
                    <p className="mt-2 text-muted">Main keyword: <span className="text-ink">{page.target_keyword}</span></p>
                    <div className="mt-2 flex flex-wrap gap-1.5">{page.targeted_keywords?.map(keyword => <span key={keyword} className="rounded-md border border-line bg-white/5 px-2 py-1 text-muted">{keyword}</span>)}</div>
                  </details>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" variant="secondary" onClick={() => selectPage(page)} aria-label={`View brief for ${label(page)}`}>View brief</Button>
                  <Button size="sm" variant="primary" onClick={() => onOpen(page)} aria-label={`${pageActionLabel(page)}: ${label(page)}`}>{pageActionLabel(page)}<ArrowRight className="h-4 w-4" /></Button>
                </div>
              </div>
            ))}
            {!visible.length && <p className="p-8 text-center text-sm text-muted">No pages match these filters.</p>}
          </div>}

          {tab === 'links' && <div className="space-y-3">
            <p className="text-sm text-muted">Directed links to implement in relevant page content. Suggested anchors can be adapted naturally.</p>
            <Button variant="secondary" onClick={() => downloadText('internal-links.csv', ['Source URL,Target URL,Anchor text,Relationship', ...links.map(link => [link.source_url, link.target_url, link.anchor_text, link.relationship].map(value => `"${value.replace(/"/g, '""')}"`).join(','))].join('\n'))}><Download className="h-4 w-4" />Export links</Button>
            {visibleLinks.map(link => (
              <div key={`${link.source}-${link.target}`} className="rounded-2xl border border-line bg-raised p-5 text-sm">
                <p className="break-words font-medium text-ink">{link.source_keyword}<ArrowRight className="mx-2 inline h-4 w-4 text-glow-amber" /><button type="button" onClick={() => selectTarget(link.target_keyword)} className="text-soft-violet underline underline-offset-2 hover:text-ink">{link.target_keyword}</button></p>
                <p className="mt-2 break-all font-mono text-xs text-muted">{link.source_url} → {link.target_url}</p>
                <p className="mt-2 text-xs text-muted">Anchor: <span className="text-ink">{link.anchor_text}</span> · {link.reason}</p>
              </div>
            ))}
            {!visibleLinks.length && <p className="p-8 text-center text-sm text-muted">No links match these filters.</p>}
          </div>}

          {tab === 'keywords' && <div className="space-y-2.5">
            <p className="mb-4 text-sm text-muted">Every keyword gets one destination or a documented reason for exclusion.</p>
            {(mapping.keyword_assignments || []).filter(item => `${item.keyword} ${item.assigned_to || ''}`.toLowerCase().includes(query.toLowerCase()) && (filter === 'all' || visible.some(page => page.target_keyword === item.assigned_to))).map(item => (
              <div key={item.keyword} className="rounded-2xl border border-line bg-raised p-4 text-sm">
                <div className="flex flex-wrap justify-between gap-2"><strong className="text-ink">{item.keyword}</strong><span className="text-xs text-muted">{{ page_target: 'Main keyword', supporting: 'Include on page', discard: 'Not included' }[item.disposition]}</span></div>
                {item.assigned_to && <button type="button" onClick={() => selectTarget(item.assigned_to!)} className="mt-1 text-xs text-soft-violet underline underline-offset-2 hover:text-ink">{item.assigned_to} {item.placement ? `· ${item.placement}` : ''}</button>}
                <p className="mt-2 text-xs text-muted">{item.reason}</p>
              </div>
            ))}
            {!mapping.keyword_assignments?.length && <p className="text-sm text-muted">This saved plan has no recorded keyword decisions.</p>}
          </div>}
        </div>

        {selected && <aside ref={briefRef} aria-label="Page brief" className="border-t border-line p-4 sm:p-5 xl:border-l xl:border-t-0">
          <div className="rounded-2xl border border-line bg-raised p-6 shadow-[0_24px_64px_rgba(0,0,0,0.5)] xl:sticky xl:top-6 xl:max-h-[calc(100vh-3rem)] xl:overflow-y-auto">
            <div className="flex items-start justify-between gap-3">
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-glow-amber">Page brief</p>
              <button type="button" aria-label="Close page brief" onClick={() => setSelectedTarget(null)} className="rounded-lg p-1.5 text-muted transition-colors hover:bg-white/5 hover:text-ink"><X className="h-4 w-4" /></button>
            </div>
            <h4 className="mt-3 font-display text-xl font-bold tracking-tight text-ink">{label(selected)}</h4>
            <p className="mt-1 break-all font-mono text-xs text-muted">{selected.existing_url || selected.slug || '/'}</p>
            <div className="mt-3">{pageStatusBadge(selected)}</div>
            <p className="mt-2 text-xs text-muted">{evidence(selected)} · {isExistingPage(selected) ? 'Already on your site' : selected.action === 'create' ? (isToolPage(selected) ? 'Create tool' : 'Create page') : 'Review page'}</p>
            {safeUrl(selected.existing_url) && <a href={safeUrl(selected.existing_url)} target="_blank" rel="noreferrer" className="mt-2 block break-all text-xs text-soft-violet underline underline-offset-2 hover:text-ink">Open existing page ↗</a>}
            <div className="mt-5 space-y-2.5">
              <Button variant="glow" className="w-full" onClick={() => onOpen(selected)}>{pageActionLabel(selected)}<ArrowRight className="h-4 w-4" /></Button>
              <p className="text-xs leading-relaxed text-muted">{isExistingPage(selected) ? 'This page already exists. The editor will receive its current URL and instructions to improve it in place.' : `Opens ${isToolPage(selected) ? 'Build Page' : pageEditor(selected) === 'blog' ? 'Blog Writer' : 'the page builder'} with this keyword and brief ready to use.`}</p>
            </div>
            <div className="mt-6 space-y-5 border-t border-line pt-6 text-sm">
              <div><p className="mb-1 font-semibold text-ink">Reader task</p><p className="text-muted">{selected.reader_outcome || selected.search_intent || selected.content_brief || 'Review the purpose of this page before writing.'}</p></div>
              {selected.user_problem && <div><p className="mb-1 font-semibold text-ink">User problem</p><p className="text-muted">{selected.user_problem}</p></div>}
              {selected.entity_topic && <div><p className="mb-1 font-semibold text-ink">Entity/topic</p><p className="text-muted">{selected.entity_topic}</p></div>}
              <div><p className="mb-1 font-semibold text-ink">Content requirements</p><p className="text-muted">Enough content to completely satisfy this page’s unique intent. No fixed word count.</p>{!!selected.content_requirements?.length && <ul className="mt-2 list-disc space-y-1 pl-4 text-muted">{selected.content_requirements.map(requirement => <li key={requirement}>{requirement}</li>)}</ul>}</div>
              {selected.url_decision_reason && <div><p className="mb-1 font-semibold text-ink">URL decision</p><p className="text-muted">{selected.url_decision_reason}</p></div>}
              {selected.unique_page_value && <div><p className="mb-1 font-semibold text-ink">Unique page value</p><p className="text-muted">{selected.unique_page_value}</p></div>}
              {selected.content_brief && <div><p className="mb-1 font-semibold text-ink">Coverage</p><p className="leading-relaxed text-muted">{selected.content_brief}</p></div>}
              {!!selected.scope_out?.length && <div><p className="mb-1 font-semibold text-ink">Leave to other pages</p><ul className="list-disc space-y-1 pl-4 text-muted">{selected.scope_out.map(scope => <li key={scope}>{scope}</li>)}</ul></div>}
              <div><p className="mb-1 font-semibold text-ink">Primary keyword</p><p className="text-muted">{selected.target_keyword}</p><p className="mt-2 font-mono text-xs text-muted">Volume: {selected.search_volume?.toLocaleString() ?? 'Unknown'} · Difficulty: {selected.difficulty ?? 'Unknown'}</p></div>
              {selected.evidence_type === 'editorial_proposal' && <div className="rounded-xl border border-glow-amber/25 bg-glow-amber/[0.06] p-3.5 text-xs leading-relaxed text-ink">Proposed from: {selected.support_phrase || 'site context'}. {selected.evidence_rationale || 'Confirm relevance and demand with research.'} No measured demand is implied.</div>}
              {!!selected.targeted_keywords?.length && <div><p className="mb-2 font-semibold text-ink">Supporting keywords</p><div className="flex flex-wrap gap-1.5">{selected.targeted_keywords.map(keyword => <span key={keyword} className="rounded-md border border-line bg-white/5 px-2 py-1 text-xs text-muted">{keyword}</span>)}</div></div>}
              {!!selected.h2_sections?.length && <div><p className="mb-2 font-semibold text-ink">Section outline</p><ol className="list-decimal space-y-2 pl-4 text-muted">{selected.h2_sections.map((section, index) => <li key={index}><span className="font-medium text-ink">{section.h2_heading}</span>{section.section_definition && <p className="mt-0.5 text-xs">{section.section_definition}</p>}{!!section.targeted_keywords_placed_here?.length && <p className="mt-1 text-xs">Include: {section.targeted_keywords_placed_here.join(', ')}</p>}</li>)}</ol></div>}
              {!!selected.faq_schema_questions?.length && <div><p className="mb-2 font-semibold text-ink">Questions to answer</p>{selected.faq_schema_questions.map((faq, index) => <div key={index} className="mt-1 text-muted"><p>{faq.question}</p>{!!faq.targeted_keywords_placed_here?.length && <p className="mt-1 text-xs">Include: {faq.targeted_keywords_placed_here.join(', ')}</p>}</div>)}</div>}
              {!!selected.tool_functions?.length && <div><p className="mb-2 font-semibold text-ink">Tool requirements</p><ul className="list-disc pl-4 text-muted">{selected.tool_functions.map(item => <li key={item}>{item}</li>)}</ul></div>}
              <div><p className="mb-2 flex items-center gap-2 font-semibold text-ink"><Wrench className="h-4 w-4 text-glow-amber" />Link to</p><div className="space-y-2">{links.filter(link => link.source_keyword === selected.target_keyword).map(link => <button key={link.target} type="button" onClick={() => selectTarget(link.target_keyword)} className="block text-left text-xs text-soft-violet hover:text-ink hover:underline">{link.target_keyword} <span className="text-muted">({link.relationship})</span></button>)}</div></div>
            </div>
          </div>
        </aside>}
      </div>
    </Card>
  </section>
}

