import { test, expect, type Page } from '@playwright/test'

const id = '11111111-1111-4111-8111-111111111111'
const primary = 'lunar age calculator'
const master = { id: 'home', target_keyword: primary, article_title: 'Lunar Age Calculator', page_type: 'tool', slug: '/', action: 'update', existing_url: 'https://example.com/', reader_outcome: 'Calculate age in a lunar calendar.', internal_links: ['how to calculate lunar age'], targeted_keywords: ['free lunar age calculator'] }
const method = { word_count_suggestion: 1800, user_problem: 'Find the correct age without using the calculator.', entity_topic: 'Manual lunar age calculation', content_requirements: ['Explain the boundary rule.', 'Show a worked date example.'], url_decision_reason: 'Reuse the existing manual-method URL for this distinct instructional task.', id: 'method', target_keyword: 'how to calculate lunar age', article_title: 'Calculate Lunar Age by Hand', page_type: 'article', slug: '/manual-method/', action: 'update', existing_url: 'https://example.com/manual-method/', spoke_category: 'Age calculation', reader_outcome: 'Calculate age by hand using the correct year boundary.', content_brief: 'Explain the manual calculation with a worked example.', scope_out: ['Calendar conversion belongs to the converter.'], h2_sections: [{ h2_heading: 'Choose the year boundary', section_definition: 'Use the correct calendar.' }], targeted_keywords: ['lunar age formula'], internal_links: [primary] }
const proposal = { id: 'leap', target_keyword: 'lunar leap month rules', article_title: 'Birthdays in Leap Months', page_type: 'article', slug: '/leap-months/', spoke_category: 'Calendar edge cases', action: 'create', evidence_type: 'editorial_proposal', support_phrase: primary, evidence_rationale: 'Explain the intercalary month input.', internal_links: [primary] }
const mapping = { map_version: 2, topic_clusters: [{ id: 'calculation', name: 'Age calculation', page_ids: ['method'] }, { id: 'calendar', name: 'Calendar edge cases', page_ids: ['leap'] }], hubs: [], master_hub: master, spokes: [method, proposal], _semantic_audit_status: 'passed', authority_coverage: { actual_spokes: 2, minimum_spokes: 20, maximum_spokes: 30, target_spokes: 25, new_spokes: 1, existing_spokes: 1, status: 'needs_research', message: 'More distinct topic evidence is needed.', discovery_status: 'completed' }, keyword_assignments: [{ keyword: primary, disposition: 'page_target', assigned_to: primary, reason: 'Main tool task' }, { keyword: 'lunar age formula', disposition: 'supporting', assigned_to: method.target_keyword, placement: 'h2:Choose the year boundary', reason: 'Manual calculation task' }], link_plan: [{ source: 'home', target: 'method', source_keyword: primary, target_keyword: method.target_keyword, source_url: 'https://example.com/', target_url: method.existing_url, anchor_text: method.article_title, relationship: 'child', reason: 'Learn the manual method.' }, { source: 'method', target: 'home', source_keyword: method.target_keyword, target_keyword: primary, source_url: method.existing_url, target_url: 'https://example.com/', anchor_text: master.article_title, relationship: 'parent', reason: 'Return to the calculator.' }] }
const history = { id, project_id: id, title: 'Lunar age map', context: '', keywords: [primary, method.target_keyword], cleaned_keywords: [primary, method.target_keyword], clusters: mapping, created_at: '2026-09-29T10:00:00Z', keyword_count: 2 }

async function setup(page: Page, saved = false) {
  await page.addInitScript(() => localStorage.setItem('token', 'test-token'))
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname.replace('/api', '')
    let data: unknown = []
    if (path === '/auth/me') data = { id, email: 'test@example.com', full_name: 'Map Tester' }
    else if (path === '/hub-spoke/history') data = saved ? [history] : []
    else if (path === `/hub-spoke/history/${id}`) data = history
    else if (path === '/projects') data = [{ id, name: 'Lunar age project' }]
    else if (path === '/hub-spoke/build') data = { keywords: history.cleaned_keywords, history_id: id, clusters: mapping }
    return route.fulfill({ json: data })
  })
}
async function loadSaved(page: Page) {
  await page.goto('/hub-spoke')
  await page.getByText('Saved maps', { exact: false }).click()
  await page.getByRole('button', { name: /^Lunar age map/ }).click()
  await expect(page.getByRole('heading', { name: 'Your topical authority map', exact: true })).toBeVisible()
}

test('builds a map with an explicit main topic and exports actual URL links', async ({ page }) => {
  await setup(page)
  let submitted: Record<string, unknown> | undefined
  await page.route('**/api/hub-spoke/build', route => {
    submitted = route.request().postDataJSON()
    return route.fulfill({ json: { keywords: history.cleaned_keywords, history_id: id, clusters: mapping } })
  })
  await page.goto('/hub-spoke')
  await page.getByLabel('Keyword research').fill('how to calculate lunar age\nlunar age calculator')
  await page.getByLabel('Main topic', { exact: true }).fill(primary)
  await page.getByLabel('Existing page URLs', { exact: true }).fill(method.existing_url)
  await page.getByRole('button', { name: 'Build topical map' }).click()
  await expect(page.getByRole('heading', { name: 'Your topical authority map', exact: true })).toBeVisible()
  expect(submitted?.primary_keyword).toBe(primary)
  expect(submitted).not.toHaveProperty('target_spokes')
  await expect(page.getByLabel('Target spokes', { exact: true })).toHaveCount(0)
  expect(submitted?.existing_urls).toEqual([method.existing_url])
  await page.getByRole('button', { name: 'View brief for Calculate Lunar Age by Hand', exact: true }).click()
  const brief = page.getByRole('complementary', { name: 'Page brief' })
  await expect(brief).toContainText(method.reader_outcome)
  await expect(brief).toContainText(method.user_problem)
  await expect(brief).toContainText(method.content_requirements[0])
  await expect(brief).toContainText(method.url_decision_reason)
  await expect(brief).toContainText('No fixed word count.')
  await expect(brief).toContainText(method.scope_out[0])
  await expect(brief.getByRole('link', { name: 'Open existing page' })).toHaveAttribute('href', method.existing_url)
  await page.getByRole('tab', { name: 'Links (2)' }).click()
  await expect(page.getByRole('tabpanel')).toContainText('https://example.com/ → https://example.com/manual-method/')
  const downloaded = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export links' }).click()
  expect((await downloaded).suggestedFilename()).toBe('internal-links.csv')
  await page.getByRole('tab', { name: 'Keyword decisions' }).click()
  await expect(page.getByRole('tabpanel')).toContainText('Manual calculation task')
  await page.getByRole('tab', { name: 'Keyword decisions' }).press('Home')
  await expect(page.getByRole('tab', { name: /^pages$/i })).toBeFocused()
  await page.getByRole('tab', { name: /^pages$/i }).press('ArrowRight')
  await expect(page.getByRole('tab', { name: /^map$/i })).toHaveAttribute('aria-selected', 'true')
})

test('saved map sends its page brief and project to the article writer', async ({ page }) => {
  await setup(page, true)
  await loadSaved(page)
  await expect(page.getByText('2 spokes', { exact: true })).toBeVisible()
  await expect(page.getByText('More distinct topic evidence is needed.', { exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: 'View brief for Calculate Lunar Age by Hand', exact: true }).click()
  await page.getByRole('complementary', { name: 'Page brief' }).getByRole('button', { name: 'Improve existing page', exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`/write-blog\\?.*project_id=${id}`))
  await expect(page.getByLabel('Architecture brief', { exact: true })).toContainText(method.existing_url)
  let submitted: Record<string, unknown> | undefined
  await page.route('**/api/projects/manual-generate', route => {
    submitted = route.request().postDataJSON()
    return route.fulfill({ status: 503, json: { detail: 'Test service unavailable' } })
  })
  await page.getByRole('button', { name: 'Generate Blog' }).click()
  await expect(page.getByText('Test service unavailable')).toBeVisible()
  expect(submitted?.project_id).toBe(id)
  expect(submitted?.architecture_brief).toContain(method.reader_outcome)
  expect(submitted?.architecture_brief).toContain(method.user_problem)
  expect(submitted?.architecture_brief).toContain(method.content_requirements[1])
  expect(submitted?.architecture_brief).toContain(method.url_decision_reason)
  expect(submitted?.architecture_brief).toContain('Every page = enough content to completely satisfy its unique intent.')
  expect(submitted?.architecture_brief).not.toContain('1800')
  expect(submitted?.architecture_brief).toContain('https://example.com/')
})

test('keeps previous map on failure and locks inputs during generation', async ({ page }) => {
  await setup(page, true)
  await loadSaved(page)
  await page.getByLabel('Main topic', { exact: true }).fill('updated lunar topic')
  let release!: () => void
  const pending = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/hub-spoke/build', async route => { await pending; await route.fulfill({ status: 502, json: { detail: 'AI connection unavailable' } }) })
  await page.getByRole('button', { name: 'Build topical map' }).click()
  await expect(page.getByLabel('Main topic', { exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Start fresh' })).toBeDisabled()
  release()
  await expect(page.getByRole('alert')).toHaveText('AI connection unavailable')
  await expect(page.getByRole('heading', { name: 'Your topical authority map', exact: true })).toBeVisible()
  await expect(page.getByText('Inputs have changed.', { exact: false })).toBeVisible()
  await expect(page.getByLabel('Main topic', { exact: true })).toBeEnabled()
})

test('filters research ideas and remains usable on a phone', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await setup(page, true)
  await loadSaved(page)
  await page.getByLabel('Filter pages').selectOption('research')
  await expect(page.getByRole('button', { name: 'View brief for Birthdays in Leap Months', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'View brief for Calculate Lunar Age by Hand', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: 'View brief for Birthdays in Leap Months', exact: true }).click()
  await expect(page.getByRole('complementary', { name: 'Page brief' })).toContainText('No measured demand is implied.')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: 'test-results/topical-map-mobile.png', fullPage: true })
})

test('short CSV rows retain unknown metrics and uploads clear old project context', async ({ page }) => {
  await setup(page, true)
  await loadSaved(page)
  await page.getByLabel('Website and audience context').fill('Old project context')
  await page.locator('input[type=file]').setInputFiles({ name: 'research.csv', mimeType: 'text/csv', buffer: Buffer.from('Keyword,Volume,Source Domains\nlunar age calculator\nlunar age formula,0') })
  await expect(page.getByLabel('Website and audience context')).toHaveValue('')
  await expect(page.getByLabel('Main topic', { exact: true })).toHaveValue(primary)
  let submitted: Record<string, unknown> | undefined
  await page.route('**/api/hub-spoke/build', route => { submitted = route.request().postDataJSON(); return route.fulfill({ json: { keywords: history.cleaned_keywords, history_id: id, clusters: mapping } }) })
  await page.getByRole('button', { name: 'Build topical map' }).click()
  await expect(page.getByText('Inputs have changed.', { exact: false })).toHaveCount(0)
  expect(submitted?.project_id).toBeNull()
  expect(submitted?.keyword_data).toEqual(expect.arrayContaining([expect.objectContaining({ phrase: primary, search_volume: null }), expect.objectContaining({ phrase: 'lunar age formula', search_volume: 0 })]))
})

test('opens historical maps that only contain hub and layer labels', async ({ page }) => {
  await setup(page, true)
  await page.route(`**/api/hub-spoke/history/${id}`, route => route.fulfill({ json: { ...history, clusters: { hubs: [{ hub_title: 'Age calculator', target_keyword: primary, layers: { Methods: ['Age by Hand (Target Keyword: how to calculate lunar age)'] } }] } } }))
  await loadSaved(page)
  await expect(page.getByRole('button', { name: 'View brief for Age by Hand', exact: true })).toBeVisible()
  await expect(page.getByText('Intent review needed', { exact: false })).toBeVisible()
})

test('desktop map preview and tool handoff preserve the selected scope', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1100 })
  await setup(page, true)
  await loadSaved(page)
  await page.getByRole('region', { name: 'Topical authority map', exact: true }).scrollIntoViewIfNeeded()
  await page.screenshot({ path: 'test-results/topical-map-desktop.png', fullPage: true })
  await page.getByRole('complementary', { name: 'Page brief' }).getByRole('button', { name: 'Improve existing page', exact: true }).click()
  await expect(page).toHaveURL(/gap-page-prompts/)
  await expect(page.getByLabel('Architecture brief', { exact: true })).toContainText('Calculate age in a lunar calendar.')
})


test('validates oversized inventories and invalid existing URLs before generation', async ({ page }) => {
  await setup(page)
  let calls = 0
  await page.route('**/api/hub-spoke/build', route => { calls += 1; return route.fulfill({ json: {} }) })
  await page.goto('/hub-spoke')
  await page.getByLabel('Keyword research').fill(Array.from({ length: 301 }, (_, index) => `lunar topic ${index}`).join('\n'))
  await expect(page.getByRole('alert')).toContainText('300 distinct keywords')
  await expect(page.getByRole('button', { name: 'Build topical map' })).toBeDisabled()
  await page.getByLabel('Keyword research').fill(primary)
  await page.getByLabel('Existing page URLs', { exact: true }).fill('javascript:alert(1)')
  await page.getByRole('button', { name: 'Build topical map' }).click()
  await expect(page.getByRole('alert')).toContainText('valid existing page URLs')
  expect(calls).toBe(0)
})


test('architecture exports replace legacy length quotas with intent and content requirements', async () => {
  const { grandArchitecturePrompt } = await import('../src/lib/hubSpoke')
  const prompt = grandArchitecturePrompt(mapping, '')
  expect(prompt).toContain('Every page = enough content to completely satisfy its unique intent.')
  expect(prompt).toContain('KEYWORD → SEARCH INTENT → USER PROBLEM → ENTITY/TOPIC → CONTENT REQUIREMENT → URL DECISION')
  expect(prompt).toContain(method.content_requirements[0])
  expect(prompt).toContain(method.url_decision_reason)
  expect(prompt).not.toContain('Suggested word count')
  expect(prompt).not.toContain('1800')
  expect(prompt).not.toContain('2000')
  expect(prompt).toContain('There is no minimum or target URL count.')
  expect(prompt).not.toContain('20–30')
  expect(prompt).not.toContain('More distinct topic evidence is needed.')
  expect(prompt).toContain('Topical hubs handle deeper parent-child links.')
  expect(prompt).not.toContain('Every spoke links to the Master Hub')
})

test('exports remove stale blanket homepage instructions and keep useful contextual guidance', async () => {
  const { grandArchitecturePrompt, normalizeSavedMapping } = await import('../src/lib/hubSpoke')
  const obsolete = 'The homepage links to every spoke via a categorized footer or hub section.'
  const prompt = grandArchitecturePrompt({ ...mapping,
    writing_standards: [obsolete, 'Use clear examples.'],
    master_hub: { ...master, writing_instructions: `Present the editor. ${obsolete}` },
    interlinking_strategy: `Link examples to relevant symbols. ${obsolete} Keep anchors descriptive.`,
  }, '')
  expect(prompt).not.toContain('The homepage links to every spoke')
  expect(prompt).not.toContain('categorized footer')
  expect(prompt).toContain('Link examples to relevant symbols.')
  expect(prompt).toContain('Keep anchors descriptive.')
  expect(prompt).toContain('Present the editor.')
  expect(prompt).toContain('homepage is the primary product page and editor entry point')
  expect(prompt).toContain('Small product features belong in the relevant product or documentation sections.')
  const legacy = normalizeSavedMapping({ hubs: [{ hub_title: 'Editor', target_keyword: 'editor', layers: { Guides: ['symbols', 'examples'] } }] })
  expect(legacy.master_hub?.internal_links).toEqual([])
})


test('shows and exports resolved near-duplicate page risks', async ({ page }) => {
  const consolidation = { from_keyword: 'lunar age calculator with leap months', to_keyword: primary,
    reason: 'The same calculator can handle this input; a feature URL adds no separate task.', risk_type: 'doorway' }
  const reviewed = { ...mapping, intent_consolidations: [consolidation] }
  await setup(page, true)
  await page.route(`**/api/hub-spoke/history/${id}`, route => route.fulfill({ json: { ...history, clusters: reviewed } }))
  await loadSaved(page)
  await page.getByText('Consolidated intent overlaps (1)', { exact: true }).click()
  await expect(page.getByText(`Near-duplicate page risk: ${consolidation.reason}`, { exact: true })).toBeVisible()
  const { grandArchitecturePrompt } = await import('../src/lib/hubSpoke')
  const prompt = grandArchitecturePrompt(reviewed, '')
  expect(prompt).toContain(`${consolidation.from_keyword} → ${primary}`)
  expect(prompt).toContain(consolidation.reason)
  expect(prompt).toContain('do not recreate separate URLs')
})


test('Pages actions open the correct editor directly, carrying the selected brief', async ({ page }) => {
  await setup(page, true)
  const tool = { ...proposal, id: 'converter', target_keyword: 'lunar date converter', article_title: 'Lunar Date Converter', page_type: 'tool' }
  await page.route(`**/api/hub-spoke/history/${id}`, route => route.fulfill({ json: { ...history, clusters: { ...mapping, spokes: [method, proposal, tool] } } }))
  await loadSaved(page)
  await page.getByRole('tab', { name: /^pages$/i }).click()
  await page.getByRole('button', { name: 'Create blog: Birthdays in Leap Months', exact: true }).click()
  await expect(page).toHaveURL(/write-blog\?/)
  await expect(page.getByLabel('Architecture brief', { exact: true })).toContainText(proposal.target_keyword)
  await loadSaved(page)
  await page.getByRole('tab', { name: /^pages$/i }).click()
  await page.getByRole('button', { name: 'Create page: Lunar Date Converter', exact: true }).click()
  await expect(page).toHaveURL(/gap-page-prompts\?/)
  await expect(page.getByLabel('Architecture brief', { exact: true })).toContainText(tool.target_keyword)
  expect(new URL(page.url()).searchParams.get('project_id')).toBe(id)
})

test('every tab explains its purpose and existing URLs never offer Create', async ({ page }) => {
  await setup(page, true)
  // Historical data may have a stale create action despite carrying an owned URL.
  await page.route(`**/api/hub-spoke/history/${id}`, route => route.fulfill({ json: { ...history, clusters: { ...mapping, spokes: [{ ...method, action: 'create' }, proposal] } } }))
  await loadSaved(page)
  for (const [tab, title] of [
    ['Map', 'See how your topics fit together'], ['Pages', 'Choose what to create or improve'],
    ['Links (2)', 'Connect related pages on your site'], ['Keyword decisions', 'Understand where each keyword belongs'],
  ]) {
    await page.getByRole('tab', { name: tab, exact: true }).click()
    await expect(page.getByRole('tabpanel').getByRole('heading', { name: title })).toBeVisible()
  }
  await page.getByRole('tab', { name: 'Pages', exact: true }).click()
  await expect(page.getByRole('button', { name: `Improve existing page: ${method.article_title}`, exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: `Create blog: ${method.article_title}`, exact: true })).toHaveCount(0)
  await page.getByLabel('Filter pages').selectOption('create')
  await expect(page.getByRole('tabpanel')).not.toContainText(method.article_title)
  await expect(page.getByRole('button', { name: 'Create blog: Birthdays in Leap Months', exact: true })).toBeVisible()
  await page.getByLabel('Filter pages').selectOption('update')
  await page.getByRole('button', { name: `View brief for ${method.article_title}`, exact: true }).click()
  await expect(page.getByRole('complementary', { name: 'Page brief' })).toContainText('This page already exists.')
})

test('starts with Pages and uses the requested tab order', async ({ page }) => {
  await setup(page, true)
  await loadSaved(page)
  const tabs = page.getByRole('tab')
  await expect(tabs).toHaveText(['Pages', 'Map', 'Links (2)', 'Keyword decisions'])
  await expect(page.getByRole('tab', { name: 'Pages', exact: true })).toHaveAttribute('aria-selected', 'true')
})

test('a historical map with failed topic discovery is clearly incomplete', async ({ page }) => {
  await setup(page, true)
  await page.route(`**/api/hub-spoke/history/${id}`, route => route.fulfill({ json: {
    ...history, clusters: { ...mapping, spokes: [], authority_coverage: {
      ...mapping.authority_coverage, actual_spokes: 0, discovery_status: 'unavailable',
    } },
  } }))
  await loadSaved(page)
  await expect(page.getByText('Topic research incomplete', { exact: false })).toBeVisible()
  await expect(page.getByText('Intent review passed', { exact: false })).toHaveCount(0)
  await expect(page.getByRole('status')).toContainText('Use Build topical map above to retry')
})
