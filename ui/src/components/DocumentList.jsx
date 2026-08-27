import { useCallback, useEffect, useState } from 'react'
import { listDocuments } from '../api/client'

const TYPE_COLORS = {
  company:    'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  project:    'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  technology: 'bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300',
  people:     'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
  general:    'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
}

function formatDate(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return iso
  }
}

export default function DocumentList({ refreshTrigger }) {
  const [docs, setDocs]       = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setDocs(await listDocuments())
    } catch {
      setError('Could not load document list.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load, refreshTrigger])

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wide">
          Ingested documents
          {docs.length > 0 && (
            <span className="ml-2 text-xs font-normal text-slate-400">({docs.length})</span>
          )}
        </h2>
        <button
          onClick={load}
          disabled={loading}
          className="text-xs px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700
                     text-slate-600 dark:text-slate-400 hover:border-violet-400 hover:text-violet-700
                     dark:hover:border-violet-500 dark:hover:text-violet-300
                     transition-colors disabled:opacity-40"
        >
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {error && (
        <p className="text-sm text-red-500">{error}</p>
      )}

      {!loading && docs.length === 0 && !error && (
        <div className="rounded-2xl border border-dashed border-slate-200 dark:border-slate-800
                        py-12 flex flex-col items-center gap-2 text-slate-400 dark:text-slate-600">
          <span className="text-3xl">📭</span>
          <p className="text-sm">No documents ingested yet. Upload one above.</p>
        </div>
      )}

      {docs.length > 0 && (
        <div className="flex flex-col gap-2">
          {docs.map(doc => (
            <div
              key={doc.document_id ?? doc.source_file}
              className="rounded-xl border border-slate-200 dark:border-slate-800
                         bg-white dark:bg-slate-900 px-4 py-3 flex items-start gap-4"
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">
                  {doc.title}
                </p>
                <p className="text-xs text-slate-400 dark:text-slate-600 mt-0.5 truncate">
                  {doc.source_file}
                </p>
              </div>
              <div className="flex flex-col items-end gap-1.5 shrink-0 text-right">
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${TYPE_COLORS[doc.doc_type] ?? TYPE_COLORS.general}`}>
                  {doc.doc_type}
                </span>
                <span className="text-xs text-slate-400">
                  {doc.chunk_count} chunk{doc.chunk_count !== 1 ? 's' : ''}
                </span>
                <span className="text-xs text-slate-400 dark:text-slate-600">
                  {formatDate(doc.ingested_at)}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
