import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api } from '../lib/api'
import { downloadText } from '../lib/hubSpoke'
import { Card } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import {
  ArrowLeft,
  Check,
  ClipboardCheck,
  Copy,
  Download,
  Loader2,
  PencilLine,
  Rocket,
  RotateCcw,
  Search,
} from 'lucide-react'


type IntentResponse = {
  intent: string
  competitors: string[]
}

type PromptResponse = {
  prompt: string
  attempts: number
  audit_score: number | null
}

const CHECKLIST = [
  { n: 1 as const, title: 'Input', note: 'Keyword + competitor survey' },
  { n: 2 as const, title: 'Verify intent', note: 'AI-deduced intent sign-off' },
  { n: 3 as const, title: 'Master prompt', note: 'Blueprint document' },
]

const inputClassName =
  'w-full rounded border border-line bg-ink px-3 py-2.5 font-mono text-sm text-text placeholder:text-muted/60 focus:border-amber focus:outline-none'

const labelClassName =
  'mb-1 block font-mono text-xs uppercase tracking-[0.14em] text-muted'

export default function WebsitePromptGenerator() {
  const [keyword, setKeyword] = useState('')
  const [manualCompetitors, setManualCompetitors] = useState('')
  const [intent, setIntent] = useState('')
  const [analyzedCompetitors, setAnalyzedCompetitors] = useState<string[]>([])

  const [generatedPrompt, setGeneratedPrompt] = useState<PromptResponse | null>(null)

  const [copied, setCopied] = useState(false)
  const [step, setStep] = useState<1 | 2 | 3>(1)

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
      return api.postAI<PromptResponse>('/website-prompts/generate', {
        keyword,
        intent,
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

  const promptFileName = () => {
    const slug = keyword.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'master-prompt'
    return `${slug}-master-prompt.md`
  }

  const renderChecklist = () => (
    <ol className="mx-auto mb-8 flex max-w-4xl flex-col gap-3 sm:flex-row">
      {CHECKLIST.map(({ n, title, note }) => {
        const done = step > n
        const current = step === n
        return (
          <li
            key={n}
            aria-current={current ? 'step' : undefined}
            className={[
              'flex flex-1 items-center gap-3 rounded-lg px-4 py-3',
              current
                ? 'border-2 border-amber bg-raised'
                : done
                  ? 'border border-line bg-panel'
                  : 'border-2 border-dashed border-line',
            ].join(' ')}
          >
            <span
              className={[
                'font-mono text-sm font-bold',
                done ? 'text-green' : current ? 'text-amber' : 'text-muted',
              ].join(' ')}
            >
              {String(n).padStart(2, '0')}
            </span>
            <span className="flex-1">
              <span
                className={[
                  'block font-display text-sm font-semibold',
                  done || current ? 'text-text' : 'text-muted',
                ].join(' ')}
              >
                {title}
              </span>
              <span className="block font-mono text-xs text-muted">{note}</span>
            </span>
            {done ? (
              <span className="stamp stamp-green">
                <Check className="h-3 w-3" />
                Checked
              </span>
            ) : current ? (
              <span className="stamp stamp-amber">Current</span>
            ) : (
              <span className="stamp stamp-muted">Pending</span>
            )}
          </li>
        )
      })}
    </ol>
  )

  const renderStep1 = () => (
    <Card className="mx-auto max-w-3xl p-6">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <p className="annotation">Sheet 01 — drafting instruments · input</p>
        <span className="stamp stamp-amber">
          <Search className="h-3 w-3" />
          Step 01
        </span>
      </div>

      <div className="mb-6">
        <h2 className="font-display text-xl font-bold text-text">Astro Launchpad</h2>
        <p className="annotation annotation--leading mt-2">
          Lay down the keyword and the competitor sites to survey. The auditor reads every
          homepage before the intent is deduced.
        </p>
      </div>

      <div className="space-y-5">
        <div>
          <label htmlFor="lp-keyword" className={labelClassName}>
            Main Keyword <span className="text-red">*</span>
          </label>
          <input
            id="lp-keyword"
            type="text"
            className={inputClassName}
            placeholder="e.g. mortgage calculator"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
        </div>

        <div>
          <label htmlFor="lp-competitors" className={labelClassName}>
            Manual Competitors <span className="normal-case tracking-normal">(optional)</span>
          </label>
          <p className="annotation mb-2">
            Leave blank to automatically scrape Google for the top 5 competitors — one URL per line.
          </p>
          <textarea
            id="lp-competitors"
            className={inputClassName}
            placeholder={'https://example.com\nhttps://example2.com'}
            rows={4}
            value={manualCompetitors}
            onChange={(e) => setManualCompetitors(e.target.value)}
          />
        </div>

        <Button
          onClick={() => analyzeIntentMutation.mutate()}
          disabled={analyzeIntentMutation.isPending || !keyword.trim()}
          className="w-full"
          size="lg"
        >
          {analyzeIntentMutation.isPending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Scraping homepages &amp; analyzing intent…
            </>
          ) : (
            <>
              <Rocket className="h-4 w-4" />
              Analyze intent
            </>
          )}
        </Button>

        {analyzeIntentMutation.isError && (
          <p role="alert" className="annotation !text-red">
            {String(analyzeIntentMutation.error)}
          </p>
        )}
      </div>
    </Card>
  )

  const renderStep2 = () => (
    <Card className="mx-auto max-w-3xl p-6">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <p className="annotation">Sheet 02 — verify intent · annotated drawing</p>
        <span className="stamp stamp-amber">Step 02</span>
      </div>

      <div className="mb-6">
        <h2 className="font-display text-xl font-bold text-text">Verify intent</h2>
        <p className="annotation annotation--leading mt-2">
          Competitor survey complete — {analyzedCompetitors.length}{' '}
          {analyzedCompetitors.length === 1 ? 'site' : 'sites'} scraped. The deduced intent is
          marked up below; amend it before sign-off.
        </p>
      </div>

      <div className="mb-6">
        <p className={labelClassName}>Scraped competitors</p>
        <ul className="space-y-1.5">
          {analyzedCompetitors.map((url) => (
            <li key={url} className="rounded border border-line bg-ink px-3 py-1.5 font-mono text-xs">
              <a href={url} target="_blank" rel="noopener noreferrer" className="text-amber hover:underline">
                {url}
              </a>
            </li>
          ))}
        </ul>
      </div>

      <div className="space-y-5">
        <div>
          <label htmlFor="lp-intent" className={labelClassName}>
            <span className="inline-flex items-center gap-1.5">
              <PencilLine className="h-3 w-3 text-amber" />
              Deduced intent — editable
            </span>
          </label>
          <textarea
            id="lp-intent"
            className={inputClassName}
            rows={6}
            value={intent}
            onChange={(e) => setIntent(e.target.value)}
          />
          <p className="annotation mt-2">
            Hand-edits here flow straight into the master prompt draft.
          </p>
        </div>

        <div className="flex gap-3">
          <Button
            variant="draft"
            onClick={() => setStep(1)}
            disabled={generatePromptMutation.isPending}
          >
            <ArrowLeft className="h-4 w-4" />
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
                Auditor is checking prompt quality…
              </>
            ) : (
              <>
                <ClipboardCheck className="h-4 w-4" />
                Confirm intent &amp; generate prompt
              </>
            )}
          </Button>
        </div>

        {generatePromptMutation.isError && (
          <p role="alert" className="annotation !text-red">
            {String(generatePromptMutation.error)}
          </p>
        )}
      </div>
    </Card>
  )

  const renderStep3 = () => {
    const score = generatedPrompt?.audit_score ?? null
    const passed = score != null && score >= 80

    return (
      <div className="mx-auto max-w-5xl">
        <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="annotation mb-3">Sheet 03 — master prompt · blueprint document</p>
            <h2 className="font-display text-2xl font-bold text-text">Website master prompt</h2>
            <p className="annotation annotation--leading mt-2">
              Ready to be copied into Claude Opus or any capable AI builder.
            </p>
          </div>
          <div className="flex flex-col items-end gap-3">
            {score == null ? (
              <span className="stamp stamp-muted px-5 py-2.5 text-base">Not audited</span>
            ) : (
              <span
                className={[
                  'stamp px-5 py-2.5 text-base',
                  passed ? 'stamp-green' : 'stamp-red',
                ].join(' ')}
              >
                <Check className="h-4 w-4" />
                Checked · {score}/100 · {passed ? 'Pass' : 'Review'}
              </span>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setGeneratedPrompt(null)
                setStep(1)
              }}
            >
              <RotateCcw className="h-4 w-4" />
              Start over
            </Button>
          </div>
        </div>

        <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div className="spec-plate">
            <p className="spec-label">Keyword</p>
            <p className="spec-value truncate !text-lg" title={keyword}>
              {keyword}
            </p>
          </div>
          <div className="spec-plate">
            <p className="spec-label">Auditor score</p>
            <p className="spec-value">{score ?? '—'}</p>
          </div>
          <div className="spec-plate">
            <p className="spec-label">Attempts</p>
            <p className="spec-value">{generatedPrompt?.attempts}</p>
          </div>
          <div className="spec-plate">
            <p className="spec-label">Verdict</p>
            <p className="spec-value !text-lg">
              {score == null ? 'Not audited' : passed ? 'Pass' : 'Review needed'}
            </p>
          </div>
        </div>

        <Card className="p-6">
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <Button onClick={() => copyToClipboard(generatedPrompt?.prompt || '')}>
              {copied ? (
                <>
                  <Check className="h-4 w-4 text-ink" />
                  Copied!
                </>
              ) : (
                <>
                  <Copy className="h-4 w-4" />
                  Copy prompt
                </>
              )}
            </Button>
            <Button
              variant="draft"
              onClick={() => downloadText(promptFileName(), generatedPrompt?.prompt || '')}
            >
              <Download className="h-4 w-4" />
              Download .md
            </Button>
            <p className="annotation ml-auto">Master prompt — final draft, signed off.</p>
          </div>

          <div className="whitespace-pre-wrap rounded border border-line bg-ink p-5 font-mono text-sm leading-7 text-text">
            {generatedPrompt?.prompt}
          </div>
        </Card>
      </div>
    )
  }

  return (
    <div className="bg-blueprint p-6">
      <p className="annotation mx-auto mb-2 max-w-4xl">
        Astro Launchpad — pre-flight checklist
      </p>
      {renderChecklist()}
      {step === 1 && renderStep1()}
      {step === 2 && renderStep2()}
      {step === 3 && renderStep3()}
    </div>
  )
}
