import { test, expect, type Page } from '@playwright/test'

const id = '11111111-1111-4111-8111-111111111111'
const project = { id, name: 'Lunar age research', domain: 'https://example.com', own_domain: 'https://example.com', status: 'complete', target_keywords: ['lunar age calculator'], total_keywords: 1, urls_found: 2, urls_processed: 2, urls_failed: 0, created_at: '2026-09-26T10:00:00Z', last_scanned_at: '2026-09-26T10:00:00Z' }
const user = { id, email: 'first@example.com', full_name: 'First User', plan: 'free', created_at: '2026-09-26T10:00:00Z' }

async function mockAPI(page: Page) {
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname.replace('/api', '')
    let data: unknown = []
    if (path === '/auth/me') data = user
    else if (path === '/health') data = { revision: 'audit123', database: 'connected' }
    else if (path === '/providers/ai/status' || path === '/providers/ai/check') data = { configured: true, message: 'Provider status', providers: [{ name: 'DeepSeek', model: 'test', available: false, message: 'Insufficient balance.' }] }
    else if (path.startsWith('/providers/')) data = { configured: true, authenticated: true, available: true, message: 'Connected' }
    else if (path === '/projects') data = [project]
    else if (path === `/projects/${id}`) data = project
    else if (path.endsWith('/stats')) data = { total_urls: 2, scraped_urls: 2, failed_urls: 0, pending_urls: 0, total_keywords: 1, unique_keyword_types: { primary: 1 } }
    else if (path.endsWith('/scan/status')) data = { ...project, percent: 100, current_url: null }
    else if (path.endsWith('/keywords')) data = { items: [], total: 0, page: 1, page_size: 50, pages: 1 }
    else if (path.endsWith('/articles')) data = { items: [] }
    else if (path.endsWith('/keywords/hub-spoke')) data = { clusters: null, tier_metadata: {} }
    await route.fulfill({ json: data })
  })
}

const pages = ['/', `/projects/${id}`, '/scan', '/gold-hunter', '/hub-spoke', '/settings', '/website-prompts', '/gap-page-prompts', '/write-blog', `/write-blog/${id}`, '/saved-keywords']
test('workspace connection failures are visible promptly and retry restores the account', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('token', 'test-token'))
  await mockAPI(page)
  let unavailable = true
  for (const endpoint of ['auth/me', 'projects']) {
    await page.route(`**/api/${endpoint}`, route => unavailable
      ? route.fulfill({ status: 503, json: { detail: 'Account database temporarily unavailable' } })
      : route.fulfill({ json: endpoint === 'auth/me' ? user : [project] }))
  }
  await page.goto('/')
  await expect(page.getByRole('alert')).toContainText('Could not load your account', { timeout: 5000 })
  await expect(page.getByText('Account unavailable', { exact: true })).toBeVisible()
  await expect(page.getByText('0 active projects', { exact: true })).toHaveCount(0)
  await expect(page.getByText('No scans yet', { exact: true })).toHaveCount(0)
  expect(await page.evaluate(() => localStorage.getItem('token'))).toBe('test-token')
  unavailable = false
  await page.getByRole('button', { name: 'Retry connection', exact: true }).click()
  await expect(page.getByText('First User', { exact: true })).toBeVisible()
  await expect(page.getByText('1 active project', { exact: true })).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('pending account requests show loading instead of an empty account', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('token', 'test-token'))
  await mockAPI(page)
  let release!: () => void
  const pending = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/auth/me', async route => { await pending; await route.fulfill({ json: user }) })
  await page.goto('/')
  await expect(page.getByText('Loading account…', { exact: true })).toBeVisible()
  await expect(page.getByRole('status')).toHaveText('Connecting to your workspace…')
  await expect(page.getByText('User', { exact: true })).toHaveCount(0)
  release()
  await expect(page.getByText('First User', { exact: true })).toBeVisible()
})

test('a hanging account request times out once instead of retrying silently for minutes', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('token', 'test-token'))
  await mockAPI(page)
  const requestTimes: number[] = []
  await page.route('**/api/auth/me', () => { requestTimes.push(Date.now()) })
  await page.goto('/')
  await expect(page.getByRole('alert')).toContainText('The API request timed out', { timeout: 18_000 })
  // React StrictMode may cancel/restart the initial mount in development.
  // No additional attempt should start when the 15-second deadline expires.
  expect(requestTimes.length).toBeGreaterThan(0)
  expect(Math.max(...requestTimes) - Math.min(...requestTimes)).toBeLessThan(1000)
  expect(await page.evaluate(() => localStorage.getItem('token'))).toBe('test-token')
})

test('expired account session redirects to login instead of staying empty', async ({ page }) => {
  await page.addInitScript(() => {
    if (!sessionStorage.getItem('test-initialized')) {
      localStorage.setItem('token', 'expired-token')
      sessionStorage.setItem('test-initialized', 'true')
    }
  })
  await mockAPI(page)
  await page.route('**/api/auth/me', route => route.fulfill({ status: 401, json: { detail: 'Invalid or missing authentication token' } }))
  await page.goto('/')
  await expect(page).toHaveURL(/\/login$/)
  expect(await page.evaluate(() => localStorage.getItem('token'))).toBeNull()
})

for (const path of ['/website-prompts', '/gap-page-prompts']) {
  test(`prompt workflow ${path} completes without inventing an audit score`, async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('token', 'test-token'))
    await mockAPI(page)
    await page.route('**/api/website-prompts/analyze-intent', route => route.fulfill({ json: { intent: 'A lunar age tool', competitors: [] } }))
    await page.route('**/api/website-prompts/generate*', route => route.fulfill({ json: { prompt: 'Build a useful lunar age tool.', audit_score: null, attempts: 1 } }))
    await page.goto(path)
    await page.getByPlaceholder('e.g. mortgage calculator').fill('lunar age calculator')
    await page.getByRole('button', { name: 'Analyze Intent', exact: true }).click()
    await page.getByRole('button', { name: 'Confirm Intent & Generate Prompt', exact: true }).click()
    await expect(page.getByText('Not audited', { exact: true })).toBeVisible()
    await expect(page.getByText('Build a useful lunar age tool.', { exact: true })).toBeVisible()
  })
}

for (const path of pages) {
  test(`dashboard page ${path} renders without a runtime error`, async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    await page.addInitScript(() => localStorage.setItem('token', 'test-token'))
    await mockAPI(page)
    await page.goto(path)
    await expect(page.getByRole('heading').first()).toBeVisible()
    await expect(page.getByRole('link', { name: 'Dashboard', exact: true }).first()).toBeVisible()
    expect(errors).toEqual([])
  })
}
for (const path of ['/login', '/register']) {
  test(`public page ${path} renders its form`, async ({ page }) => {
    await mockAPI(page)
    await page.goto(path)
    await expect(page.locator('input[type=email]')).toBeVisible()
    await expect(page.locator('input[type=password]').first()).toBeVisible()
  })
}

test('unauthenticated users are redirected to sign in', async ({ page }) => {
  await page.goto('/settings')
  await expect(page).toHaveURL(/\/login$/)
})

test('settings exposes the failing AI provider and deployed revision', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('token', 'test-token'))
  await mockAPI(page)
  await page.goto('/settings')
  await expect(page.getByText('Insufficient balance.')).toBeVisible()
  await expect(page.getByText(/Backend revision: audit123/)).toBeVisible()
  const request = page.waitForRequest(r => r.url().endsWith('/providers/ai/check') && r.method() === 'POST')
  await page.getByRole('button', { name: 'Test AI connection' }).click()
  await request
})

test('saved completion diagnostics remain visible', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('token', 'test-token'))
  await mockAPI(page)
  await page.route(`**/api/projects/${id}/scan/jobs`, route => route.fulfill({ json: [{ id: 'job', status: 'complete', error_message: 'DataForSEO research unavailable; inspect provider status.', created_at: '2026-09-26T10:00:00Z' }] }))
  await page.goto(`/projects/${id}`)
  await expect(page.getByText('DataForSEO research unavailable; inspect provider status.').first()).toBeVisible()
})

test('manual blog preserves the source project', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('token', 'test-token'))
  await mockAPI(page)
  let body: Record<string, unknown> | undefined
  await page.route('**/api/projects/manual-generate', route => { body = route.request().postDataJSON(); return route.fulfill({ json: { project_id: id } }) })
  await page.goto(`/write-blog?keyword=lunar+age+guide&project_id=${id}`)
  await page.getByRole('button', { name: /generate/i }).first().click()
  await expect.poll(() => body?.project_id).toBe(id)
})

test('signing into another account clears the previous account display', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('token', 'test-token'))
  await mockAPI(page)
  await page.goto('/')
  await expect(page.getByText('First User', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Sign out', exact: true }).click()
  await expect(page).toHaveURL(/\/login$/)
  await page.route('**/api/auth/login', route => route.fulfill({ json: { access_token: 'second-token' } }))
  await page.route('**/api/auth/me', route => route.fulfill({ json: { ...user, full_name: 'Second User', email: 'second@example.com' } }))
  await page.route('**/api/projects', route => route.fulfill({ json: [] }))
  await page.locator('input[type=email]').fill('second@example.com')
  await page.locator('input[type=password]').fill('long-password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByText('Second User', { exact: true })).toBeVisible()
  await expect(page.getByText('First User', { exact: true })).toHaveCount(0)
  await expect(page.getByText('Lunar age research', { exact: true })).toHaveCount(0)
})

test('Gap Hunter creates a project and starts its scan with the entered seeds', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('token', 'test-token'))
  await mockAPI(page)
  let submitted: Record<string, unknown> | undefined
  await page.route('**/api/projects', route => {
    if (route.request().method() === 'POST') {
      submitted = route.request().postDataJSON()
      return route.fulfill({ json: project })
    }
    return route.fulfill({ json: [project] })
  })
  await page.goto('/scan')
  await page.getByPlaceholder('https://yourcompany.com').fill('https://example.com')
  await page.getByPlaceholder('sitemap generator, seo tool').fill('lunar age, chinese age')
  const started = page.waitForRequest(r => r.url().endsWith(`/projects/${id}/scan/start`))
  await page.getByRole('button', { name: 'Find gaps', exact: true }).click()
  await started
  await expect(page).toHaveURL(new RegExp(`/projects/${id}$`))
  expect(submitted?.target_keywords).toEqual(['lunar age', 'chinese age'])
})

test('Gold Hunter displays project creation failures', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('token', 'test-token'))
  await mockAPI(page)
  await page.route('**/api/goldhunter/history', route => route.fulfill({ json: [{ id, input_url: 'https://example.com', audit_summary: 'Lunar age tool', seeds: [{ keyword: 'lunar age', justification: 'Core task' }], created_at: project.created_at }] }))
  await page.route('**/api/projects', route => route.request().method() === 'POST'
    ? route.fulfill({ status: 503, json: { detail: 'Project storage temporarily unavailable' } })
    : route.fulfill({ json: [] }))
  await page.goto('/gold-hunter')
  await page.getByRole('button', { name: 'Run Gap Hunter with 1 seeds' }).click()
  await expect(page.getByText('Project storage temporarily unavailable', { exact: true })).toBeVisible()
})

test('saved keyword actions report API and clipboard failures', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'test-token')
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: () => Promise.reject(new Error('Denied')) } })
  })
  await mockAPI(page)
  await page.route('**/api/keyword-bank', route => route.fulfill({ json: [{ id, project_id: id, phrase: 'lunar age guide', keyword_type: 'long-tail', saved_at: project.created_at, is_done: false }] }))
  await page.route('**/api/keyword-bank/bulk-action', route => route.fulfill({ status: 503, json: { detail: 'Saving changes is temporarily unavailable' } }))
  await page.goto('/saved-keywords')
  await page.getByRole('checkbox').first().check()
  await page.getByRole('button', { name: 'Mark Done', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveText('Saving changes is temporarily unavailable')
  await page.getByRole('button', { name: 'Copy', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('Could not copy')
})

test('authority planner uses intent validation without sending a spoke target', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('token', 'test-token'))
  await mockAPI(page)
  let submitted: Record<string, unknown> | undefined
  await page.route('**/api/hub-spoke/build', route => {
    submitted = route.request().postDataJSON()
    return route.fulfill({ json: { keywords: ['lunar age'], history_id: id, clusters: { hubs: [], spokes: [], authority_coverage: { actual_spokes: 0, new_spokes: 0, existing_spokes: 0, status: 'validated', message: 'No additional distinct task was established.', discovery_status: 'unavailable' } } } })
  })
  await page.goto('/hub-spoke')
  await page.locator('input[type=file]').setInputFiles({ name: 'keywords.txt', mimeType: 'text/plain', buffer: Buffer.from('lunar age\nchinese age') })
  await page.getByRole('button', { name: 'Build topical map' }).click()
  await expect(page.getByText('0 spokes', { exact: true })).toBeVisible()
  await expect(page.getByLabel('Target spokes', { exact: true })).toHaveCount(0)
  await expect(page.getByText('Topic discovery was unavailable; this map uses the supplied inventory.', { exact: true })).toBeVisible()
  expect(submitted).not.toHaveProperty('target_spokes')
})
