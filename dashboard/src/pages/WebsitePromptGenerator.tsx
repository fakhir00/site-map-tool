import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api } from '../lib/api'
import { cn } from '../lib/utils'
import { Card } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Badge } from '../components/ui/Badge'
import { Input } from '../components/ui/Input'
import { Check, Copy, Download, Loader2, Sparkles } from 'lucide-react'


type IntentResponse = {
  intent: string
  competitors: string[]
}

type PromptResponse = {
  prompt: string
  attempts: number
  audit_score: number | null
}

const STEP_LABELS = ['Input', 'Verify intent', 'Master Prompt'] as const

const inputClassName =
  'w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 placeholder:text-slate-400 focus:border-site-sky focus:outline-none focus:ring-1 focus:ring-site-sky dark:border-line dark:bg-raised dark:text-text dark:placeholder:text-muted/60'

const errorClassName =
  'rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700 dark:border-signal-red/30 dark:bg-signal-red/10 dark:text-signal-red'

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

  const downloadMarkdown = () => {
    const text = generatedPrompt?.prompt ?? ''
    if (!text) return
    const blob = new Blob([text], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${keyword.trim() || 'master-blueprint'}.md`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }

  const renderStepper = () => (
    <div className={cn('mx-auto', step === 3 ? 'max-w-5xl' : 'max-w-3xl')}>
      <Card className="p-4">
        <ol className="flex items-center">
          {STEP_LABELS.map((label, i) => {
            const stepNum = (i + 1) as 1 | 2 | 3
            const isActive = step === stepNum
            const isDone = step > stepNum
            return (
              <li key={label} className="flex flex-1 items-center last:flex-none">
                <div className="flex items-center gap-2.5">
                  <span
                    className={cn(
                      'flex h-8 w-8 items-center justify-center rounded-full border font-mono text-sm font-bold',
                      isActive && 'border-signal-amber bg-signal-amber text-blueprint-deep',
                      isDone && 'border-site-sky/40 bg-site-sky/15 text-site-sky',
                      !isActive && !isDone && 'border-line bg-raised text-muted',
                    )}
                  >
                    {isDone ? <Check className="h-4 w-4" /> : stepNum}
                  </span>
                  <span className={cn('text-sm', isActive ? 'font-semibold text-text' : 'text-muted')}>
                    {label}
                  </span>
                </div>
                {i < STEP_LABELS.length - 1 && (
                  <div className={cn('mx-3 h-px flex-1', isDone ? 'bg-site-sky/40' : 'bg-line')} />
                )}
              </li>
            )
          })}
        </ol>
      </Card>
    </div>
  )

  const renderStep1 = () => (
    <Card className="max-w-3xl mx-auto mt-8 p-6">
      <div className="flex items-center gap-3 mb-6">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-sky-100 text-sky-700 dark:bg-site-sky/10 dark:text-site-sky">
          <Sparkles className="h-5 w-5" />
        </div>
        <div>
          <h2 className="font-display text-xl font-bold text-slate-950 dark:text-text">Astro Launchpad</h2>
          <p className="text-sm text-slate-500 dark:text-muted">Analyze competitors and generate a unified master prompt.</p>
        </div>
      </div>

      <div className="space-y-5">
        <div>
          <label className="block text-sm font-medium text-slate-700 dark:text-text mb-1">
            Main Keyword <span className="text-signal-red">*</span>
          </label>
          <Input
            type="text"
            placeholder="e.g. mortgage calculator"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 dark:text-text mb-1">
            Manual Competitors (Optional)
          </label>
          <p className="text-xs text-slate-500 dark:text-muted mb-2">Leave blank to automatically scrape Google for the top 5 competitors.</p>
          <textarea
            className={cn(inputClassName, 'font-mono')}
            placeholder="https://example.com&#10;https://example2.com"
            rows={4}
            value={manualCompetitors}
            onChange={(e) => setManualCompetitors(e.target.value)}
          />
        </div>

        <Button
          variant="primary"
          className="w-full"
          onClick={() => analyzeIntentMutation.mutate()}
          disabled={analyzeIntentMutation.isPending || !keyword.trim()}
        >
          {analyzeIntentMutation.isPending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Scraping Homepages & Analyzing Intent...
            </>
          ) : (
            'Analyze Intent'
          )}
        </Button>

        {analyzeIntentMutation.isError && (
          <div className={errorClassName}>
            {String(analyzeIntentMutation.error)}
          </div>
        )}
      </div>
    </Card>
  )

  const renderStep2 = () => (
    <Card className="max-w-3xl mx-auto mt-8 p-6">
      <div className="mb-6">
        <h2 className="font-display text-xl font-bold text-slate-950 dark:text-text mb-2">Verify Intent</h2>
        <p className="text-sm text-slate-500 dark:text-muted">
          We scraped the competitors. Here is the deduced intent of this keyword.
          Modify it if needed before generating the Master Prompt.
        </p>
      </div>

      <div className="mb-6 rounded-lg border border-line bg-raised p-4">
        <h3 className="text-sm font-semibold text-slate-800 dark:text-text mb-2">Scraped Competitors:</h3>
        <ul className="list-disc pl-5 text-sm text-slate-600 dark:text-muted space-y-1">
          {analyzedCompetitors.map(url => (
            <li key={url}><a href={url} target="_blank" rel="noopener noreferrer" className="text-sky-600 hover:underline dark:text-site-sky">{url}</a></li>
          ))}
        </ul>
      </div>

      <div className="space-y-5">
        <div>
          <label className="block text-sm font-medium text-slate-700 dark:text-text mb-1">
            Deduced Intent
          </label>
          <textarea
            className={inputClassName}
            rows={6}
            value={intent}
            onChange={(e) => setIntent(e.target.value)}
          />
        </div>

        <div className="flex gap-3">
          <Button
            variant="secondary"
            className="flex-1"
            onClick={() => setStep(1)}
            disabled={generatePromptMutation.isPending}
          >
            Back
          </Button>
          <Button
            variant="primary"
            className="flex-[2]"
            onClick={() => generatePromptMutation.mutate()}
            disabled={generatePromptMutation.isPending || !intent.trim()}
          >
            {generatePromptMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Auditor is checking prompt quality...
              </>
            ) : (
              'Confirm Intent & Generate Prompt'
            )}
          </Button>
        </div>

        {generatePromptMutation.isError && (
          <div className={errorClassName}>
            {String(generatePromptMutation.error)}
          </div>
        )}
      </div>
    </Card>
  )

  const renderStep3 = () => {
    const score = generatedPrompt?.audit_score ?? null
    const verdict = score == null ? 'Not audited' : score >= 80 ? 'Pass' : 'Review needed'
    const verdictVariant = score == null ? 'slate' : score >= 80 ? 'green' : 'amber'

    return (
      <div className="max-w-5xl mx-auto mt-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="font-display text-2xl font-bold text-slate-950 dark:text-text">Website Master Prompt</h2>
            <p className="text-sm text-slate-500 dark:text-muted mt-1">Ready to be copied into Claude Opus or any capable AI builder.</p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setGeneratedPrompt(null)
              setStep(1)
            }}
          >
            Start Over
          </Button>
        </div>

        <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4 mb-6">
          <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 dark:border-line dark:bg-raised">
            <p className="text-slate-500 dark:text-muted">Keyword</p>
            <p className="text-base font-bold text-slate-950 dark:text-text truncate" title={keyword}>{keyword}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 dark:border-line dark:bg-raised">
            <p className="text-slate-500 dark:text-muted">Auditor Score</p>
            <p className="text-base font-bold text-slate-950 dark:text-text">{generatedPrompt?.audit_score ?? '-'}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 dark:border-line dark:bg-raised">
            <p className="text-slate-500 dark:text-muted">Attempts</p>
            <p className="text-base font-bold text-slate-950 dark:text-text">{generatedPrompt?.attempts}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 dark:border-line dark:bg-raised">
            <p className="text-slate-500 dark:text-muted">Verdict</p>
            <p className="mt-1"><Badge variant={verdictVariant}>{verdict}</Badge></p>
          </div>
        </div>

        <Card className="mb-6 p-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <span className="font-mono text-sm text-slate-600 dark:text-muted">
                {score == null ? 'Not audited' : `Checked · ${score}/100`}
              </span>
              <Badge variant={verdictVariant}>{verdict}</Badge>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="secondary" size="sm" onClick={downloadMarkdown} disabled={!generatedPrompt?.prompt}>
                <Download className="h-3.5 w-3.5" />
                Download .md
              </Button>
              <Button variant="primary" size="sm" onClick={() => copyToClipboard(generatedPrompt?.prompt || '')}>
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
          </div>
        </Card>

        <Card className="p-6">
          <div className="whitespace-pre-wrap rounded-lg border border-slate-100 bg-slate-50 p-4 font-mono text-sm leading-7 text-slate-800 dark:border-line dark:bg-raised dark:text-text">
            {generatedPrompt?.prompt}
          </div>
        </Card>
      </div>
    )
  }

  return (
    <div className="p-6">
      {renderStepper()}
      {step === 1 && renderStep1()}
      {step === 2 && renderStep2()}
      {step === 3 && renderStep3()}
    </div>
  )
}
