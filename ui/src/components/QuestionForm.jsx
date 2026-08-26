import { useState } from 'react'

/**
 * QuestionForm — search-bar + context-chunk slider.
 *
 * Props:
 *   onSubmit(question: string, topK: number) → void
 *   loading: bool
 *   disabled: bool  (pipeline not ready)
 */
export default function QuestionForm({ onSubmit, loading, disabled }) {
  const [topK, setTopK] = useState(5)

  function handleSubmit(e) {
    e.preventDefault()
    const question = e.currentTarget.question.value.trim()
    if (!question) return
    onSubmit(question, topK)
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
      <div className="flex gap-2">
        <input
          name="question"
          type="text"
          placeholder={
            disabled
              ? 'Waiting for pipeline to load…'
              : 'Ask a question about TechNova Corporation…'
          }
          disabled={disabled || loading}
          maxLength={500}
          autoComplete="off"
          className="flex-1 rounded-xl border border-slate-300 dark:border-slate-600
                     bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100
                     px-4 py-3 text-base shadow-sm
                     placeholder:text-slate-400 dark:placeholder:text-slate-500
                     focus:outline-none focus:ring-2 focus:ring-violet-500
                     disabled:opacity-50 disabled:cursor-not-allowed"
        />
        <button
          type="submit"
          disabled={disabled || loading}
          className="rounded-xl bg-violet-600 hover:bg-violet-700 active:bg-violet-800
                     text-white font-medium px-5 py-3 text-base shadow-sm
                     transition-colors disabled:opacity-50 disabled:cursor-not-allowed
                     focus:outline-none focus:ring-2 focus:ring-violet-500 focus:ring-offset-2"
        >
          {loading ? (
            <span className="flex items-center gap-2">
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10"
                  stroke="currentColor" strokeWidth="4"/>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
              </svg>
              Thinking…
            </span>
          ) : 'Ask'}
        </button>
      </div>

      <div className="flex items-center gap-3 text-sm text-slate-500 dark:text-slate-400">
        <label className="shrink-0">Context chunks:</label>
        <input
          type="range" min={1} max={10} value={topK}
          onChange={e => setTopK(Number(e.target.value))}
          className="w-28 accent-violet-600"
        />
        <span className="w-5 text-center font-mono text-xs font-medium
                         text-slate-700 dark:text-slate-300">
          {topK}
        </span>
      </div>
    </form>
  )
}
