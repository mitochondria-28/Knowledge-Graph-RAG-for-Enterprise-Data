import { useState } from 'react'

/**
 * CitationList — collapsible panel showing validated citations.
 *
 * Props:
 *   citations: CitationOut[]
 *     { chunk_id, source_file, quote, is_valid, match_score, reason }
 */
export default function CitationList({ citations }) {
  const [open, setOpen] = useState(false)

  if (!citations || citations.length === 0) return null

  const valid = citations.filter(c => c.is_valid).length

  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3
                   text-sm font-medium text-slate-700 dark:text-slate-300
                   bg-slate-50 dark:bg-slate-800/60 hover:bg-slate-100
                   dark:hover:bg-slate-800 transition-colors"
        aria-expanded={open}
      >
        <span>
          Citations &nbsp;
          <span className="font-mono text-xs px-1.5 py-0.5 rounded bg-slate-200
                           dark:bg-slate-700 text-slate-600 dark:text-slate-300">
            {valid}/{citations.length} verified
          </span>
        </span>
        <span className={`transition-transform ${open ? 'rotate-180' : ''}`}>▾</span>
      </button>

      {open && (
        <ul className="divide-y divide-slate-100 dark:divide-slate-700/60">
          {citations.map(c => (
            <li key={c.chunk_id} className="px-4 py-3 text-sm">
              <div className="flex items-start justify-between gap-2 mb-1">
                <span className="font-mono text-xs text-slate-400 dark:text-slate-500 truncate">
                  {c.source_file.replace('corpus/', '')}
                </span>
                <ValidBadge valid={c.is_valid} score={c.match_score} />
              </div>

              <blockquote className="border-l-2 border-slate-300 dark:border-slate-600
                                     pl-3 italic text-slate-600 dark:text-slate-400
                                     text-[0.8125rem] leading-relaxed line-clamp-3">
                "{c.quote}"
              </blockquote>

              <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">{c.reason}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function ValidBadge({ valid, score }) {
  return valid ? (
    <span className="shrink-0 inline-flex items-center gap-1 text-xs font-medium
                     text-emerald-700 dark:text-emerald-400">
      <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor">
        <path fillRule="evenodd" clipRule="evenodd"
          d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075
             l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z"/>
      </svg>
      {score === 1 ? 'Exact' : `Fuzzy ${Math.round(score * 100)}%`}
    </span>
  ) : (
    <span className="shrink-0 inline-flex items-center gap-1 text-xs font-medium
                     text-red-600 dark:text-red-400">
      <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor">
        <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06
                 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75
                 0 00-1.06-1.06L10 8.94 6.28 5.22z"/>
      </svg>
      Unverified
    </span>
  )
}
