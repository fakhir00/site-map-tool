import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckSquare, FilePenLine, FileText, Loader2, PackageOpen, Search, Trash2, XSquare } from 'lucide-react'
import { api, type KeywordBankEntry } from '../lib/api'
import { Button } from './ui/Button'
import { Card } from './ui/Card'

export type SavedKeywordsTableProps = {
  keywords: KeywordBankEntry[]
  isLoading: boolean
  actionIcon?: 'write' | 'build' | 'both'
  onAction?: (keyword: KeywordBankEntry, actionType: 'write' | 'build') => void
}

type BinFilter = 'all' | 'tool' | 'blog'

function binOf(keyword: KeywordBankEntry): BinFilter | null {
  if (keyword.notes === '#tool') return 'tool'
  if (keyword.notes === '#blog') return 'blog'
  return null
}

function SourceStamp({ keyword }: { keyword: KeywordBankEntry }) {
  const bin = binOf(keyword)
  if (bin === 'tool') return <span className="stamp stamp-sky">Tool</span>
  if (bin === 'blog') return <span className="stamp stamp-amber">Blog</span>
  return <span className="stamp stamp-muted">Unsorted</span>
}

export function SavedKeywordsTable({ keywords, isLoading, actionIcon, onAction }: SavedKeywordsTableProps) {
  const queryClient = useQueryClient()
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [copyMessage, setCopyMessage] = useState('')
  const [binFilter, setBinFilter] = useState<BinFilter>('all')
  const availableIds = new Set(keywords.map((keyword) => keyword.id))
  const rows = binFilter === 'all' ? keywords : keywords.filter((keyword) => binOf(keyword) === binFilter)
  const selectedVisibleIds = Array.from(selectedIds).filter((id) => availableIds.has(id))

  const bulkActionMutation = useMutation({
    mutationFn: (data: { keyword_bank_ids: string[]; action: string }) =>
      api.post('/keyword-bank/bulk-action', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['keyword-bank'] })
      setSelectedIds(new Set())
    },
  })

  const toggleAll = () => {
    if (selectedVisibleIds.length === rows.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(rows.map(kw => kw.id)))
    }
  }

  const toggleOne = (id: string) => {
    const next = new Set(selectedIds)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelectedIds(next)
  }

  const handleBulkAction = (action: 'mark_done' | 'mark_not_done' | 'delete') => {
    if (selectedVisibleIds.length === 0) return
    if (action === 'delete' && !window.confirm(`Permanently delete ${selectedVisibleIds.length} saved keyword${selectedVisibleIds.length === 1 ? '' : 's'}?`)) return
    bulkActionMutation.mutate({
      keyword_bank_ids: selectedVisibleIds,
      action,
    })
  }

  const chipClass = (active: boolean) =>
    `rounded-md border px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.18em] transition-colors cursor-pointer ${
      active
        ? 'border-amber/70 bg-amber/10 text-amber'
        : 'border-line bg-transparent text-muted hover:border-amber/40 hover:text-text'
    }`
  const binCount = (bin: BinFilter) => bin === 'all' ? keywords.length : keywords.filter((keyword) => binOf(keyword) === bin).length
  const colSpan = onAction ? 7 : 6

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="font-display text-lg font-bold text-text">Inventory Ledger</h3>
          <p className="annotation mt-1">
            {rows.length} {rows.length === 1 ? 'part' : 'parts'} shelved
            {selectedVisibleIds.length > 0 && <> · {selectedVisibleIds.length} pulled for the tray</>}
          </p>
        </div>

        <div className="flex items-center gap-2" aria-label="Filter parts by bin">
          <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-muted">Bin:</span>
          {(['all', 'tool', 'blog'] as const).map((bin) => (
            <button
              key={bin}
              type="button"
              className={chipClass(binFilter === bin)}
              aria-pressed={binFilter === bin}
              onClick={() => setBinFilter(bin)}
            >
              {bin} · {binCount(bin)}
            </button>
          ))}
        </div>
      </div>

      {selectedVisibleIds.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-dashed border-amber/60 bg-panel px-4 py-3">
          <span className="font-mono text-xs font-semibold uppercase tracking-[0.14em] text-amber">
            {selectedVisibleIds.length} picked
          </span>
          <span className="font-mono text-xs text-muted">— tool tray</span>
          <span className="mx-1 hidden h-5 w-px bg-line sm:block" aria-hidden="true" />
          <Button
            size="sm"
            variant="draft"
            disabled={selectedVisibleIds.length === 0}
            onClick={async () => {
              const selectedKeywordsText = keywords.filter(k => selectedIds.has(k.id)).map(k => k.phrase).join('\n')
              try {
                await navigator.clipboard.writeText(selectedKeywordsText)
                setCopyMessage('Copied to clipboard.')
              } catch {
                setCopyMessage('Could not copy. Check browser clipboard permissions and try again.')
              }
            }}
          >
            <FileText className="h-4 w-4 mr-2" />
            Copy
          </Button>
          <Button
            size="sm"
            variant="draft"
            disabled={bulkActionMutation.isPending}
            onClick={() => handleBulkAction('mark_done')}
          >
            <CheckSquare className="h-4 w-4 mr-2" />
            Mark Done
          </Button>
          <Button
            size="sm"
            variant="draft"
            disabled={bulkActionMutation.isPending}
            onClick={() => handleBulkAction('mark_not_done')}
          >
            <XSquare className="h-4 w-4 mr-2" />
            Mark Not Done
          </Button>
          <Button
            size="sm"
            variant="danger"
            disabled={bulkActionMutation.isPending}
            onClick={() => handleBulkAction('delete')}
          >
            <Trash2 className="h-4 w-4 mr-2" />
            Delete
          </Button>
        </div>
      )}

      {bulkActionMutation.error && <p role="alert" className="annotation !text-red mb-4">{bulkActionMutation.error.message}</p>}
      {copyMessage && <p role="status" className="annotation mb-4">{copyMessage}</p>}

      <Card className="overflow-hidden p-0">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-line">
              <th className="w-12 px-5 py-3">
                <input
                  type="checkbox"
                  className="h-4 w-4 cursor-pointer accent-amber"
                  checked={rows.length > 0 && selectedVisibleIds.length === rows.length}
                  onChange={toggleAll}
                  disabled={rows.length === 0}
                  aria-label="Select all parts"
                />
              </th>
              <th className="px-5 py-3 font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-muted">Keyword</th>
              <th className="px-5 py-3 font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-muted">Source</th>
              <th className="px-5 py-3 font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-muted">Type</th>
              <th className="px-5 py-3 font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-muted">Saved</th>
              <th className="px-5 py-3 font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-muted">Project</th>
              {onAction && <th className="px-5 py-3 text-right font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-muted">Action</th>}
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={colSpan} className="px-5 py-10 text-center">
                  <Loader2 className="mx-auto mb-3 h-8 w-8 animate-spin text-amber" />
                  <p className="annotation inline-block">Pulling parts from the shelves…</p>
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={colSpan} className="px-5 py-8">
                  <div className="bg-blueprint dashed-amber mx-auto flex max-w-md flex-col items-center rounded-xl px-6 py-10 text-center">
                    <PackageOpen className="h-10 w-10 text-amber" aria-hidden="true" />
                    <p className="mt-4 font-display text-base font-semibold text-text">Empty bin</p>
                    <p className="annotation mt-2 text-left">
                      {binFilter === 'all'
                        ? 'No parts shelved yet. Save keywords from a Gap Scan or the Blog tool and they land here.'
                        : `No ${binFilter} parts in this bin. Switch bins or save more keywords from the ${binFilter === 'tool' ? 'Gap Scan' : 'Blog tool'}.`}
                    </p>
                  </div>
                </td>
              </tr>
            ) : (
              rows.map((kw) => (
                <tr key={kw.id} className={`border-b border-line last:border-0 hover:bg-raised ${kw.is_done ? 'opacity-50' : ''}`}>
                  <td className="px-5 py-4">
                    <input
                      type="checkbox"
                      className="h-4 w-4 cursor-pointer accent-amber"
                      checked={selectedIds.has(kw.id)}
                      onChange={() => toggleOne(kw.id)}
                      aria-label={`Select ${kw.phrase}`}
                    />
                  </td>
                  <td className="px-5 py-4 font-mono text-[13px] text-text">
                    {kw.is_done ? (
                      <span className="line-through decoration-amber/70">{kw.phrase}</span>
                    ) : (
                      kw.phrase
                    )}
                    {kw.is_done && <span className="stamp stamp-green ml-3">Done</span>}
                  </td>
                  <td className="px-5 py-4">
                    <SourceStamp keyword={kw} />
                  </td>
                  <td className="px-5 py-4 font-mono text-xs uppercase tracking-wider text-muted">{kw.keyword_type}</td>
                  <td className="px-5 py-4 font-mono text-xs text-muted">
                    {new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(kw.saved_at))}
                  </td>
                  <td className="px-5 py-4 font-mono text-xs uppercase text-muted">PRJ·{kw.project_id.slice(0, 8)}</td>
                  {onAction && (
                    <td className="px-5 py-4 text-right">
                      <div className="flex justify-end gap-2">
                        {(actionIcon === 'write' || actionIcon === 'both') && (
                          <Button
                            onClick={() => onAction(kw, 'write')}
                            size="sm"
                            variant="draft"
                            disabled={kw.is_done}
                          >
                            <FilePenLine className="h-4 w-4 mr-2" />
                            Write
                          </Button>
                        )}
                        {(actionIcon === 'build' || actionIcon === 'both') && (
                          <Button
                            onClick={() => onAction(kw, 'build')}
                            size="sm"
                            variant="draft"
                            disabled={kw.is_done}
                          >
                            <Search className="h-4 w-4 mr-2" />
                            Build
                          </Button>
                        )}
                      </div>
                    </td>
                  )}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
