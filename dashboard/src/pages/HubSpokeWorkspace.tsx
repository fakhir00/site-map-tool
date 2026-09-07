import { useRef, useState } from 'react'
import { Download, FileUp, Network, Sparkles, Trash2 } from 'lucide-react'
import { api } from '../lib/api'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'

type LayerMap = Record<string, string[]>
type Silo = { hub_title: string; target_keyword: string; h2_keywords?: string[]; layers: LayerMap }
type Hub = Silo & { sub_silos?: Silo[] }
type Mapping = { hubs: Hub[]; _planning_thought?: string }

const parseFile = (text: string) => {
  const values = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
  if (values[0]?.toLowerCase().replaceAll('"', '').startsWith('keyword')) values.shift()
  return values.map((line) => line.split(',')[0].replaceAll('"', '').trim()).filter(Boolean)
}

const downloadText = (name: string, content: string) => {
  const url = URL.createObjectURL(new Blob([content], { type: 'text/plain;charset=utf-8' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = name
  anchor.click()
  URL.revokeObjectURL(url)
}

export function HubSpokeWorkspace() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [keywords, setKeywords] = useState<string[]>([])
  const [cleaned, setCleaned] = useState<string[]>([])
  const [contextOpen, setContextOpen] = useState(false)
  const [context, setContext] = useState('')
  const [mapping, setMapping] = useState<Mapping | null>(null)
  const [busy, setBusy] = useState<'clean' | 'build' | null>(null)
  const [error, setError] = useState('')

  const loadFile = async (file?: File) => {
    if (!file) return
    if (file.size > 5_000_000) {
      setError('Use a CSV or TXT file smaller than 5 MB.')
      return
    }
    setKeywords(parseFile(await file.text()))
    setCleaned([])
    setMapping(null)
    setError('')
  }

  const removeNoise = async () => {
    setBusy('clean'); setError('')
    try {
      const result = await api.postAI<{ keywords: string[] }>('/hub-spoke/clean', { keywords, context })
      setCleaned(result.keywords)
      setMapping(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Keyword cleaning failed')
    } finally { setBusy(null) }
  }

  const build = async () => {
    setBusy('build'); setError('')
    try {
      const result = await api.postAI<{ keywords: string[]; clusters: Mapping }>('/hub-spoke/build', {
        keywords: cleaned.length ? cleaned : keywords,
        context,
      })
      setCleaned(result.keywords)
      setMapping(result.clusters)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Hub-spoke generation failed')
    } finally { setBusy(null) }
  }

  const renderLayers = (layers: LayerMap) => Object.entries(layers || {}).map(([name, spokes]) => (
    <div key={name} className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
      <p className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500">{name}</p>
      <ul className="space-y-1.5 text-sm text-slate-700 dark:text-slate-300">
        {spokes.map((spoke) => <li key={spoke}>• {spoke}</li>)}
      </ul>
    </div>
  ))

  const renderH2s = (keywords?: string[]) => keywords?.length ? (
    <div className="mt-3 rounded-lg bg-cyan-50 p-3 dark:bg-cyan-950/30">
      <p className="mb-1 text-xs font-bold uppercase tracking-wide text-cyan-700 dark:text-cyan-300">Cover on this page as H2 sections</p>
      <ul className="space-y-1 text-sm text-slate-700 dark:text-slate-300">
        {keywords.map((keyword) => <li key={keyword}>• {keyword}</li>)}
      </ul>
    </div>
  ) : null

  return (
    <div className="space-y-6">
      <section>
        <h2 className="text-2xl font-bold">Hub Spoke</h2>
        <p className="mt-1 text-sm text-slate-500">Upload keyword research, remove noise with your context, then build a cannibalization-safe content architecture.</p>
      </section>

      <Card className="space-y-5 p-6">
        <input ref={inputRef} className="hidden" type="file" accept=".csv,.txt,text/csv,text/plain" onChange={(event) => loadFile(event.target.files?.[0])} />
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => { event.preventDefault(); loadFile(event.dataTransfer.files?.[0]) }}
          className="flex min-h-52 w-full flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-300 bg-slate-50 px-6 text-center hover:border-cyan-500 dark:border-slate-700 dark:bg-slate-900/50"
        >
          <FileUp className="mb-3 h-9 w-9 text-cyan-700 dark:text-cyan-400" />
          <span className="font-semibold">Drop a CSV or TXT keyword list here</span>
          <span className="mt-1 text-sm text-slate-500">or click to add from your computer</span>
        </button>

        {keywords.length > 0 && <p className="text-sm font-medium text-emerald-700 dark:text-emerald-400">Loaded {keywords.length.toLocaleString()} keywords</p>}

        <div className="flex flex-wrap gap-3">
          <Button variant="secondary" onClick={() => setContextOpen((value) => !value)}><Sparkles className="h-4 w-4" />Add context</Button>
          <Button disabled={!keywords.length || busy !== null} onClick={removeNoise}><Trash2 className="h-4 w-4" />{busy === 'clean' ? 'Cleaning…' : 'Remove noise'}</Button>
          <Button disabled={!keywords.length || busy !== null} onClick={build}><Network className="h-4 w-4" />{busy === 'build' ? 'Building…' : 'Make hub spoke'}</Button>
        </div>

        {contextOpen && (
          <div>
            <label className="mb-2 block text-sm font-semibold">Website and audience context</label>
            <textarea
              className="min-h-40 w-full rounded-lg border border-slate-300 bg-white p-3 text-sm outline-none focus:ring-2 focus:ring-cyan-500 dark:border-slate-700 dark:bg-slate-900"
              value={context}
              onChange={(event) => setContext(event.target.value)}
              placeholder="Describe the website, product, target audience, search intent, competitors, capabilities, and topics that must be excluded."
            />
          </div>
        )}

        {error && <p className="rounded-lg bg-rose-50 p-3 text-sm text-rose-700 dark:bg-rose-900/30 dark:text-rose-300">{error}</p>}
      </Card>

      {cleaned.length > 0 && (
        <Card className="p-6">
          <div className="flex items-center justify-between gap-4">
            <div><h3 className="font-bold">Clean keyword list</h3><p className="text-sm text-slate-500">{cleaned.length.toLocaleString()} relevant keywords remain</p></div>
            <Button variant="secondary" onClick={() => downloadText('cleaned-keywords.txt', cleaned.join('\n'))}><Download className="h-4 w-4" />Download cleaned list</Button>
          </div>
          <div className="mt-4 max-h-64 overflow-auto rounded-lg bg-slate-50 p-4 text-sm dark:bg-slate-900/60">{cleaned.map((keyword) => <div key={keyword}>{keyword}</div>)}</div>
        </Card>
      )}

      {mapping && (
        <section className="space-y-4">
          <div className="flex items-center justify-between gap-4">
            <div><h3 className="text-xl font-bold">Hub-spoke architecture</h3>{mapping._planning_thought && <p className="text-sm text-slate-500">{mapping._planning_thought}</p>}</div>
            <Button onClick={() => downloadText('hub-spoke-architecture.txt', JSON.stringify(mapping, null, 2))}><Download className="h-4 w-4" />Download architecture</Button>
          </div>
          {mapping.hubs.map((hub) => (
            <Card key={hub.target_keyword} className="space-y-4 p-6">
              <div><p className="text-xs font-bold uppercase text-cyan-700">Master hub</p><h4 className="text-lg font-bold">{hub.hub_title}</h4><p className="text-sm text-slate-500">Target: {hub.target_keyword}</p>{renderH2s(hub.h2_keywords)}</div>
              {Object.keys(hub.layers || {}).length > 0 && <div className="grid gap-3 lg:grid-cols-2">{renderLayers(hub.layers)}</div>}
              <div className="grid gap-4 xl:grid-cols-2">
                {(hub.sub_silos || []).map((silo) => <div key={silo.target_keyword} className="rounded-xl border border-slate-200 p-4 dark:border-slate-700"><h5 className="font-bold">{silo.hub_title}</h5><p className="text-xs text-slate-500">Target: {silo.target_keyword}</p>{renderH2s(silo.h2_keywords)}<div className="mt-3 space-y-3">{renderLayers(silo.layers)}</div></div>)}
              </div>
            </Card>
          ))}
        </section>
      )}
    </div>
  )
}
