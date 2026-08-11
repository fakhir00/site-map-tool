import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { api } from '../lib/api'
import { Card } from '../components/ui/Card'
import { Check, Copy, Loader2, Sparkles } from 'lucide-react'


type IntentResponse = {
  intent: string
  competitors: string[]
}

type PromptResponse = {
  prompt: string
  attempts: number
  audit_score: number
}

export default function GapPageGenerator() {
  const [searchParams] = useSearchParams()
  const initialKeyword = searchParams.get('keyword') || ''

  const [keyword, setKeyword] = useState(initialKeyword)
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

      return api.post<IntentResponse>('/website-prompts/analyze-intent', {
        keyword,
        manual_competitors: competitorsList.length > 0 ? competitorsList : undefined,
      }, {
        timeoutMs: 120_000 // up to 2 mins for scraping
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
      return api.post<PromptResponse>('/website-prompts/generate-gap-page', {
        keyword,
        intent,
        competitors: analyzedCompetitors,
      }, {
        timeoutMs: 300_000 // 5 minutes max
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

  const renderStep1 = () => (
    <Card className="max-w-3xl mx-auto mt-8 p-6">
      <div className="flex items-center gap-3 mb-6">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-cyan-100 text-cyan-700">
          <Sparkles className="h-5 w-5" />
        </div>
        <div>
          <h2 className="text-xl font-bold text-slate-900">Build Tool</h2>
          <p className="text-sm text-slate-500">Analyze competitors and generate a targeted prompt for a single gap page.</p>
        </div>
      </div>

      <div className="space-y-5">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Main Keyword <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
            placeholder="e.g. mortgage calculator"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
        </div>
        
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Manual Competitors (Optional)
          </label>
          <p className="text-xs text-slate-500 mb-2">Leave blank to automatically scrape Google for the top 5 competitors.</p>
          <textarea
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 font-mono"
            placeholder="https://example.com&#10;https://example2.com"
            rows={4}
            value={manualCompetitors}
            onChange={(e) => setManualCompetitors(e.target.value)}
          />
        </div>

        <button
          onClick={() => analyzeIntentMutation.mutate()}
          disabled={analyzeIntentMutation.isPending || !keyword.trim()}
          className="flex w-full items-center justify-center gap-2 rounded-md bg-cyan-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-cyan-700 disabled:opacity-50"
        >
          {analyzeIntentMutation.isPending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Scraping Homepages & Analyzing Intent...
            </>
          ) : (
            'Analyze Intent'
          )}
        </button>
        
        {analyzeIntentMutation.isError && (
          <div className="p-3 bg-red-50 text-red-700 rounded-md text-sm border border-red-200">
            {String(analyzeIntentMutation.error)}
          </div>
        )}
      </div>
    </Card>
  )

  const renderStep2 = () => (
    <Card className="max-w-3xl mx-auto mt-8 p-6">
      <div className="mb-6">
        <h2 className="text-xl font-bold text-slate-900 mb-2">Verify Intent</h2>
        <p className="text-sm text-slate-500">
          We scraped the competitors. Here is the deduced intent of this keyword. 
          Modify it if needed before generating the Master Prompt.
        </p>
      </div>

      <div className="mb-6">
        <h3 className="text-sm font-semibold text-slate-800 mb-2">Scraped Competitors:</h3>
        <ul className="list-disc pl-5 text-sm text-slate-600 space-y-1">
          {analyzedCompetitors.map(url => (
            <li key={url}><a href={url} target="_blank" rel="noopener noreferrer" className="text-cyan-600 hover:underline">{url}</a></li>
          ))}
        </ul>
      </div>

      <div className="space-y-5">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Deduced Intent
          </label>
          <textarea
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
            rows={6}
            value={intent}
            onChange={(e) => setIntent(e.target.value)}
          />
        </div>

        <div className="flex gap-3">
          <button
            onClick={() => setStep(1)}
            disabled={generatePromptMutation.isPending}
            className="flex-1 rounded-md border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            Back
          </button>
          <button
            onClick={() => generatePromptMutation.mutate()}
            disabled={generatePromptMutation.isPending || !intent.trim()}
            className="flex flex-[2] items-center justify-center gap-2 rounded-md bg-cyan-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-cyan-700 disabled:opacity-50"
          >
            {generatePromptMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Auditor is checking prompt quality...
              </>
            ) : (
              'Confirm Intent & Generate Prompt'
            )}
          </button>
        </div>
        
        {generatePromptMutation.isError && (
          <div className="p-3 bg-red-50 text-red-700 rounded-md text-sm border border-red-200">
            {String(generatePromptMutation.error)}
          </div>
        )}
      </div>
    </Card>
  )

  const renderStep3 = () => (
    <div className="max-w-5xl mx-auto mt-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-lg font-bold text-slate-900">Build Tool Prompt</h3>
          <p className="text-sm text-slate-500 mt-1">Ready to be copied into Claude Opus or any capable AI builder.</p>
        </div>
        <button
          onClick={() => {
            setGeneratedPrompt(null)
            setStep(1)
          }}
          className="text-sm font-medium text-cyan-600 hover:text-cyan-700"
        >
          Start Over
        </button>
      </div>
      
      <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4 mb-6">
        <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
          <p className="text-slate-500">Keyword</p>
          <p className="text-base font-bold text-slate-950 truncate" title={keyword}>{keyword}</p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
          <p className="text-slate-500">Auditor Score</p>
          <p className="text-base font-bold text-slate-950">{generatedPrompt?.audit_score ?? '-'}</p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
          <p className="text-slate-500">Attempts</p>
          <p className="text-base font-bold text-slate-950">{generatedPrompt?.attempts}</p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
          <p className="text-slate-500">Verdict</p>
          <p className="text-base font-bold text-slate-950">
            {generatedPrompt?.audit_score && generatedPrompt.audit_score >= 80 ? 'Pass' : 'Warning'}
          </p>
        </div>
      </div>

      <Card className="relative p-6">
        <div className="absolute right-4 top-4 flex items-center gap-3">
          <div className="h-5 w-px bg-slate-300" />

          <button
            onClick={() => copyToClipboard(generatedPrompt?.prompt || '')}
            className="flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:ring-offset-1"
          >
            {copied ? (
              <>
                <Check className="h-3.5 w-3.5 text-emerald-600" />
                Copied!
              </>
            ) : (
              <>
                <Copy className="h-3.5 w-3.5" />
                Copy prompt
              </>
            )}
          </button>
        </div>

        <div className="prose prose-slate mt-12 max-w-none whitespace-pre-wrap text-sm leading-7 text-slate-800 bg-slate-50 p-4 rounded-md border border-slate-100 font-mono">
          {generatedPrompt?.prompt}
        </div>
      </Card>
    </div>
  )

  return (
    <div className="p-6">
      {step === 1 && renderStep1()}
      {step === 2 && renderStep2()}
      {step === 3 && renderStep3()}
    </div>
  )
}
