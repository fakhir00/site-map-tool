import { useState } from 'react'
import { useLocation, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { api, type KeywordBankEntry } from '../lib/api'
import { Card } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { Badge } from '../components/ui/Badge'
import {
  ArrowLeft,
  Check,
  Copy,
  Globe,
  Hammer,
  Loader2,
  PencilLine,
  Radar,
  Sparkles,
  Wand2,
} from 'lucide-react'
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

/* ------------------------------------------------------------------ */
/*  Small presentational pieces (visuals only)                         */
/* ------------------------------------------------------------------ */

const STEP_LABELS = ['Analyze intent', 'Verify intent', 'Build page'] as const

function StepPills({ step }: { step: 1 | 2 | 3 }) {
  return (
    <div className="flex items-center gap-2" aria-hidden>
      {STEP_LABELS.map((label, i) => {
        const n = (i + 1) as 1 | 2 | 3
        const done = n < step
        const active = n === step
        return (
          <div key={label} className="flex items-center gap-2">
            {i > 0 && <div className={`h-px w-6 sm:w-10 ${done ? 'bg-glow-amber/50' : 'bg-line'}`} />}
            <div
              className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                active
                  ? 'border-glow-amber/40 bg-glow-amber/10 text-glow-amber'
                  : done
                    ? 'border-alive-green/30 bg-alive-green/10 text-alive-green'
                    : 'border-line bg-raised text-muted'
              }`}
            >
              <span
                className={`flex h-4 w-4 items-center justify-center rounded-full font-mono text-[10px] ${
                  active ? 'bg-glow-amber text-on-accent' : done ? 'bg-alive-green text-on-accent' : 'bg-overlay/10 text-muted'
                }`}
              >
                {done ? <Check className="h-2.5 w-2.5" strokeWidth={3.5} /> : n}
              </span>
              <span className="hidden sm:inline">{label}</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function ErrorNotice({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-warm-red/30 bg-warm-red/10 p-3.5 text-sm text-warm-red">
      {message}
    </div>
  )
}

function SkeletonBlock() {
  return (
    <Card lift={false} className="animate-fade-up p-6">
      <div className="animate-shimmer mb-4 h-6 w-1/3 rounded-lg" />
      <div className="space-y-3">
        <div className="animate-shimmer h-4 w-full rounded-md" />
        <div className="animate-shimmer h-4 w-11/12 rounded-md" />
        <div className="animate-shimmer h-4 w-4/5 rounded-md" />
        <div className="animate-shimmer h-4 w-2/3 rounded-md" />
      </div>
    </Card>
  )
}

/** Friendly pre-generation explainer — soft illustration + plain English + 3 steps. */
function HowItWorks() {
  const steps = [
    {
      icon: Radar,
      title: 'We study the winners',
      body: 'Your keyword goes through the top-ranking pages, so the prompt knows what Google already rewards.',
    },
    {
      icon: PencilLine,
      title: 'You check the intent',
      body: 'A plain-English read of what the searcher wants. Tweak it until it sounds right.',
    },
    {
      icon: Wand2,
      title: 'You get a build prompt',
      body: 'One copy-ready prompt, quality-checked, that any AI builder can turn into the page.',
    },
  ]
  return (
    <Card lift={false} className="animate-fade-up">
      <div className="flex flex-col items-center gap-6 sm:flex-row sm:gap-8">
        {/* soft inline illustration */}
        <svg viewBox="0 0 120 120" className="h-24 w-24 shrink-0" aria-hidden>
          <rect x="28" y="14" width="64" height="88" rx="12" fill="#161B26" stroke="#1C2230" />
          <rect x="38" y="28" width="44" height="8" rx="4" fill="#F5A524" opacity="0.85" />
          <rect x="38" y="44" width="44" height="5" rx="2.5" fill="#2A3348" />
          <rect x="38" y="54" width="34" height="5" rx="2.5" fill="#2A3348" />
          <rect x="38" y="64" width="40" height="5" rx="2.5" fill="#2A3348" />
          <circle cx="86" cy="84" r="14" fill="#F5A524" opacity="0.18" />
          <path
            d="M86 76l1.8 5.2 5.2 1.8-5.2 1.8-1.8 5.2-1.8-5.2-5.2-1.8 5.2-1.8z"
            fill="#F5A524"
          />
          <path
            d="M26 30l1.2 3.4 3.4 1.2-3.4 1.2-1.2 3.4-1.2-3.4-3.4-1.2 3.4-1.2z"
            fill="#A78BFA"
            opacity="0.9"
          />
          <circle cx="94" cy="26" r="3" fill="#34D399" opacity="0.8" />
        </svg>
        <div className="flex-1">
          <h2 className="font-display text-lg font-semibold text-ink">How this works</h2>
          <p className="mt-1 text-sm leading-6 text-muted">
            Nothing to figure out — just start with a keyword. The page practically builds its own blueprint.
          </p>
          <ul className="mt-4 space-y-3.5">
            {steps.map(({ icon: Icon, title, body }) => (
              <li key={title} className="flex gap-3">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-glow-amber/10 text-glow-amber">
                  <Icon className="h-4 w-4" />
                </span>
                <div>
                  <p className="text-sm font-semibold text-ink">{title}</p>
                  <p className="text-sm leading-5 text-muted">{body}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Card>
  )
}

const inputLabelClass = 'block text-sm font-semibold text-ink'
const requiredStar = (
  <span className="ml-1 font-mono text-xs text-glow-amber" aria-hidden>
    *
  </span>
)
const textareaClass =
  'w-full rounded-xl border border-line bg-raised px-3.5 py-2.5 text-sm leading-6 text-ink placeholder:text-muted/70 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-glow-amber/40 focus-visible:border-glow-amber/60'

export default function GapPageGenerator() {
  const [searchParams] = useSearchParams()
  const initialKeyword = searchParams.get('keyword') || ''
  const location = useLocation()
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

  const analyzing = analyzeIntentMutation.isPending
  const generating = generatePromptMutation.isPending

  const verdict = generatedPrompt?.audit_score == null
    ? { label: 'Not audited', variant: 'slate' as const }
    : generatedPrompt.audit_score >= 80
      ? { label: 'Pass', variant: 'teal' as const }
      : { label: 'Review needed', variant: 'amber' as const }

  const renderStep1 = () => (
    <div className="animate-fade-up space-y-6">
      <Card>
        <div className="mb-7 flex items-center gap-4">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-glow-amber/12 text-glow-amber shadow-[0_0_20px_rgba(245,165,36,0.25)]">
            <Hammer className="h-5 w-5" />
          </div>
          <div>
            <h2 className="font-display text-xl font-semibold text-ink">Build Page</h2>
            <p className="mt-0.5 text-sm text-muted">One keyword in, one build-ready prompt out.</p>
          </div>
        </div>

        <div className="space-y-6">
          <div>
            <label htmlFor="build-keyword" className={`${inputLabelClass} mb-2`}>
              Main keyword{requiredStar}
            </label>
            <Input
              id="build-keyword"
              placeholder="e.g. mortgage calculator"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              className="h-12 text-[15px]"
            />
          </div>

          <div>
            <label htmlFor="build-competitors" className={`${inputLabelClass} mb-2`}>
              Competitors <span className="font-normal text-muted">(optional)</span>
            </label>
            <p className="mb-2 text-[13px] leading-5 text-muted">
              Leave blank and we will pull the top 5 from Google ourselves. Or paste your own, one per line.
            </p>
            <textarea
              id="build-competitors"
              className={`${textareaClass} font-mono text-[13px]`}
              placeholder={'https://example.com\nhttps://example2.com'}
              rows={3}
              value={manualCompetitors}
              onChange={(e) => setManualCompetitors(e.target.value)}
            />
          </div>

          {architectureBrief && (
            <div>
              <label htmlFor="build-brief" className={`${inputLabelClass} mb-2`}>
                Architecture brief
              </label>
              <textarea
                id="build-brief"
                aria-label="Architecture brief"
                value={architectureBrief}
                onChange={(event) => setArchitectureBrief(event.target.value)}
                maxLength={12000}
                rows={6}
                className={textareaClass}
              />
            </div>
          )}

          <Button
            variant="glow"
            size="lg"
            className="w-full"
            onClick={() => analyzeIntentMutation.mutate()}
            disabled={analyzing || !keyword.trim()}
          >
            {analyzing ? (
              <>
                <Loader2 className="h-5 w-5 animate-spin" />
                Scraping homepages & analyzing intent…
              </>
            ) : (
              <>
                <Sparkles className="h-5 w-5" />
                Analyze intent
              </>
            )}
          </Button>

          {analyzeIntentMutation.isError && <ErrorNotice message={String(analyzeIntentMutation.error)} />}
        </div>
      </Card>

      {analyzing ? <SkeletonBlock /> : <HowItWorks />}
    </div>
  )

  const renderStep2 = () => (
    <div className="animate-fade-up space-y-6">
      <Card>
        <div className="mb-6">
          <div className="mb-1.5 flex items-center gap-2">
            <Badge variant="cyan" className="font-mono text-[11px] uppercase tracking-wide">
              AI read
            </Badge>
          </div>
          <h2 className="font-display text-xl font-semibold text-ink">Does this sound right?</h2>
          <p className="mt-1.5 max-w-lg text-sm leading-6 text-muted">
            We studied the competitors and guessed what people searching{' '}
            <span className="font-semibold text-ink">“{keyword}”</span> actually want. Tweak it before we build.
          </p>
        </div>

        {analyzedCompetitors.length > 0 && (
          <div className="mb-6 rounded-xl border border-line bg-raised/60 p-4">
            <p className="mb-2.5 font-mono text-[11px] font-semibold uppercase tracking-widest text-muted">
              Studied competitors
            </p>
            <ul className="flex flex-wrap gap-2">
              {analyzedCompetitors.map((url) => (
                <li key={url}>
                  <a
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex max-w-[260px] items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1.5 font-mono text-xs text-muted transition-colors hover:border-glow-amber/40 hover:text-ink"
                  >
                    <Globe className="h-3 w-3 shrink-0 text-glow-amber/70" />
                    <span className="truncate">{url.replace(/^https?:\/\//, '')}</span>
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="space-y-6">
          <div>
            <label htmlFor="build-intent" className={`${inputLabelClass} mb-2`}>
              The intent, in plain words
            </label>
            <textarea
              id="build-intent"
              className={textareaClass}
              rows={7}
              value={intent}
              onChange={(e) => setIntent(e.target.value)}
            />
          </div>

          <div className="flex flex-col-reverse gap-3 sm:flex-row">
            <Button
              variant="secondary"
              size="lg"
              className="sm:w-auto"
              onClick={() => setStep(1)}
              disabled={generating}
            >
              <ArrowLeft className="h-4 w-4" />
              Back
            </Button>
            <Button
              variant="glow"
              size="lg"
              className="flex-1"
              onClick={() => generatePromptMutation.mutate()}
              disabled={generating || !intent.trim()}
            >
              {generating ? (
                <>
                  <Loader2 className="h-5 w-5 animate-spin" />
                  Building your prompt…
                </>
              ) : (
                <>
                  <Wand2 className="h-5 w-5" />
                  Generate page prompt
                </>
              )}
            </Button>
          </div>

          {generatePromptMutation.isError && <ErrorNotice message={String(generatePromptMutation.error)} />}
        </div>
      </Card>

      {generating && <SkeletonBlock />}
    </div>
  )

  const renderStep3 = () => (
    <div className="animate-fade-up space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="font-display text-2xl font-semibold text-ink">Your page prompt is ready</h2>
          <p className="mt-1.5 text-sm text-muted">
            Drop it into Claude, ChatGPT, or any capable AI builder and ship the page.
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={() => { setGeneratedPrompt(null); setStep(1) }}>
          Start over
        </Button>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <Card lift={false} className="px-4 py-3.5">
          <p className="font-mono text-[11px] uppercase tracking-widest text-muted">Keyword</p>
          <p className="mt-1 truncate text-[15px] font-semibold text-ink" title={keyword}>{keyword}</p>
        </Card>
        <Card lift={false} className="px-4 py-3.5">
          <p className="font-mono text-[11px] uppercase tracking-widest text-muted">Quality score</p>
          <p className="mt-1 text-[15px] font-semibold text-ink">
            {generatedPrompt?.audit_score ?? <span className="text-muted">–</span>}
          </p>
        </Card>
        <Card lift={false} className="px-4 py-3.5">
          <p className="font-mono text-[11px] uppercase tracking-widest text-muted">Verdict</p>
          <div className="mt-1.5">
            <Badge variant={verdict.variant}>{verdict.label}</Badge>
          </div>
        </Card>
      </div>

      <Card lift={false} className="relative overflow-hidden p-0">
        <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-3.5">
          <p className="font-mono text-[11px] font-semibold uppercase tracking-widest text-muted">
            Build prompt
          </p>
          <Button
            variant={copied ? 'secondary' : 'glow'}
            size="sm"
            onClick={() => copyToClipboard(generatedPrompt?.prompt || '')}
            className={copied ? 'border-alive-green/30 text-alive-green' : ''}
          >
            {copied ? (
              <>
                <Check className="h-3.5 w-3.5" />
                Copied!
              </>
            ) : (
              <>
                <Copy className="h-3.5 w-3.5" />
                Copy prompt
              </>
            )}
          </Button>
        </div>
        <div className="max-h-[560px] overflow-y-auto whitespace-pre-wrap px-5 py-5 font-mono text-[13px] leading-7 text-ink/90">
          {generatedPrompt?.prompt}
        </div>
      </Card>
    </div>
  )

  return (
    <div className="page-shell warm-glow-bg">
      <div className="mx-auto max-w-3xl space-y-10">
        <header className="animate-fade-up space-y-5 pt-2">
          <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.2em] text-glow-amber">
            Build Page
          </p>
          <StepPills step={step} />
        </header>

        <main>
          {step === 1 && renderStep1()}
          {step === 2 && renderStep2()}
          {step === 3 && renderStep3()}
        </main>

        {/* Keyword Bank from Gap Scan */}
        <section>
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
        </section>
      </div>
    </div>
  )
}
