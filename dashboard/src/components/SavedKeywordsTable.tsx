import { Fragment, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  CheckSquare,
  ChevronDown,
  FilePenLine,
  FileText,
  Search,
  Trash2,
  XSquare,
} from 'lucide-react'
import { api, type KeywordBankEntry } from '../lib/api'
import { Button } from './ui/Button'
import { Card } from './ui/Card'
import { Badge } from './ui/Badge'
import { Input } from './ui/Input'

export type SavedKeywordsTableProps = {
  keywords: KeywordBankEntry[]
  isLoading: boolean
  actionIcon?: 'write' | 'build' | 'both'
  onAction?: (keyword: KeywordBankEntry, actionType: 'write' | 'build') => void
}

const TYPE_LABELS: Record<KeywordBankEntry['keyword_type'], string> = {
  'top-pick': 'Top pick',
  primary: 'Primary',
  lsi: 'LSI',
  entity: 'Entity',
  heading: 'Heading',
  'long-tail': 'Long tail',
}

const MICRO_LABEL = 'text-[11px] font-semibold uppercase tracking-[0.08em] text-muted'

function formatDate(savedAt: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(savedAt))
}

function EmptyBankArt() {
  return (
    <svg
      width="112"
      height="92"
      viewBox="0 0 112 92"
      fill="none"
      aria-hidden="true"
      className="mx-auto mb-5"
    >
      <rect x="16" y="38" width="80" height="42" rx="12" fill="#161B26" stroke="#2A3348" strokeWidth="2" />
      <rect x="28" y="48" width="56" height="8" rx="4" fill="#1C2230" />
      <rect x="28" y="62" width="36" height="8" rx="4" fill="#1C2230" />
      <path
        d="M50 6h12v30l-6-5.5L50 36V6z"
        fill="#F5A524"
        fillOpacity="0.28"
        stroke="#F5A524"
        strokeOpacity="0.8"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <circle cx="88" cy="22" r="3" fill="#F5A524" fillOpacity="0.5" />
      <circle cx="24" cy="28" r="2.5" fill="#9AA3B2" fillOpacity="0.4" />
      <circle cx="96" cy="58" r="2" fill="#9AA3B2" fillOpacity="0.3" />
    </svg>
  )
}

export function SavedKeywordsTable({ keywords, isLoading, actionIcon, onAction }: SavedKeywordsTableProps) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())
  const [search, setSearch] = useState('')
  const [copyMessage, setCopyMessage] = useState('')
  const availableIds = new Set(keywords.map((keyword) => keyword.id))
  const selectedVisibleIds = Array.from(selectedIds).filter((id) => availableIds.has(id))

  const query = search.trim().toLowerCase()
  const visibleKeywords = query
    ? keywords.filter((kw) => kw.phrase.toLowerCase().includes(query))
    : keywords
  const visibleIds = visibleKeywords.map((kw) => kw.id)
  const selectedInViewCount = visibleIds.filter((id) => selectedIds.has(id)).length
  const doneCount = keywords.filter((kw) => kw.is_done).length

  const bulkActionMutation = useMutation({
    mutationFn: (data: { keyword_bank_ids: string[]; action: string }) =>
      api.post('/keyword-bank/bulk-action', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['keyword-bank'] })
      setSelectedIds(new Set())
    },
  })

  const toggleAll = () => {
    const next = new Set(selectedIds)
    if (visibleIds.length > 0 && selectedInViewCount === visibleIds.length) {
      visibleIds.forEach((id) => next.delete(id))
    } else {
      visibleIds.forEach((id) => next.add(id))
    }
    setSelectedIds(next)
  }

  const toggleOne = (id: string) => {
    const next = new Set(selectedIds)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelectedIds(next)
  }

  const toggleExpanded = (id: string) => {
    const next = new Set(expandedIds)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setExpandedIds(next)
  }

  const handleBulkAction = (action: 'mark_done' | 'mark_not_done' | 'delete') => {
    if (selectedVisibleIds.length === 0) return
    if (action === 'delete' && !window.confirm(`Permanently delete ${selectedVisibleIds.length} saved keyword${selectedVisibleIds.length === 1 ? '' : 's'}?`)) return
    bulkActionMutation.mutate({
      keyword_bank_ids: selectedVisibleIds,
      action,
    })
  }

  const handleCopy = async () => {
    const selectedKeywordsText = keywords.filter((k) => selectedIds.has(k.id)).map((k) => k.phrase).join('\n')
    try {
      await navigator.clipboard.writeText(selectedKeywordsText)
      setCopyMessage('Copied to clipboard.')
    } catch {
      setCopyMessage('Could not copy. Check browser clipboard permissions and try again.')
    }
  }

  const colSpan = onAction ? 4 : 3

  return (
    <div className="animate-fade-up">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h3 className="font-display text-xl font-semibold text-ink">Saved keywords</h3>
          <p className="mt-0.5 text-sm text-muted">
            {keywords.length === 0
              ? 'Nothing saved yet'
              : `${keywords.length} saved · ${doneCount} done`}
          </p>
        </div>
        <div className="relative w-full sm:w-64">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search keywords…"
            aria-label="Search saved keywords"
            className="pl-9"
          />
        </div>
      </div>

      {selectedVisibleIds.length > 0 && (
        <div className="animate-fade-up mb-4 flex flex-wrap items-center gap-2 rounded-2xl border border-glow-amber/25 bg-glow-amber/[0.07] px-4 py-3">
          <span className="mr-1 text-sm font-semibold text-glow-amber">
            {selectedVisibleIds.length} selected
          </span>
          <Button size="sm" variant="secondary" onClick={handleCopy}>
            <FileText className="h-4 w-4" />
            Copy
          </Button>
          <Button size="sm" variant="secondary" disabled={bulkActionMutation.isPending} onClick={() => handleBulkAction('mark_done')}>
            <CheckSquare className="h-4 w-4" />
            Mark done
          </Button>
          <Button size="sm" variant="ghost" disabled={bulkActionMutation.isPending} onClick={() => handleBulkAction('mark_not_done')}>
            <XSquare className="h-4 w-4" />
            Not done
          </Button>
          <Button size="sm" variant="danger" disabled={bulkActionMutation.isPending} onClick={() => handleBulkAction('delete')}>
            <Trash2 className="h-4 w-4" />
            Delete
          </Button>
        </div>
      )}

      {bulkActionMutation.error && (
        <p role="alert" className="mb-4 rounded-xl border border-warm-red/25 bg-warm-red/10 px-4 py-3 text-sm text-warm-red">
          {bulkActionMutation.error.message}
        </p>
      )}
      {copyMessage && (
        <p role="status" className="mb-4 text-sm text-alive-green">{copyMessage}</p>
      )}

      <Card className="overflow-hidden p-0" lift={false}>
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-line">
              <th className="w-12 px-6 py-3">
                <input
                  type="checkbox"
                  className="h-4 w-4 cursor-pointer rounded accent-glow-amber"
                  checked={visibleIds.length > 0 && selectedInViewCount === visibleIds.length}
                  onChange={toggleAll}
                  disabled={keywords.length === 0}
                  aria-label="Select all keywords"
                />
              </th>
              <th className={`px-6 py-3 ${MICRO_LABEL}`}>Keyword</th>
              <th className={`px-6 py-3 ${MICRO_LABEL}`}>Status</th>
              {onAction && (
                <th className={`px-6 py-3 text-right ${MICRO_LABEL}`}>
                  <span className="sr-only">Actions</span>
                </th>
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i}>
                  <td className="px-6 py-5">
                    <div className="animate-shimmer h-4 w-4 rounded" />
                  </td>
                  <td className="px-6 py-5">
                    <div className="animate-shimmer h-5 w-2/3 rounded-lg" />
                    <div className="animate-shimmer mt-2 h-4 w-1/3 rounded-lg" />
                  </td>
                  <td className="px-6 py-5">
                    <div className="animate-shimmer h-6 w-16 rounded-full" />
                  </td>
                  {onAction && (
                    <td className="px-6 py-5">
                      <div className="animate-shimmer ml-auto h-8 w-28 rounded-xl" />
                    </td>
                  )}
                </tr>
              ))
            ) : keywords.length === 0 ? (
              <tr>
                <td colSpan={colSpan} className="px-6 py-14 text-center">
                  <EmptyBankArt />
                  <p className="font-display text-lg font-semibold text-ink">Your bank is empty</p>
                  <p className="mx-auto mt-1 max-w-sm text-sm text-muted">
                    Save keywords from a Gap Scan and they'll be waiting for you here, ready to turn into pages.
                  </p>
                  <Button variant="glow" size="md" className="mt-5" onClick={() => navigate('/scan')}>
                    <Search className="h-4 w-4" />
                    Find keywords
                  </Button>
                </td>
              </tr>
            ) : visibleKeywords.length === 0 ? (
              <tr>
                <td colSpan={colSpan} className="px-6 py-14 text-center">
                  <p className="font-display text-lg font-semibold text-ink">No matches for “{search.trim()}”</p>
                  <p className="mt-1 text-sm text-muted">Try a different word, or clear the search to see everything.</p>
                  <Button variant="secondary" size="sm" className="mt-4" onClick={() => setSearch('')}>
                    Clear search
                  </Button>
                </td>
              </tr>
            ) : (
              visibleKeywords.map((kw, ri) => {
                const expanded = expandedIds.has(kw.id)
                return (
                  <Fragment key={kw.id}>
                    <tr className={`animate-fade-up transition-colors hover:bg-glow-amber/[0.05] stagger-${Math.min(ri + 1, 8)} ${kw.is_done ? 'opacity-55' : ''}`}>
                      <td className="w-12 px-6 py-5 align-top">
                        <input
                          type="checkbox"
                          className="mt-1 h-4 w-4 cursor-pointer rounded accent-glow-amber"
                          checked={selectedIds.has(kw.id)}
                          onChange={() => toggleOne(kw.id)}
                          aria-label={`Select ${kw.phrase}`}
                        />
                      </td>
                      <td className="px-6 py-5">
                        <p className={`font-medium text-ink ${kw.is_done ? 'line-through decoration-muted/50' : ''}`}>
                          {kw.phrase}
                        </p>
                        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                          <Badge variant={kw.keyword_type === 'top-pick' ? 'amber' : 'slate'}>
                            {TYPE_LABELS[kw.keyword_type]}
                          </Badge>
                          <span className="font-mono text-[11px] text-muted">{formatDate(kw.saved_at)}</span>
                        </div>
                      </td>
                      <td className="px-6 py-5">
                        {kw.is_done ? (
                          <Badge variant="green">Done</Badge>
                        ) : (
                          <Badge variant="amber">Ready</Badge>
                        )}
                      </td>
                      {onAction && (
                        <td className="px-6 py-5">
                          <div className="flex items-center justify-end gap-2">
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => toggleExpanded(kw.id)}
                              aria-label={expanded ? `Hide details for ${kw.phrase}` : `Show details for ${kw.phrase}`}
                              aria-expanded={expanded}
                            >
                              <ChevronDown className={`h-4 w-4 transition-transform ${expanded ? 'rotate-180' : ''}`} />
                            </Button>
                            {(actionIcon === 'write' || actionIcon === 'both') && (
                              <Button
                                onClick={() => onAction(kw, 'write')}
                                size="sm"
                                variant="secondary"
                                disabled={kw.is_done}
                              >
                                <FilePenLine className="h-4 w-4" />
                                Write
                              </Button>
                            )}
                            {(actionIcon === 'build' || actionIcon === 'both') && (
                              <Button
                                onClick={() => onAction(kw, 'build')}
                                size="sm"
                                variant="secondary"
                                disabled={kw.is_done}
                              >
                                <Search className="h-4 w-4" />
                                Build
                              </Button>
                            )}
                          </div>
                        </td>
                      )}
                    </tr>
                    {expanded && (
                      <tr className={kw.is_done ? 'opacity-55' : ''}>
                        <td className="px-6 py-0" aria-hidden="true" />
                        <td colSpan={colSpan - 1} className="px-6 pb-6 pt-0">
                          <div className="animate-fade-up grid gap-4 rounded-xl border border-line bg-raised/70 p-4 sm:grid-cols-3">
                            <div>
                              <p className={MICRO_LABEL}>Notes</p>
                              <p className="mt-1 text-sm text-ink">{kw.notes || <span className="text-muted">No notes yet.</span>}</p>
                            </div>
                            <div>
                              <p className={MICRO_LABEL}>Frequency</p>
                              <p className="mt-1 font-mono text-sm text-ink">{kw.frequency}</p>
                            </div>
                            <div>
                              <p className={MICRO_LABEL}>Saved</p>
                              <p className="mt-1 text-sm text-ink">{formatDate(kw.saved_at)}</p>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })
            )}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
