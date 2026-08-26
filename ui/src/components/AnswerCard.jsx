import CitationList from './CitationList'
import MetaBadges from './MetaBadges'

/**
 * AnswerCard — displays a single Q&A result with metadata and citations.
 *
 * Props:
 *   result: AskResponse — the full API response object
 */
export default function AnswerCard({ result }) {
  return (
    <article className="rounded-2xl border border-slate-200 dark:border-slate-700
                        bg-white dark:bg-slate-900 shadow-sm overflow-hidden">
      {/* Question */}
      <div className="px-5 pt-5 pb-3 border-b border-slate-100 dark:border-slate-800">
        <p className="text-xs font-semibold uppercase tracking-wide
                      text-slate-400 dark:text-slate-500 mb-1">Question</p>
        <p className="text-slate-800 dark:text-slate-200 font-medium leading-snug">
          {result.question}
        </p>
      </div>

      {/* Answer */}
      <div className="px-5 py-4">
        <p className="text-xs font-semibold uppercase tracking-wide
                      text-slate-400 dark:text-slate-500 mb-2">Answer</p>
        <p className="text-slate-700 dark:text-slate-300 leading-relaxed whitespace-pre-wrap">
          {result.answer}
        </p>
      </div>

      {/* Meta badges */}
      <div className="px-5 pb-4">
        <MetaBadges
          strategy={result.retrieval_strategy}
          latencyMs={result.latency_ms}
          citationConfidence={result.citation_confidence}
          model={result.model}
          chunkCount={result.chunk_count}
        />
      </div>

      {/* Citations (collapsible) */}
      {result.citations?.length > 0 && (
        <div className="px-5 pb-5">
          <CitationList citations={result.citations} />
        </div>
      )}
    </article>
  )
}
