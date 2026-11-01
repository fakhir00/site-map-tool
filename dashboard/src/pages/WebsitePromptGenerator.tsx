import { Fragment, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api } from '../lib/api'
import { Card } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Badge } from '../components/ui/Badge'
import { Input } from '../components/ui/Input'
import { CountUp } from '../components/CountUp'
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Copy,
  Globe,
  Loader2,
  Rocket,
  RotateCcw,
  ShieldCheck,
  Sparkles,
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

const STEPS = [
  { id: 1, label: 'Your keyword' },
  { id: 2, label: 'Check the intent' },
  { id: 3, label: 'Master prompt' },
] as const

const textareaClasses =
  'w-full rounded-xl border border-line bg-raised px-3 py-2 text-sm text-ink placeholder:text-muted/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-glow-amber/40 focus-visible:border-glow-amber/60 transition-colors'

const labelClasses = 'mb-1.5 block text-sm font-semibold text-ink'

const hintClasses = 'mb-2 text-xs leading-relaxed text-muted'

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

  const renderStepIndicator = () => (
    <ol className="mt-8 flex items-center justify-center gap-1.5 sm:gap-2.5">
      {STEPS.map((s, i) => {
        const isActive = step === s.id
        const isDone = step > s.id
        return (
          <Fragment key={s.id}>
            {i > 0 && (
              <div
                aria-hidden
                className={`h-px w-6 sm:w-12 transition-colors ${
                  isDone || isActive ? 'bg-glow-amber/60' : 'bg-line'
                }`}
              />
            )}
            <li
              aria-current={isActive ? 'step' : undefined}
              className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold transition-all sm:px-4 sm:py-2 sm:text-sm ${
                isActive
                  ? 'border-glow-amber/50 bg-glow-amber/10 text-ink shadow-[0_0_24px_rgba(245,165,36,0.35)]'
                  : isDone
                    ? 'border-alive-green/30 bg-alive-green/10 text-ink'
                    : 'border-line bg-surface text-muted'
              }`}
            >
              <span
                className={`flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-bold ${
                  isActive
                    ? 'bg-glow-amber text-abyss'
                    : isDone
                      ? 'bg-alive-green text-abyss'
                      : 'border border-line bg-raised text-muted'
                }`}
              >
                {isDone ? <Check className="h-3 w-3" strokeWidth={3} /> : s.id}
              </span>
              <span className="hidden sm:inline">{s.label}</span>
              <span className="sm:hidden">{s.id}</span>
            </li>
          </Fragment>
        )
      })}
    </ol>
  )

  const renderError = (message: unknown) => (
    <div className="rounded-xl border border-warm-red/25 bg-warm-red/10 p-3.5 text-sm text-warm-red">
      Something went wrong — {String(message)}
    </div>
  )

  const renderStep1 = () => (
    <Card className="mx-auto max-w-2xl p-6 sm:p-8">
      <h2 className="font-display text-2xl font-bold sm:text-3xl">What do you want to rank for?</h2>
      <p className="mt-2 text-sm leading-relaxed text-muted">
        Give us the main keyword for the page. We&apos;ll peek at the sites already ranking for it and
        figure out what searchers actually want.
      </p>

      <div className="mt-7 space-y-5">
        <div>
          <label htmlFor="launchpad-keyword" className={labelClasses}>
            Main keyword <span className="text-warm-red">*</span>
          </label>
          <Input
            id="launchpad-keyword"
            placeholder="e.g. mortgage calculator"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            autoFocus
          />
        </div>

        <div>
          <label htmlFor="launchpad-competitors" className={labelClasses}>
            Competitor sites <Badge variant="slate" className="ml-1.5">optional</Badge>
          </label>
          <p className={hintClasses}>
            Leave this empty and we&apos;ll grab the top 5 from Google for you. One URL per line if
            you&apos;d rather pick them yourself.
          </p>
          <textarea
            id="launchpad-competitors"
            className={`${textareaClasses} font-mono`}
            placeholder={'https://example.com\nhttps://example2.com'}
            rows={4}
            value={manualCompetitors}
            onChange={(e) => setManualCompetitors(e.target.value)}
          />
        </div>

        <div className="pt-1">
          <Button
            variant="glow"
            size="lg"
            className="w-full"
            onClick={() => analyzeIntentMutation.mutate()}
            disabled={analyzeIntentMutation.isPending || !keyword.trim()}
          >
            {analyzeIntentMutation.isPending ? (
              <>
                <Loader2 className="h-5 w-5 animate-spin" />
                Reading competitor homepages…
              </>
            ) : (
              <>
                Analyze intent
                <ArrowRight className="h-5 w-5" />
              </>
            )}
          </Button>
          <p className="mt-3 text-center text-xs text-muted">
            This usually takes a few moments — we read the homepages so you don&apos;t have to.
          </p>
        </div>

        {analyzeIntentMutation.isPending && (
          <div className="space-y-3 rounded-xl border border-line bg-raised p-4">
            <p className="flex items-center gap-2 text-sm font-medium text-ink">
              <Loader2 className="h-4 w-4 animate-spin text-glow-amber" />
              Scraping homepages and reading the intent…
            </p>
            <div className="animate-shimmer h-2.5 rounded-full" />
            <div className="animate-shimmer h-2.5 w-11/12 rounded-full" />
            <div className="animate-shimmer h-2.5 w-4/5 rounded-full" />
          </div>
        )}

        {analyzeIntentMutation.isError && renderError(analyzeIntentMutation.error)}
      </div>
    </Card>
  )

  const renderStep2 = () => (
    <Card className="mx-auto max-w-2xl p-6 sm:p-8">
      <h2 className="font-display text-2xl font-bold sm:text-3xl">Does this sound right?</h2>
      <p className="mt-2 text-sm leading-relaxed text-muted">
        Here&apos;s what we found on the sites ranking for{' '}
        <span className="font-semibold text-ink">&ldquo;{keyword}&rdquo;</span>. Tweak anything that
        looks off — your master prompt is built from this.
      </p>

      <div className="mt-6">
        <p className="mb-2.5 font-mono text-[11px] font-semibold uppercase tracking-widest text-muted">
          We looked at these sites
        </p>
        <ul className="flex flex-wrap gap-2">
          {analyzedCompetitors.map((url) => (
            <li key={url}>
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                title={url}
                className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-line bg-raised px-3 py-1.5 text-xs text-muted transition-colors hover:border-glow-amber/40 hover:text-ink"
              >
                <Globe className="h-3.5 w-3.5 shrink-0 text-glow-amber" />
                <span className="max-w-52 truncate">{url}</span>
              </a>
            </li>
          ))}
        </ul>
      </div>

      <div className="mt-6">
        <label htmlFor="launchpad-intent" className={labelClasses}>
          Search intent <Badge variant="cyan" className="ml-1.5">AI-deduced</Badge>
        </label>
        <p className={hintClasses}>
          It&apos;s okay to edit this — make it say exactly what a searcher wants, in your words.
        </p>
        <textarea
          id="launchpad-intent"
          className={textareaClasses}
          rows={6}
          value={intent}
          onChange={(e) => setIntent(e.target.value)}
        />
      </div>

      <div className="mt-7 flex flex-col gap-3 sm:flex-row">
        <Button
          variant="ghost"
          size="lg"
          onClick={() => setStep(1)}
          disabled={generatePromptMutation.isPending}
          className="sm:w-36"
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
        <Button
          variant="glow"
          size="lg"
          className="flex-1"
          onClick={() => generatePromptMutation.mutate()}
          disabled={generatePromptMutation.isPending || !intent.trim()}
        >
          {generatePromptMutation.isPending ? (
            <>
              <Loader2 className="h-5 w-5 animate-spin" />
              The auditor is checking quality…
            </>
          ) : (
            <>
              <Sparkles className="h-5 w-5" />
              Build my master prompt
            </>
          )}
        </Button>
      </div>

      {generatePromptMutation.isError && (
        <div className="mt-5">{renderError(generatePromptMutation.error)}</div>
      )}
    </Card>
  )

  const renderStep3 = () => {
    const score = generatedPrompt?.audit_score
    const verdict =
      score == null ? (
        <Badge variant="slate">Not audited</Badge>
      ) : score >= 80 ? (
        <Badge variant="green">Passed</Badge>
      ) : (
        <Badge variant="amber">Review needed</Badge>
      )

    return (
      <div className="mx-auto max-w-3xl">
        <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="font-display text-2xl font-bold sm:text-3xl">
              Your master prompt is ready
            </h2>
            <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted">
              Paste it into Claude Opus or your favorite AI website builder. It&apos;s written to
              outrank the sites we just analyzed.
            </p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setGeneratedPrompt(null)
              setStep(1)
            }}
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Start over
          </Button>
        </div>

        <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Card className="p-4" lift={false}>
            <p className="font-mono text-[11px] font-semibold uppercase tracking-widest text-muted">
              Keyword
            </p>
            <p className="mt-1.5 truncate font-display text-base font-bold" title={keyword}>
              {keyword}
            </p>
          </Card>
          <Card className="p-4" lift={false}>
            <p className="flex items-center gap-1.5 font-mono text-[11px] font-semibold uppercase tracking-widest text-muted">
              <ShieldCheck className="h-3.5 w-3.5 text-soft-violet" />
              Auditor score
            </p>
            <p className="mt-1.5 font-display text-base font-bold">{score == null ? '–' : <CountUp value={score} duration={700} />}</p>
          </Card>
          <Card className="p-4" lift={false}>
            <p className="font-mono text-[11px] font-semibold uppercase tracking-widest text-muted">
              Attempts
            </p>
            <p className="mt-1.5 font-mono text-base font-bold">{generatedPrompt?.attempts}</p>
          </Card>
          <Card className="p-4" lift={false}>
            <p className="font-mono text-[11px] font-semibold uppercase tracking-widest text-muted">
              Verdict
            </p>
            <div className="mt-2">{verdict}</div>
          </Card>
        </div>

        <Card className="p-5 sm:p-7">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-glow-amber" />
              <h3 className="font-display text-lg font-bold">Master prompt</h3>
            </div>
            <Button
              variant="glow"
              size="md"
              onClick={() => copyToClipboard(generatedPrompt?.prompt || '')}
              className="min-w-40"
            >
              {copied ? (
                <>
                  <Check className="h-4 w-4" strokeWidth={3} />
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

          <div className="whitespace-pre-wrap rounded-xl border border-line bg-raised p-5 font-mono text-sm leading-7 text-ink/90">
            {generatedPrompt?.prompt}
          </div>

          <p className="mt-4 text-center text-xs text-muted">
            Tip: keep this prompt with your project — reusing it keeps new pages consistent.
          </p>
        </Card>
      </div>
    )
  }

  return (
    <div className="page-shell">
      <div className="warm-glow-bg pb-2 pt-4 text-center">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-glow-amber shadow-[0_0_32px_rgba(245,165,36,0.45)]">
          <Rocket className="h-7 w-7 text-abyss" />
        </div>
        <h1 className="mt-5 font-display text-4xl font-bold tracking-tight sm:text-5xl">
          Astro Launchpad
        </h1>
        <p className="mx-auto mt-3 max-w-xl text-sm leading-relaxed text-muted sm:text-base">
          Turn a keyword into a website-building master prompt in three easy steps. We study the
          competition, you confirm the plan, then you launch.
        </p>
        {renderStepIndicator()}
      </div>

      <div key={step} className="animate-fade-up mt-10">
        {step === 1 && renderStep1()}
        {step === 2 && renderStep2()}
        {step === 3 && renderStep3()}
      </div>
    </div>
  )
}
