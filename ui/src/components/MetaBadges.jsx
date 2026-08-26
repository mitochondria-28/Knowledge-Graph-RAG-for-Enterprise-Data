/**
 * MetaBadges — row of coloured pills showing routing strategy, latency, confidence.
 *
 * Props:
 *   strategy: 'vector' | 'graph' | 'hybrid'
 *   latencyMs: number
 *   citationConfidence: number   (0–1)
 *   model: string
 *   chunkCount: number
 */

const STRATEGY_STYLE = {
  vector: 'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300',
  graph:  'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  hybrid: 'bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300',
}

const STRATEGY_LABEL = {
  vector: '⚡ Vector',
  graph:  '🕸 Graph',
  hybrid: '🔀 Hybrid',
}

function Badge({ children, className = '' }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5
                      text-xs font-medium ${className}`}>
      {children}
    </span>
  )
}

function confColor(v) {
  if (v >= 0.9) return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
  if (v >= 0.6) return 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300'
  return 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300'
}

export default function MetaBadges({ strategy, latencyMs, citationConfidence, model, chunkCount }) {
  return (
    <div className="flex flex-wrap gap-2">
      <Badge className={STRATEGY_STYLE[strategy] ?? STRATEGY_STYLE.hybrid}>
        {STRATEGY_LABEL[strategy] ?? strategy}
      </Badge>

      <Badge className="bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
        ⏱ {latencyMs < 1000
            ? `${Math.round(latencyMs)}ms`
            : `${(latencyMs / 1000).toFixed(1)}s`}
      </Badge>

      <Badge className={confColor(citationConfidence)}>
        ✓ {Math.round(citationConfidence * 100)}% cited
      </Badge>

      <Badge className="bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
        📄 {chunkCount} chunk{chunkCount !== 1 ? 's' : ''}
      </Badge>

      <Badge className="bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400 font-mono">
        {model.replace('gemini-', 'gemini/').replace('claude-', '').replace(/-\d{8}$/, '')}
      </Badge>
    </div>
  )
}
