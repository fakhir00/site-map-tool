export type MapLink = { source: string; target: string; source_keyword: string; target_keyword: string; source_url: string; target_url: string; anchor_text: string; relationship: string; reason: string }
export type LayerMap = Record<string, string[]>
export type Silo = { hub_title: string; target_keyword: string; h2_keywords?: string[]; layers: LayerMap }
export type Hub = Silo & { sub_silos?: Silo[] }
export type SectionDetail = { h2_heading: string; section_definition?: string; targeted_keywords_placed_here?: string[] }
export type FaqDetail = { question: string; targeted_keywords_placed_here?: string[] }
export type KeywordMetric = { phrase: string; keyword_type?: string; search_volume?: number | null; difficulty?: number | null; frequency?: number; source_domains?: string[]; seo_recommendation?: string | null; evidence_type?: string; research_status?: string; source_urls?: string[] }
export type PageDetail = { spoke_category?: string; id?: string; parent_target?: string | null; search_intent?: string; user_problem?: string; entity_topic?: string; content_requirements?: string[]; url_decision_reason?: string; unique_page_value?: string; reader_outcome?: string; scope_out?: string[]; evidence_rationale?: string; action?: string; existing_url?: string | null; evidence_type?: string; support_phrase?: string | null; article_title?: string; target_keyword?: string; slug?: string; page_type?: string; ranking_role?: string; search_volume?: number | null; difficulty?: number | null; content_brief?: string; targeted_keywords?: string[]; tool_functions?: string[]; writing_instructions?: string; h2_sections?: SectionDetail[]; faq_schema_questions?: FaqDetail[]; entity_terms?: string[]; internal_links?: string[]; tool_economics?: { qualifies: boolean; reason: string; minimum_volume: number; search_volume?: number | null; difficulty?: number | null } }
export type SpokeDetail = PageDetail & { article_title: string; target_keyword: string; spoke_category?: string }
export type DeduplicationCheck = { unique_target_keywords?: string; unique_titles?: string; unique_slugs?: string; semantic_intents?: string; duplicates_removed?: number }
export type KeywordDecision = { keyword: string; disposition: 'page_target' | 'supporting' | 'discard'; assigned_to?: string | null; placement?: string | null; reason: string }
export type IntentConsolidation = { from_keyword: string; to_keyword: string; reason: string; risk_type: string; one_page_test?: Record<string, boolean> | null }
export type Mapping = { intent_consolidations?: IntentConsolidation[]; map_version?: number; map_warnings?: string[]; topic_clusters?: { id: string; name: string; page_ids: string[] }[]; link_plan?: MapLink[]; authority_coverage?: { actual_spokes: number; new_spokes: number; existing_spokes: number; status: string; message: string; discovery_status: string }; hubs: Hub[]; site_domain?: string; _semantic_audit_status?: string; _planning_thought?: string; _deduplication_check?: DeduplicationCheck; _keyword_metrics?: KeywordMetric[]; master_hub?: PageDetail; spokes?: SpokeDetail[]; interlinking_strategy?: string; filtered_irrelevant_keywords?: string[]; discarded_keywords?: { keyword: string; reason: string }[]; keyword_assignments?: KeywordDecision[]; deferred_spoke_keywords?: string[]; writing_standards?: string[] }
export type HistorySummary = { id: string; project_id: string | null; title: string; keyword_count: number; created_at: string }
export type HistoryDetail = { id: string; project_id: string | null; title: string; context: string; keywords: string[]; cleaned_keywords: string[]; clusters: Mapping; created_at: string }
export type ProjectImport = { project_id: string; project_name: string; keywords: string[]; keyword_data?: KeywordMetric[]; context: string; research_summary?: { new_gaps: number; research_candidates: number; pending_review: number; existing_topics: number; planning_keywords: number; available_keywords: number; not_included: number } }

export const PAGE_COUNT_POLICY = 'Final spoke count is determined by semantic validation, distinct search intent, product capability, and unique user value. There is no minimum or target URL count.'

export const LINK_HIERARCHY_POLICY = 'The homepage leads to major use cases, major resources and selected supporting pages. Topical hubs handle deeper parent-child links. Do not automatically link the homepage to every spoke or give every page equal prominence. This hierarchy takes precedence over older blanket homepage/spoke linking instructions.'

export const URL_PURPOSE_POLICY = 'Do not create a URL just because a keyword exists. Keep only pages with a clearly distinct purpose. Small product features belong in the relevant product or documentation sections. Unsupported capabilities must not receive dedicated pages or implementation requirements.'
export const PRODUCT_HOME_POLICY = 'For product/tool sites, the homepage is the primary product page and editor entry point. It owns the exact-match core query, presents the tool, and links to major hubs and selected high-value supporting pages.'

// Saved maps can predate the selective-link policy. Remove the obsolete command
// instead of exporting two contradictory instructions to the downstream writer.
const currentLinkInstructions = (value: string) => value.replace(/\b(?:The\s+)?(?:homepage|home page|master hub)\s+(?:must\s+|should\s+)?links?\s+to\s+(?:every|all)\s+(?:the\s+)?spokes?\b[^.!?\n]*[.!?]?/gi, '').trim()

export const CONTENT_COMPLETENESS = 'Every page = enough content to completely satisfy its unique intent.'
export const isExistingPage = (page: PageDetail) => Boolean(page.existing_url) || page.action === 'update'
export const pageKeywords = (page: PageDetail) => [...new Set([page.target_keyword, ...(page.targeted_keywords || [])].filter((keyword): keyword is string => Boolean(keyword)))]
export function keywordCoverage(mapping: Mapping) {
  const decisions = new Map((mapping.keyword_assignments || []).map(item => [item.keyword, item]))
  const pages = [mapping.master_hub, ...(mapping.spokes || [])].filter((page): page is PageDetail => Boolean(page))
  const used = new Set(pages.flatMap(pageKeywords).filter(keyword => decisions.get(keyword)?.disposition !== 'discard'))
  const excluded = new Set([...decisions.values()].filter(item => item.disposition === 'discard').map(item => item.keyword))
  const inventory = new Set([...(mapping._keyword_metrics || []).map(item => item.phrase), ...decisions.keys(), ...used, ...excluded])
  const primary = new Set(pages.map(page => page.target_keyword).filter(Boolean))
  return { total: inventory.size, used: used.size, supporting: [...used].filter(keyword => !primary.has(keyword)).length,
    excluded: excluded.size, unassigned: [...inventory].filter(keyword => !used.has(keyword) && !excluded.has(keyword)).length }
}
export const pageEditor = (page: PageDetail) => ['tool', 'page', 'landing_page', 'service', 'product'].includes(page.page_type || '') ? 'page' : 'blog'
export const pageActionLabel = (page: PageDetail) => isExistingPage(page) ? 'Improve existing page' : pageEditor(page) === 'page' ? 'Create page' : 'Create blog'
export const PILLAR_CLUSTER_PROCESS = 'KEYWORD → SEARCH INTENT → USER PROBLEM → ENTITY/TOPIC → CONTENT REQUIREMENT → URL DECISION'

const toolIntent = /\b(tool|software|calculator|generator|maker|builder|creator|checker|converter|app)\b/i
const informationalIntent = /^(how|what|why|when|where|can|does)\b|\b(guide|tutorial|examples|symbols|definition|meaning|tips|troubleshooting|review|comparison|alternatives|vs|terms(?: and conditions)?|privacy(?: policy)?|disclaimer|legal|about us|contact us|cookie policy|refund policy|editorial policy|accessibility|support|faq)\b/i
const shouldBuildTool = (keyword: string) => toolIntent.test(keyword) && !informationalIntent.test(keyword)
const slugify = (value: string) => value.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
const pageSlug = (keyword: string, supplied?: string) => supplied || `/${slugify(keyword)}/`

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

export const parseFile = (text: string) => {
  const rows = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).map(parseCsvRow)
  if (!rows.length) return { keywords: [], keywordData: [] }
  const header = rows[0].map((cell) => cell.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim())
  const keywordIndex = header.findIndex((cell) => cell === 'keyword' || cell === 'keyword gap' || cell === 'phrase')
  const volumeIndex = header.findIndex((cell) => cell === 'search volume' || cell === 'volume')
  const difficultyIndex = header.findIndex((cell) => cell === 'difficulty' || cell === 'keyword difficulty' || cell === 'kd')
  const typeIndex = header.findIndex((cell) => cell === 'type' || cell === 'keyword type')
  const sourceDomainsIndex = header.findIndex((cell) => cell === 'source domains' || cell === 'source domain')
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
      source_domains: sourceDomainsIndex >= 0
        ? (row[sourceDomainsIndex] || '').split(';').map((value) => value.trim()).filter(Boolean)
        : [],
    }]
  })
  return { keywords: keywordData.map((item) => item.phrase), keywordData }
}

export const downloadText = (name: string, content: string) => {
  const url = URL.createObjectURL(new Blob([content], { type: 'text/plain;charset=utf-8' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = name
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export const grandArchitecturePrompt = (mapping: Mapping, context: string) => {
  const lines = ['# GRAND WEBSITE ARCHITECTURE BUILD PROMPT', '', 'Build the complete website architecture below. Follow every page specification and preserve the assigned keyword placements.', '']
  if (context.trim()) lines.push('## Website context', context.trim(), '')
  if (mapping._deduplication_check) lines.push('## Architecture validation', `- Semantic review: ${mapping._semantic_audit_status || 'not recorded'}`,  `- Cannibalizing pages removed: ${mapping._deduplication_check.duplicates_removed || 0}`, '')
  lines.push('## Global writing standards')
  ;(mapping.writing_standards || []).map(currentLinkInstructions).filter(Boolean).forEach((rule) => lines.push(`- ${rule}`))
  lines.push(`- ${URL_PURPOSE_POLICY}`, `- ${PRODUCT_HOME_POLICY}`)
  lines.push('', '## Required deliverables', '- Build every article and interactive tool in this plan as a production-ready page.', '- For each article, provide the title, meta title, meta description, H1, complete body copy, internal links, and FAQ schema only for assigned FAQs.', '- For each tool, provide the working interface and logic, helpful explanatory copy, accessibility labels, validation, result states, and requested export actions.', '', '## Execution rules', '- Create only pages marked create. Improve existing pages in place and preserve their URLs; never create duplicates.', '- Use each target keyword for only its assigned URL and keep every slug exactly as written.', `- ${CONTENT_COMPLETENESS} No fixed word count or padding.`, `- Planning logic: ${PILLAR_CLUSTER_PROCESS}`, '- Use H2 keywords only in their assigned substantive sections, FAQ keywords only in the FAQ block and FAQ schema, and entity terms naturally in the copy.', '- Never turn an entity or FAQ variation into an extra indexable page.', '- Implement every listed tool function on pages marked as tool.', '- Add the specified internal links and keep anchor text natural and descriptive.', '')

  lines.push('## Planned coverage', `${mapping.spokes?.length ?? mapping.authority_coverage?.actual_spokes ?? 0} spokes. ${PAGE_COUNT_POLICY}`, '')

  if (mapping.intent_consolidations?.length) {
    lines.push('## Consolidated intent overlaps', 'Keep these phrases on their assigned page; do not recreate separate URLs.')
    mapping.intent_consolidations.forEach(item => lines.push(`- ${item.from_keyword} → ${item.to_keyword} (${item.risk_type === 'doorway' ? 'Near-duplicate page risk' : 'Same user need'}): ${item.reason}`))
    lines.push('')
  }

  const addPage = (label: string, page: PageDetail) => {
    const target = page.target_keyword || ''
    const heading = label === 'MASTER HUB' ? `MASTER HUB: ${mapping.site_domain || page.article_title || target}` : `${label}: ${page.article_title || target}`
    lines.push(`## ${heading}`, `- Ranking role: ${page.ranking_role || (label === 'MASTER HUB' ? 'master_hub' : 'supporting_spoke')}`, `- Page type: ${page.page_type || (shouldBuildTool(target) ? 'tool' : 'article')}`, `- ${label === 'MASTER HUB' ? 'Primary keyword' : 'Target keyword'}: ${target}`, `- Slug: ${pageSlug(target, page.slug)}`, `- Search volume: ${page.search_volume ?? 'unknown'}`, `- Keyword difficulty: ${page.difficulty ?? 'unknown'}`, `- Content brief: ${page.content_brief || 'Fully satisfy the target search intent for the website audience.'}`)
    lines.push(`- Action: ${isExistingPage(page) ? 'update' : page.action || 'review'}${page.existing_url ? ` existing page ${page.existing_url}; preserve its URL` : ''}`, `- Evidence: ${page.evidence_type === 'editorial_proposal' ? 'Editorial proposal; validate demand before publishing' : 'Supplied keyword; demand may be unknown'}`)
    lines.push(`- Search intent: ${page.search_intent || page.reader_outcome || 'Review required'}`)
    if (page.user_problem) lines.push(`- User problem: ${page.user_problem}`)
    if (page.entity_topic) lines.push(`- Entity/topic: ${page.entity_topic}`)
    if (page.content_requirements?.length) {
      lines.push('- Content requirements:')
      page.content_requirements.forEach(requirement => lines.push(`  - ${requirement}`))
    }
    if (page.unique_page_value) lines.push(`- Unique page value: ${page.unique_page_value}`)
    if (page.url_decision_reason) lines.push(`- URL decision: ${page.url_decision_reason}`)
    if (page.targeted_keywords?.length) lines.push(`- Additional hub keywords: ${page.targeted_keywords.join(', ')}`)
    if (page.tool_functions?.length) { lines.push('- Required tool functions:'); page.tool_functions.forEach((item) => lines.push(`  - ${item}`)) }
    if (page.h2_sections?.length) { lines.push('- H2 plan:'); page.h2_sections.forEach((section) => lines.push(`  - ${section.h2_heading}: ${section.section_definition || 'Cover this section directly.'}${section.targeted_keywords_placed_here?.length ? ` Keywords: ${section.targeted_keywords_placed_here.join(', ')}` : ''}`)) }
    if (page.faq_schema_questions?.length) { lines.push('- FAQ schema:'); page.faq_schema_questions.forEach((faq) => lines.push(`  - ${faq.question}${faq.targeted_keywords_placed_here?.length ? ` Keywords: ${faq.targeted_keywords_placed_here.join(', ')}` : ''}`)) }
    if (page.entity_terms?.length) lines.push(`- Entities to use naturally: ${page.entity_terms.join(', ')}`)
    if (page.internal_links?.length) lines.push(`- Required internal links to these target pages: ${page.internal_links.join(', ')}`)
    if (page.reader_outcome) lines.push(`- Reader outcome: ${page.reader_outcome}`)
    if (page.scope_out?.length) lines.push(`- Leave to other pages: ${page.scope_out.join('; ')}`)
    if (page.parent_target) lines.push(`- Parent page: ${page.parent_target}`)
    if (page.writing_instructions && currentLinkInstructions(page.writing_instructions)) lines.push(`- Writing instructions: ${currentLinkInstructions(page.writing_instructions)}`)
    lines.push('')
  }

  if (mapping.master_hub) addPage('MASTER HUB', mapping.master_hub)
  ;(mapping.spokes || []).forEach((spoke, index) => addPage(`SPOKE ${index + 1} — ${spoke.spoke_category || 'Strategic article'}`, spoke))
  lines.push('## Interlinking strategy', LINK_HIERARCHY_POLICY, currentLinkInstructions(mapping.interlinking_strategy || '') || 'Each supporting page links to its relevant parent; add useful contextual links for the reader’s next task.', '')
  if (mapping.filtered_irrelevant_keywords?.length) lines.push(
    '## DO NOT CREATE DEDICATED PAGES FOR THESE KEYWORDS',
    'These phrases may still occur naturally where semantically appropriate. They must not be assigned as standalone SEO targets unless later evidence demonstrates a genuinely distinct search intent.',
    '',
    ...mapping.filtered_irrelevant_keywords.map((keyword) => `- ${keyword}`),
    '',
  )
  if (mapping.link_plan?.length) {
    lines.push('## Internal link implementation')
    mapping.link_plan.forEach(link => lines.push(`- ${link.source_url} → ${link.target_url}; suggested anchor: ${link.anchor_text}; ${link.reason}`))
  }
  lines.push('Begin with the Master Hub, then work through each spoke in order. Reuse every existing URL and create only missing pages. Return production-ready pages and tools that follow this architecture.')
  return lines.join('\n')
}


export function pageArchitectureBrief(page: PageDetail, mapping: Mapping): string {
  return [
    `Page: ${page.article_title || page.target_keyword}`,
    `URL: ${page.existing_url || page.slug || '/'}`,
    `Action: ${isExistingPage(page) ? 'update' : page.action || 'review'}`,
    isExistingPage(page) ? 'Improve the existing page in place. Preserve its URL; do not create a duplicate page.' : '',
    `Parent page: ${page.parent_target || (page.target_keyword === mapping.master_hub?.target_keyword ? 'Homepage' : mapping.master_hub?.target_keyword) || 'Review parent assignment'}`,
    LINK_HIERARCHY_POLICY,
    URL_PURPOSE_POLICY,
    PRODUCT_HOME_POLICY,
    CONTENT_COMPLETENESS,
    `Planning logic: ${PILLAR_CLUSTER_PROCESS}`,
    `Keyword: ${page.target_keyword || ''}`,
    `Search intent: ${page.search_intent || page.reader_outcome || ''}`,
    `User problem: ${page.user_problem || page.reader_outcome || page.search_intent || ''}`,
    `Entity/topic: ${page.entity_topic || page.target_keyword || ''}`,
    `Content requirements: ${(page.content_requirements || []).join('; ') || page.content_brief || 'Completely solve the assigned reader problem.'}`,
    page.url_decision_reason ? `URL decision: ${page.url_decision_reason}` : '',
    page.unique_page_value ? `Unique page value: ${page.unique_page_value}` : '',
    `Reader task: ${page.reader_outcome || page.search_intent || ''}`,
    `Scope: ${page.content_brief || ''}`,
    `Leave to other pages: ${(page.scope_out || []).join('; ')}`,
    `Outline: ${(page.h2_sections || []).map(section => `${section.h2_heading}: ${section.section_definition || ''}`).join('\n')}`,
    `Supporting keywords: ${(page.targeted_keywords || []).join(', ')}`,
    `Tool functions: ${(page.tool_functions || []).join('; ')}`,
    'Internal links:',
    ...(mapping.link_plan || []).filter(link => link.source_keyword === page.target_keyword).map(link => `${link.target_url} — ${link.anchor_text}`),
    ...(mapping.link_plan ? [] : page.internal_links || []),
    page.evidence_type === 'editorial_proposal' ? 'Editorial idea: confirm demand and relevance before publication.' : '',
  ].filter(Boolean).join('\n')
}

export function normalizeSavedMapping(mapping: Mapping): Mapping {
  if (mapping.master_hub || mapping.spokes?.length || !mapping.hubs?.length) return {
    ...mapping,
    master_hub: mapping.master_hub?.existing_url ? { ...mapping.master_hub, action: 'update' } : mapping.master_hub,
    spokes: mapping.spokes?.map(page => page.existing_url ? { ...page, action: 'update' } : page),
  }
  const [root, ...otherHubs] = mapping.hubs
  const spokes: SpokeDetail[] = []
  const visit = (hub: Hub, includeHub: boolean) => {
    if (includeHub && hub.target_keyword) spokes.push({ article_title: hub.hub_title, target_keyword: hub.target_keyword, slug: pageSlug(hub.target_keyword), targeted_keywords: hub.h2_keywords || [], spoke_category: 'Supporting hubs' })
    for (const [category, values] of Object.entries(hub.layers || {})) {
      for (const value of values || []) {
        const target = value.match(/\(Target Keyword:\s*(.*?)\)/i)?.[1]?.trim() || value.trim()
        const title = value.split(/\(Target Keyword:/i)[0].replace('[Tool]', '').trim() || target
        if (!target || target === root.target_keyword || spokes.some(page => page.target_keyword === target)) continue
        spokes.push({ article_title: title, target_keyword: target, spoke_category: category, slug: pageSlug(target), page_type: value.includes('[Tool]') ? 'tool' : 'article', internal_links: [root.target_keyword] })
      }
    }
    for (const child of hub.sub_silos || []) visit(child, true)
  }
  visit(root, false)
  otherHubs.forEach(hub => visit(hub, true))
  return { ...mapping, master_hub: { target_keyword: root.target_keyword, article_title: root.hub_title, slug: '/', targeted_keywords: root.h2_keywords || [], internal_links: [] }, spokes }
}
