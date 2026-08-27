import { useRef, useState } from 'react'
import { uploadDocument } from '../api/client'

const DOC_TYPES = [
  { value: 'general',    label: 'General' },
  { value: 'company',    label: 'Company' },
  { value: 'project',    label: 'Project' },
  { value: 'technology', label: 'Technology' },
  { value: 'people',     label: 'People' },
]

const ACCEPT = '.md,.txt,.pdf'

export default function DocumentUpload({ onUploaded }) {
  const [file, setFile]           = useState(null)
  const [docType, setDocType]     = useState('general')
  const [isDragging, setDragging] = useState(false)
  const [status, setStatus]       = useState('idle') // idle | uploading | success | error
  const [result, setResult]       = useState(null)
  const [errorMsg, setErrorMsg]   = useState('')
  const inputRef = useRef(null)

  function pickFile(f) {
    if (!f) return
    setFile(f)
    setStatus('idle')
    setResult(null)
    setErrorMsg('')
  }

  function handleDrop(e) {
    e.preventDefault()
    setDragging(false)
    const dropped = e.dataTransfer.files[0]
    if (dropped) pickFile(dropped)
  }

  async function handleUpload() {
    if (!file) return
    setStatus('uploading')
    setResult(null)
    setErrorMsg('')
    try {
      const res = await uploadDocument(file, docType)
      setResult(res)
      setStatus('success')
      setFile(null)
      if (inputRef.current) inputRef.current.value = ''
      onUploaded?.()
    } catch (err) {
      setErrorMsg(err.message)
      setStatus('error')
    }
  }

  const dropZoneClass = [
    'relative flex flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed',
    'p-10 transition-colors cursor-pointer select-none',
    isDragging
      ? 'border-violet-500 bg-violet-50 dark:bg-violet-950/30'
      : 'border-slate-300 dark:border-slate-700 hover:border-violet-400 dark:hover:border-violet-600',
  ].join(' ')

  return (
    <div className="flex flex-col gap-5">
      {/* Drop zone */}
      <div
        className={dropZoneClass}
        onClick={() => inputRef.current?.click()}
        onDragEnter={e => { e.preventDefault(); setDragging(true) }}
        onDragOver={e => e.preventDefault()}
        onDragLeave={e => { e.preventDefault(); setDragging(false) }}
        onDrop={handleDrop}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="hidden"
          onChange={e => pickFile(e.target.files?.[0])}
        />
        <span className="text-4xl">{isDragging ? '📂' : '📄'}</span>
        {file ? (
          <div className="text-center">
            <p className="text-sm font-medium text-slate-700 dark:text-slate-200 truncate max-w-xs">
              {file.name}
            </p>
            <p className="text-xs text-slate-400 mt-0.5">
              {(file.size / 1024).toFixed(1)} KB — click to change
            </p>
          </div>
        ) : (
          <div className="text-center">
            <p className="text-sm text-slate-600 dark:text-slate-400">
              Drag a file here or <span className="text-violet-600 dark:text-violet-400 font-medium">browse</span>
            </p>
            <p className="text-xs text-slate-400 mt-1">.md · .txt · .pdf — max 10 MB</p>
          </div>
        )}
      </div>

      {/* Doc type + upload button */}
      <div className="flex gap-3 items-end">
        <div className="flex flex-col gap-1.5 flex-1">
          <label className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide">
            Document type
          </label>
          <select
            value={docType}
            onChange={e => setDocType(e.target.value)}
            className="rounded-lg border border-slate-200 dark:border-slate-700
                       bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-200
                       px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"
          >
            {DOC_TYPES.map(t => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>

        <button
          onClick={handleUpload}
          disabled={!file || status === 'uploading'}
          className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-medium
                     bg-violet-600 hover:bg-violet-700 text-white transition-colors
                     disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {status === 'uploading' ? (
            <>
              <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
              Uploading…
            </>
          ) : 'Upload & Ingest'}
        </button>
      </div>

      {/* Success */}
      {status === 'success' && result && (
        <div className="rounded-xl border border-emerald-200 dark:border-emerald-800
                        bg-emerald-50 dark:bg-emerald-950/40 px-4 py-3 text-sm
                        text-emerald-700 dark:text-emerald-400">
          <strong>{result.filename}</strong> ingested —&nbsp;
          {result.stats.chunks_created ?? 0} new chunk(s) created
          {result.stats.documents_skipped > 0 && ' (file was already indexed, skipped)'}
          . The pipeline has been updated.
        </div>
      )}

      {/* Error */}
      {status === 'error' && (
        <div className="rounded-xl border border-red-200 dark:border-red-800
                        bg-red-50 dark:bg-red-950/40 px-4 py-3 text-sm
                        text-red-700 dark:text-red-400">
          <strong>Upload failed:</strong> {errorMsg}
        </div>
      )}
    </div>
  )
}
