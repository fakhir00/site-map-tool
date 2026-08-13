import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckSquare, FilePenLine, FileText, Loader2, Search, Trash2, XSquare } from 'lucide-react'
import { api, type KeywordBankEntry } from '../lib/api'
import { Button } from './ui/Button'
import { Card } from './ui/Card'

export type SavedKeywordsTableProps = {
  keywords: KeywordBankEntry[]
  isLoading: boolean
  actionIcon?: 'write' | 'build'
  onAction?: (keyword: KeywordBankEntry) => void
}

export function SavedKeywordsTable({ keywords, isLoading, actionIcon, onAction }: SavedKeywordsTableProps) {
  const queryClient = useQueryClient()
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  const bulkActionMutation = useMutation({
    mutationFn: (data: { keyword_bank_ids: string[]; action: string }) =>
      api.post('/keyword-bank/bulk-action', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['keyword-bank'] })
      setSelectedIds(new Set())
    },
  })

  const toggleAll = () => {
    if (selectedIds.size === keywords.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(keywords.map(kw => kw.id)))
    }
  }

  const toggleOne = (id: string) => {
    const next = new Set(selectedIds)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelectedIds(next)
  }

  const handleBulkAction = (action: 'mark_done' | 'mark_not_done' | 'delete') => {
    if (selectedIds.size === 0) return
    bulkActionMutation.mutate({
      keyword_bank_ids: Array.from(selectedIds),
      action,
    })
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-lg font-bold text-slate-900">Saved Keywords</h3>
        
        <div className="flex items-center gap-2">
          {selectedIds.size > 0 && (
            <>
              <span className="text-sm text-slate-500 mr-2">{selectedIds.size} selected</span>
              <Button
                size="sm"
                variant="secondary"
                disabled={bulkActionMutation.isPending}
                onClick={() => handleBulkAction('mark_done')}
              >
                <CheckSquare className="h-4 w-4 mr-2" />
                Mark Done
              </Button>
              <Button
                size="sm"
                variant="secondary"
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
            </>
          )}
        </div>
      </div>
      
      <Card className="overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-slate-500">
            <tr>
              <th className="px-5 py-3 font-semibold w-12">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-slate-300 text-cyan-600 focus:ring-cyan-600 cursor-pointer"
                  checked={keywords.length > 0 && selectedIds.size === keywords.length}
                  onChange={toggleAll}
                  disabled={keywords.length === 0}
                />
              </th>
              <th className="px-5 py-3 font-semibold">Keyword</th>
              <th className="px-5 py-3 font-semibold">Type</th>
              <th className="px-5 py-3 font-semibold">Saved Date</th>
              {onAction && <th className="px-5 py-3 text-right font-semibold">Action</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {isLoading ? (
              <tr>
                <td colSpan={onAction ? 5 : 4} className="px-5 py-8 text-center text-slate-500">
                  <Loader2 className="mx-auto mb-3 h-8 w-8 animate-spin text-slate-300" />
                  Loading saved keywords...
                </td>
              </tr>
            ) : keywords.length === 0 ? (
              <tr>
                <td colSpan={onAction ? 5 : 4} className="px-5 py-8 text-center text-slate-500">
                  <FileText className="mx-auto mb-3 h-8 w-8 text-slate-300" />
                  <p>No keywords saved yet.</p>
                  <p className="mt-1 text-xs">Go to a project's Keyword gaps and save keywords to your bank.</p>
                </td>
              </tr>
            ) : (
              keywords.map((kw) => (
                <tr key={kw.id} className={`hover:bg-slate-50 ${kw.is_done ? 'opacity-50 line-through' : ''}`}>
                  <td className="px-5 py-4">
                    <input
                      type="checkbox"
                      className={`h-4 w-4 rounded border-slate-300 cursor-pointer ${
                        kw.is_done 
                          ? 'text-emerald-600 focus:ring-emerald-600' 
                          : 'text-cyan-600 focus:ring-cyan-600'
                      }`}
                      checked={selectedIds.has(kw.id)}
                      onChange={() => toggleOne(kw.id)}
                    />
                  </td>
                  <td className="px-5 py-4 font-medium text-slate-900">{kw.phrase}</td>
                  <td className="px-5 py-4 text-slate-500 capitalize">{kw.keyword_type}</td>
                  <td className="px-5 py-4 text-slate-500">
                    {new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(kw.saved_at))}
                  </td>
                  {onAction && (
                    <td className="px-5 py-4 text-right">
                      <Button
                        onClick={() => onAction(kw)}
                        size="sm"
                        variant="secondary"
                        disabled={kw.is_done}
                      >
                        {actionIcon === 'write' ? <FilePenLine className="h-4 w-4 mr-2" /> : <Search className="h-4 w-4 mr-2" />}
                        {actionIcon === 'write' ? 'Write' : 'Build'}
                      </Button>
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
