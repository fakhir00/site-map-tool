import { useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { api, type KeywordBankEntry } from '../lib/api'
import { Card } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Check, Copy, FileSearch, Loader2, Sparkles } from 'lucide-react'
import { SavedKeywordsTable } from '../components/SavedKeywordsTable'

type IntentResponse = {
  intent: string
  competitors: string[]
}

type PromptResponse = {
  prompt: string
  attempts: number
  audit_score: number | null
}

type PromptSection = {
  title: string
  body: string
}

const SECTION_DISPLAY: Record<string, string> = {
  'page goal': 'Page goal',
  'must cover terms': 'Must-cover terms',
  'structure outline': 'Structure outline',
  'seo notes': 'SEO notes',
}

const sectionHeadingRe = /^(?:#{1,4}\s*)?(page goal|must[-\s]?cover terms|structure outline|seo notes)\s*:?\s*$/i

/** Split a generated master prompt into labeled spec sections on known headings. */
function parsePromptSections(prompt: string): PromptSection[] {
  const sections: PromptSection[] = []
  let current: PromptSection | null = null
  for (const line of prompt.split('\n')) {
    const match = line.match(sectionHeadingRe)
    if (match) {
      const key = match[1].toLowerCase().replace(/[-\s]+/g, ' ')
      current = { title: SECTION_DISPLAY[key] ?? match[1], body: '' }
      sections.push(current)
    } else if (current) {
      current.body += `${line}\n`
    } else if (line.trim()) {
      current = { title: 'Spec notes', body: `${line}\n` }
      sections.push(current)
    }
  }
  if (sections.length === 0) return [{ title: 'Master prompt', body: prompt }]
  return sections
}

/** Pull individual must-cover terms out of a section body for mono chips. */
function splitTerms(body: string): { chips: string[]; notes: string[] } {
  const chips: string[] = []
  const notes: string[] = []
  for (const raw of body.split('\n')) {
    const line = raw.replace(/^[\s>*#\-–•\d.)]+/, '').trim()
    if (!line) continue
    const parts = line.includes(',')
      ? line.split(',').map((part) => part.trim()).filter(Boolean)
      : [line]
    for (const part of parts) {
      if (part.length <= 60 && !part.endsWith('.')) chips.push(part)
      else notes.push(part)
    }
  }
  return { chips, notes }
}

const fieldLabel = 'font-mono text-xs uppercase tracking-[0.14em] text-muted'
const inputClass =
  'w-full rounded-lg border border-line bg-ink px-3 py-2 text-sm text-text placeholder:text-muted/60 focus:border-amber focus:outline-none'

export default function GapPageGenerator() {
  const [searchParams] = useSearchParams()
  const initialKeyword = searchParams.get('keyword') || ''
  const location = useLocation()
  const navigate = useNavigate()
  const [architectureBrief, setArchitectureBrief] = useState<string>(location.state?.architectureBrief || '')

  const [keyword, setKeyword] = useState(initialKeyword)
  const [manualCompetitors, setManualCompetitors] = useState('')
  const [intent, setIntent] = useState('')
  const [analyzedCompetitors, setAnalyzedCompetitors] = useState<string[]>([])

  const [generatedPrompt, setGeneratedPrompt] = useState<PromptResponse | null>(null)

  const [copied, setCopied] = useState(false)
  const [step, setStep] = useState<1 | 2 | 3>(1)

  const { data: allKeywords = [], isLoading } = useQuery({
    queryKey: ['keyword-bank'],
    queryFn: () => api.get<KeywordBankEntry[]>('/keyword-bank'),
  })

  const keywords = allKeywords.filter(kw => kw.notes === '#tool')

  const analyzeIntentMutation = useMutation({
    mutationFn: async () => {
      const competitorsList = manualCompetitors
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)

      return api.postAI<IntentResponse>('/website-prompts/analyze-intent', {
        keyword,
        manual_competitors: competitorsList.length > 0 ? competitorsList : undefined,
      })
    },
    onSuccess: (data) => {
      setIntent(data.intent)
      setAnalyzedCompetitors(data.competitors)
      setStep(2)
    },
  })

  const generatePromptMutation = useMutation({
    mutationFn: async () => {
      return api.postAI<PromptResponse>('/website-prompts/generate-gap-page', {
        keyword,
        intent: [intent, architectureBrief].filter(Boolean).join('\n\nArchitecture requirements:\n'),
        competitors: analyzedCompetitors,
      })
    },
    onSuccess: (data) => {
      setGeneratedPrompt(data)
      setStep(3)
    },
  })

  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy text: ', err)
    }
  }

  const renderWorkOrderHeader = () => (
    <div className="flex flex-wrap items-center justify-between gap-4 border-b border-line pb-5">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-line bg-ink text-amber">
          <Sparkles className="h-5 w-5" />
        </div>
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.18em] text-amber">Work order · № BP-01</p>
          <p className="annotation mt-1">Target keyword + intent, recorded on the sheet</p>
        </div>
      </div>
      <div className="inline-flex items-center rounded-lg border border-line bg-ink p-1" role="group" aria-label="Page intent">
        <span className="rounded-md bg-amber px-4 py-1.5 font-mono text-xs font-semibold uppercase tracking-[0.14em] text-ink">
          Tool
        </span>
        <button
          type="button"
          onClick={() => navigate(`/write-blog?keyword=${encodeURIComponent(keyword)}`)}
          className="rounded-md px-4 py-1.5 font-mono text-xs uppercase tracking-[0.14em] text-muted transition-colors hover:text-text"
        >
          Blog
        </button>
      </div>
    </div>
  )

  const renderStep1 = () => (
    <Card className="p-6">
      {renderWorkOrderHeader()}

      <div className="mt-6 space-y-6">
        <div>
          <label className={fieldLabel} htmlFor="bp-keyword">
            ▸ Main keyword <span className="text-red">*</span>
          </label>
          <input
            id="bp-keyword"
            type="text"
            className={`${inputClass} mt-2 font-mono`}
            placeholder="e.g. mortgage calculator"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
        </div>

        <div>
          <label className={fieldLabel} htmlFor="bp-competitors">
            ▸ Competitor sources
          </label>
          <p className="annotation mt-2">Leave blank — we auto-scrape the top 5 from Google.</p>
          <textarea
            id="bp-competitors"
            className={`${inputClass} mt-2 font-mono`}
            placeholder="https://example.com&#10;https://example2.com"
            rows={4}
            value={manualCompetitors}
            onChange={(e) => setManualCompetitors(e.target.value)}
          />
        </div>

        {architectureBrief && (
          <div>
            <label className={fieldLabel} htmlFor="bp-brief">
              ▸ Architecture brief
            </label>
            <textarea
              id="bp-brief"
              value={architectureBrief}
              onChange={event => setArchitectureBrief(event.target.value)}
              maxLength={12000}
              rows={6}
              className={`${inputClass} mt-2 font-mono`}
            />
          </div>
        )}

        <Button
          onClick={() => analyzeIntentMutation.mutate()}
          disabled={analyzeIntentMutation.isPending || !keyword.trim()}
          className="w-full"
          size="lg"
        >
          {analyzeIntentMutation.isPending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Scraping homepages & analyzing intent…
            </>
          ) : (
            'Analyze intent'
          )}
        </Button>

        {analyzeIntentMutation.isError && (
          <p role="alert" className="rounded-lg border border-red/50 bg-red/10 p-3 font-mono text-xs text-red">
            {String(analyzeIntentMutation.error)}
          </p>
        )}
      </div>
    </Card>
  )

  const renderStep2 = () => (
    <Card className="p-6">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-line pb-5">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.18em] text-amber">Work order · № BP-01</p>
          <h2 className="mt-1 font-display text-xl font-bold">Verify intent</h2>
          <p className="annotation mt-1">We scraped the sources. Deduced intent below — amend before drafting.</p>
        </div>
        <span className="stamp stamp-amber">Step 02</span>
      </div>

      <div className="mt-6">
        <p className={fieldLabel}>▸ Source list — {analyzedCompetitors.length} annotated</p>
        <ol className="mt-3 space-y-2">
          {analyzedCompetitors.map((url, index) => (
            <li key={url} className="annotation annotation--leading flex items-baseline gap-2 rounded-lg border border-line bg-ink px-3 py-2">
              <span className="font-mono text-xs font-semibold text-amber">{String(index + 1).padStart(2, '0')}</span>
              <a href={url} target="_blank" rel="noopener noreferrer" className="break-all font-mono text-xs text-sky hover:text-amber hover:underline">
                {url}
              </a>
            </li>
          ))}
        </ol>
      </div>

      <div className="mt-6">
        <label className={fieldLabel} htmlFor="bp-intent">
          ▸ Deduced intent
        </label>
        <textarea
          id="bp-intent"
          className={`${inputClass} mt-2`}
          rows={6}
          value={intent}
          onChange={(e) => setIntent(e.target.value)}
        />
      </div>

      <div className="mt-6 flex gap-3">
        <Button
          variant="secondary"
          onClick={() => setStep(1)}
          disabled={generatePromptMutation.isPending}
          className="flex-1"
        >
          Back
        </Button>
        <Button
          onClick={() => generatePromptMutation.mutate()}
          disabled={generatePromptMutation.isPending || !intent.trim()}
          className="flex-[2]"
          size="lg"
        >
          {generatePromptMutation.isPending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Generating tool prompt…
            </>
          ) : (
            'Confirm intent & generate prompt'
          )}
        </Button>
      </div>

      {generatePromptMutation.isError && (
        <p role="alert" className="mt-4 rounded-lg border border-red/50 bg-red/10 p-3 font-mono text-xs text-red">
          {String(generatePromptMutation.error)}
        </p>
      )}
    </Card>
  )

  const renderStep3 = () => {
    const score = generatedPrompt?.audit_score ?? null
    const sections = parsePromptSections(generatedPrompt?.prompt || '')

    return (
      <Card className="p-6">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-line pb-5">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.18em] text-amber">Work order · № BP-01</p>
            <h2 className="mt-1 font-display text-xl font-bold">Build Page prompt</h2>
            <p className="annotation mt-1">Master prompt, drafted as a spec sheet — ready for a capable AI builder.</p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setGeneratedPrompt(null)
              setStep(1)
            }}
            className="font-mono text-xs uppercase tracking-[0.14em]"
          >
            Start over
          </Button>
        </div>

        <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div className="spec-plate">
            <p className="spec-label">Keyword</p>
            <p className="spec-value truncate text-lg" title={keyword}>{keyword}</p>
          </div>
          <div className="spec-plate">
            <p className="spec-label">Auditor score</p>
            <p className="spec-value">{score ?? '–'}</p>
          </div>
          <div className="spec-plate">
            <p className="spec-label">Attempts</p>
            <p className="spec-value">{generatedPrompt?.attempts ?? '–'}</p>
          </div>
          <div className="spec-plate">
            <p className="spec-label">Verdict</p>
            <p className="spec-value text-lg">
              {score == null ? 'Not audited' : score >= 80 ? 'Pass' : 'Review needed'}
            </p>
          </div>
        </div>

        <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
          {score == null ? (
            <span className="stamp stamp-muted">Not audited</span>
          ) : score >= 80 ? (
            <span className="stamp stamp-green">Checked · {score}/100</span>
          ) : (
            <span className="stamp stamp-amber">Review needed · {score}/100</span>
          )}
          <Button
            onClick={() => copyToClipboard(generatedPrompt?.prompt || '')}
            size="lg"
          >
            {copied ? (
              <>
                <Check className="h-4 w-4" />
                Copied!
              </>
            ) : (
              <>
                <Copy className="h-4 w-4" />
                Copy prompt
              </>
            )}
          </Button>
        </div>

        <div className="mt-6 divide-y divide-[rgba(30,58,95,0.6)] rounded-xl border border-line bg-ink">
          {sections.map((section, sectionIndex) => {
            if (section.title === 'Must-cover terms') {
              const { chips, notes } = splitTerms(section.body)
              return (
                <div key={sectionIndex} className="p-5">
                  <p className={fieldLabel}>▸ {section.title}</p>
                  {chips.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {chips.map((term, termIndex) => (
                        <span
                          key={termIndex}
                          className="rounded border border-line bg-panel px-2 py-1 font-mono text-xs text-text"
                        >
                          {term}
                        </span>
                      ))}
                    </div>
                  )}
                  {notes.map((note, noteIndex) => (
                    <p key={`n${noteIndex}`} className="mt-2 whitespace-pre-wrap text-sm leading-6 text-muted">
                      {note}
                    </p>
                  ))}
                </div>
              )
            }
            return (
              <div key={sectionIndex} className="p-5">
                <p className={fieldLabel}>▸ {section.title}</p>
                <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-text">
                  {section.body.trim()}
                </p>
              </div>
            )
          })}
        </div>
      </Card>
    )
  }

  const renderPartsBin = () => (
    <section className="dashed-amber rounded-2xl bg-panel p-5">
      <p className="annotation">▸ Keyword bank — parts bin</p>
      <p className="mt-2 font-mono text-xs uppercase tracking-[0.14em] text-muted">
        Saved #tool keywords · hit Build on any row to load it onto this work order
      </p>
      <div className="mt-4">
        <SavedKeywordsTable
          keywords={keywords}
          isLoading={isLoading}
          actionIcon="build"
          onAction={(kw) => {
            setKeyword(kw.phrase)
            setArchitectureBrief('')
            window.scrollTo({ top: 0, behavior: 'smooth' })
          }}
        />
      </div>
    </section>
  )

  const stepStamp = (n: 1 | 2 | 3, label: string) => (
    <span key={n} className={`stamp ${step === n ? 'stamp-amber' : 'stamp-muted'}`}>
      {label}
    </span>
  )

  return (
    <div className="mx-auto max-w-6xl py-8">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="annotation">▸ Build page — work order sheet</p>
          <h1 className="mt-2 font-display text-3xl font-bold">Build Page</h1>
          <p className="mt-1 text-sm text-muted">
            Analyze competitors, verify intent, and draft a build-ready prompt for a single gap page.
          </p>
        </div>
        <div className="flex gap-2">
          {stepStamp(1, 'Step 01 · Draft')}
          {stepStamp(2, 'Step 02 · Verify')}
          {stepStamp(3, 'Step 03 · Spec')}
        </div>
      </div>

      {step === 1 ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
          {renderStep1()}
          <aside>{renderPartsBin()}</aside>
        </div>
      ) : (
        <div className="mx-auto max-w-3xl space-y-8">
          {step === 2 && renderStep2()}
          {step === 3 && renderStep3()}
          {renderPartsBin()}
        </div>
      )}

      <p className="annotation mt-8 flex items-center gap-2">
        <FileSearch className="h-3.5 w-3.5 text-amber" />
        Tool keywords from Gap Scan feed this work order — blog targets live in the Blog Writer lane.
      </p>
    </div>
  )
}
