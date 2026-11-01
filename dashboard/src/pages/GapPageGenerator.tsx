import { useState } from 'react'
import { useLocation, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { api, type KeywordBankEntry } from '../lib/api'
import { Card } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Badge } from '../components/ui/Badge'
import { Check, Copy, Loader2, Sparkles } from 'lucide-react'
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

const textareaClassName =
  'w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 placeholder:text-slate-400 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-site-sky dark:border-line dark:bg-raised dark:text-text dark:placeholder:text-muted/60'

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

  const verdictBadge =
    generatedPrompt?.audit_score == null
      ? { label: 'Not audited', variant: 'slate' as const }
      : generatedPrompt.audit_score >= 80
        ? { label: 'Pass', variant: 'green' as const }
        : { label: 'Review needed', variant: 'amber' as const }

  const renderStep1 = () => (
    <Card className="p-6">
      <div className="flex items-center gap-3 mb-6">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-site-sky/15 text-site-sky">
          <Sparkles className="h-5 w-5" />
        </div>
        <div>
          <h2 className="font-display text-xl font-bold text-slate-950 dark:text-text">Build Page</h2>
          <p className="text-sm text-slate-500 dark:text-muted">Analyze competitors and generate a targeted prompt for a single gap page.</p>
        </div>
      </div>

      <div className="space-y-5">
        <div>
          <label className="block text-sm font-medium text-slate-700 dark:text-text mb-1">
            Main Keyword <span className="text-signal-red">*</span>
          </label>
          <input
            type="text"
            className="flex h-10 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 placeholder:text-slate-400 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-site-sky dark:border-line dark:bg-raised dark:text-text dark:placeholder:text-muted/60"
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
            className={`${textareaClassName} font-mono`}
            placeholder="https://example.com&#10;https://example2.com"
            rows={4}
            value={manualCompetitors}
            onChange={(e) => setManualCompetitors(e.target.value)}
          />
        </div>

        {architectureBrief && <label className="block text-sm font-medium text-slate-700 dark:text-text">Architecture brief<textarea aria-label="Architecture brief" value={architectureBrief} onChange={event => setArchitectureBrief(event.target.value)} maxLength={12000} rows={8} className={`${textareaClassName} mt-2`} /></label>}
        <Button
          onClick={() => analyzeIntentMutation.mutate()}
          disabled={analyzeIntentMutation.isPending || !keyword.trim()}
          className="w-full"
          size="lg"
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
          <div className="p-3 rounded-lg text-sm border border-rose-200 bg-rose-50 text-rose-700 dark:border-signal-red/30 dark:bg-signal-red/10 dark:text-signal-red">
            {String(analyzeIntentMutation.error)}
          </div>
        )}
      </div>
    </Card>
  )

  const renderStep2 = () => (
    <Card className="p-6">
      <div className="mb-6">
        <h2 className="font-display text-xl font-bold text-slate-950 dark:text-text mb-2">Verify Intent</h2>
        <p className="text-sm text-slate-500 dark:text-muted">
          We scraped the competitors. Here is the deduced intent of this keyword.
          Modify it if needed before generating the Master Prompt.
        </p>
      </div>

      <div className="mb-6">
        <h3 className="text-sm font-semibold text-slate-800 dark:text-text mb-2">Scraped Competitors:</h3>
        <ul className="list-disc pl-5 text-sm text-slate-600 dark:text-muted space-y-1">
          {analyzedCompetitors.map(url => (
            <li key={url}><a href={url} target="_blank" rel="noopener noreferrer" className="text-site-sky hover:underline">{url}</a></li>
          ))}
        </ul>
      </div>

      <div className="space-y-5">
        <div>
          <label className="block text-sm font-medium text-slate-700 dark:text-text mb-1">
            Deduced Intent
          </label>
          <textarea
            className={textareaClassName}
            rows={6}
            value={intent}
            onChange={(e) => setIntent(e.target.value)}
          />
        </div>

        <div className="flex gap-3">
          <Button
            variant="secondary"
            onClick={() => setStep(1)}
            disabled={generatePromptMutation.isPending}
            className="flex-1"
            size="lg"
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
                Generating tool prompt...
              </>
            ) : (
              'Confirm Intent & Generate Prompt'
            )}
          </Button>
        </div>

        {generatePromptMutation.isError && (
          <div className="p-3 rounded-lg text-sm border border-rose-200 bg-rose-50 text-rose-700 dark:border-signal-red/30 dark:bg-signal-red/10 dark:text-signal-red">
            {String(generatePromptMutation.error)}
          </div>
        )}
      </div>
    </Card>
  )

  const renderStep3 = () => (
    <Card className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="font-display text-lg font-bold text-slate-950 dark:text-text">Build Page Prompt</h3>
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
        <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm dark:border-line dark:bg-raised">
          <p className="text-slate-500 dark:text-muted">Keyword</p>
          <p className="text-base font-bold text-slate-950 dark:text-text truncate font-mono" title={keyword}>{keyword}</p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm dark:border-line dark:bg-raised">
          <p className="text-slate-500 dark:text-muted">Auditor Score</p>
          <p className="text-base font-bold text-slate-950 dark:text-text font-mono">{generatedPrompt?.audit_score ?? '-'}</p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm dark:border-line dark:bg-raised">
          <p className="text-slate-500 dark:text-muted">Attempts</p>
          <p className="text-base font-bold text-slate-950 dark:text-text font-mono">{generatedPrompt?.attempts}</p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm dark:border-line dark:bg-raised">
          <p className="text-slate-500 dark:text-muted mb-1">Verdict</p>
          <Badge variant={verdictBadge.variant}>{verdictBadge.label}</Badge>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white dark:border-line dark:bg-raised">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 dark:border-line px-5 py-4">
          <div className="flex items-center gap-3">
            <h4 className="font-display text-sm font-bold text-slate-950 dark:text-text">Checked prompt</h4>
            {generatedPrompt?.audit_score != null ? (
              <Badge variant="green">Checked · {generatedPrompt.audit_score}/100</Badge>
            ) : (
              <Badge variant="slate">Not audited</Badge>
            )}
          </div>
          <Button
            size="sm"
            onClick={() => copyToClipboard(generatedPrompt?.prompt || '')}
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

        <div className="p-5">
          <div className="whitespace-pre-wrap text-sm leading-7 text-slate-800 dark:text-text font-mono rounded-lg border border-slate-100 dark:border-line bg-slate-50 dark:bg-blueprint-deep p-4">
            {generatedPrompt?.prompt}
          </div>
        </div>
      </div>
    </Card>
  )

  return (
    <div className="mx-auto max-w-3xl py-8 space-y-8">
      <div>
        {step === 1 && renderStep1()}
        {step === 2 && renderStep2()}
        {step === 3 && renderStep3()}
      </div>

      {/* Keyword Bank from Gap Scan */}
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
  )
}
