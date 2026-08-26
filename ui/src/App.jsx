import { useEffect, useRef, useState } from 'react'
import { askQuestion, checkReady } from './api/client'
import AnswerCard from './components/AnswerCard'
import QuestionForm from './components/QuestionForm'
import './index.css'

const EXAMPLE_QUESTIONS = [
  'What is StellarDB?',
  'Who leads the Platform Team?',
  'When did TechNova acquire Stellar Systems?',
  'How does TechNova use machine learning in its products?',
  'What compliance certifications does TechNova hold?',
]

export default function App() {
  const [ready, setReady] = useState(null)       // null=checking, true/false
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [history, setHistory] = useState([])     // list of AskResponse
  const bottomRef = useRef(null)

  // Poll /ready once on mount
  useEffect(() => {
    checkReady().then(r => setReady(r.status === 'ready'))
  }, [])

  // Scroll to newest answer
  useEffect(() => {
    if (history.length) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [history.length])

  async function handleSubmit(question, topK) {
    setLoading(true)
    setError(null)
    try {
      const result = await askQuestion(question, topK)
      setHistory(h => [result, ...h])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  function handleExample(q) {
    handleSubmit(q, 5)
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100">
      {/* ── Header ── */}
      <header className="border-b border-slate-200 dark:border-slate-800
                         bg-white/80 dark:bg-slate-900/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span className="text-xl">🕸</span>
            <span className="font-semibold text-slate-800 dark:text-slate-200">
              KG-RAG
            </span>
            <span className="text-sm text-slate-400 dark:text-slate-500 hidden sm:inline">
              Enterprise Knowledge Graph Assistant
            </span>
          </div>
          <ReadyIndicator ready={ready} />
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-8 flex flex-col gap-8">
        {/* ── Question form ── */}
        <section>
          <QuestionForm
            onSubmit={handleSubmit}
            loading={loading}
            disabled={ready === false}
          />

          {/* Example pills */}
          {history.length === 0 && !loading && (
            <div className="mt-4 flex flex-wrap gap-2">
              {EXAMPLE_QUESTIONS.map(q => (
                <button
                  key={q}
                  onClick={() => handleExample(q)}
                  disabled={loading || ready === false}
                  className="text-xs px-3 py-1.5 rounded-full border border-slate-200
                             dark:border-slate-700 text-slate-600 dark:text-slate-400
                             hover:border-violet-400 hover:text-violet-700
                             dark:hover:border-violet-500 dark:hover:text-violet-300
                             transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {q}
                </button>
              ))}
            </div>
          )}
        </section>

        {/* ── Error ── */}
        {error && (
          <div className="rounded-xl border border-red-200 dark:border-red-800
                          bg-red-50 dark:bg-red-950/40 px-4 py-3 text-sm
                          text-red-700 dark:text-red-400">
            <strong>Error:</strong> {error}
          </div>
        )}

        {/* ── Loading skeleton ── */}
        {loading && (
          <div className="rounded-2xl border border-slate-200 dark:border-slate-700
                          bg-white dark:bg-slate-900 p-5 animate-pulse">
            <div className="h-3 bg-slate-200 dark:bg-slate-700 rounded w-1/3 mb-4"/>
            <div className="space-y-2">
              <div className="h-3 bg-slate-200 dark:bg-slate-700 rounded w-full"/>
              <div className="h-3 bg-slate-200 dark:bg-slate-700 rounded w-5/6"/>
              <div className="h-3 bg-slate-200 dark:bg-slate-700 rounded w-4/6"/>
            </div>
          </div>
        )}

        {/* ── Answer history ── */}
        <section className="flex flex-col gap-4">
          {history.map((result, i) => (
            <AnswerCard key={`${result.question}-${i}`} result={result} />
          ))}
          <div ref={bottomRef} />
        </section>

        {/* ── Empty state ── */}
        {history.length === 0 && !loading && (
          <EmptyState />
        )}
      </main>

      <footer className="border-t border-slate-200 dark:border-slate-800
                         text-center py-6 text-xs text-slate-400 dark:text-slate-600">
        Enterprise KG-RAG · Hybrid vector + knowledge graph retrieval · Built with Claude
      </footer>
    </div>
  )
}

function ReadyIndicator({ ready }) {
  if (ready === null) {
    return (
      <span className="flex items-center gap-1.5 text-xs text-slate-400">
        <span className="w-2 h-2 rounded-full bg-slate-300 animate-pulse"/>
        Connecting…
      </span>
    )
  }
  return ready ? (
    <span className="flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-400">
      <span className="w-2 h-2 rounded-full bg-emerald-500"/>
      Pipeline ready
    </span>
  ) : (
    <span className="flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400">
      <span className="w-2 h-2 rounded-full bg-amber-500"/>
      Pipeline loading…
    </span>
  )
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center gap-3 py-16 text-slate-400 dark:text-slate-600">
      <span className="text-5xl">🕸</span>
      <p className="text-sm text-center max-w-xs leading-relaxed">
        Ask a question about the TechNova corpus — the pipeline will route it,
        retrieve context, generate an answer, and validate every citation.
      </p>
      <div className="mt-4 grid grid-cols-3 gap-3 text-xs text-center">
        {[
          ['⚡', 'Vector', 'Definitions & facts'],
          ['🕸', 'Graph', 'Relationships & hops'],
          ['🔀', 'Hybrid', 'Multi-entity queries'],
        ].map(([icon, label, desc]) => (
          <div key={label} className="rounded-xl border border-slate-200 dark:border-slate-800
                                      p-3 flex flex-col gap-1">
            <span className="text-2xl">{icon}</span>
            <span className="font-medium text-slate-600 dark:text-slate-400">{label}</span>
            <span className="text-slate-400 dark:text-slate-600">{desc}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
