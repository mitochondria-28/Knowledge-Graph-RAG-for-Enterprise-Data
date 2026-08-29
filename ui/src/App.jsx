import { useCallback, useEffect, useRef, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { askQuestion, checkReady, listDocuments } from './api/client'
import AnswerCard from './components/AnswerCard'
import DocumentList from './components/DocumentList'
import DocumentUpload from './components/DocumentUpload'
import QuestionForm from './components/QuestionForm'
import { useAuth } from './context/AuthContext'
import './index.css'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'

export default function App() {
  return (
    <Routes>
      <Route path="/login"    element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/*"        element={<ProtectedShell />} />
    </Routes>
  )
}

function ProtectedShell() {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex items-center justify-center">
        <span className="text-slate-400 text-sm animate-pulse">Loading…</span>
      </div>
    )
  }

  if (!user) return <Navigate to="/login" replace />
  return <MainApp />
}

function MainApp() {
  const { user, signOut }                = useAuth()
  const [ready, setReady]               = useState(null)
  const [loading, setLoading]           = useState(false)
  const [error, setError]               = useState(null)
  const [history, setHistory]           = useState([])
  const [activeTab, setActiveTab]       = useState('ask')
  const [docRefresh, setDocRefresh]     = useState(0)
  const [showUserMenu, setShowUserMenu] = useState(false)
  const [hasDocuments, setHasDocuments] = useState(null)  // null=unknown, true/false
  const bottomRef = useRef(null)

  // Check whether user has any documents
  useEffect(() => {
    checkReady().then(r => setReady(r.status === 'ready'))
    listDocuments().then(docs => setHasDocuments(docs.length > 0))
  }, [])

  // Re-check after an upload
  const handleUploaded = useCallback(() => {
    setDocRefresh(n => n + 1)
    listDocuments().then(docs => setHasDocuments(docs.length > 0))
  }, [])

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
      if (err.status === 401) { signOut(); return }
      // Empty corpus — nudge the user to upload
      if (err.status === 400 && err.message.includes('empty')) {
        setActiveTab('documents')
        return
      }
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100">
      {/* ── Header ── */}
      <header className="border-b border-slate-200 dark:border-slate-800
                         bg-white/80 dark:bg-slate-900/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center justify-between gap-4">
          {/* Branding */}
          <div className="flex items-center gap-2.5 shrink-0">
            <span className="text-xl">🕸</span>
            <span className="font-semibold text-slate-800 dark:text-slate-200">KG-RAG</span>
            <span className="text-sm text-slate-400 dark:text-slate-500 hidden sm:inline">
              Enterprise Knowledge Graph Assistant
            </span>
          </div>

          {/* Tab switcher */}
          <nav className="flex items-center gap-1 rounded-lg border border-slate-200 dark:border-slate-800 p-0.5">
            {[
              { id: 'ask',       label: 'Ask',       icon: '💬' },
              { id: 'documents', label: 'Documents',  icon: '📄' },
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={[
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors',
                  activeTab === tab.id
                    ? 'bg-violet-600 text-white'
                    : 'text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200',
                ].join(' ')}
              >
                <span>{tab.icon}</span>
                {tab.label}
              </button>
            ))}
          </nav>

          <div className="flex items-center gap-3">
            <ReadyIndicator ready={ready} />

            {/* User menu */}
            <div className="relative">
              <button
                onClick={() => setShowUserMenu(v => !v)}
                className="flex items-center gap-2 rounded-lg px-2 py-1 text-xs
                           text-slate-600 dark:text-slate-400
                           hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
              >
                {user.avatar_url ? (
                  <img src={user.avatar_url} alt="avatar"
                    className="w-6 h-6 rounded-full object-cover" />
                ) : (
                  <span className="w-6 h-6 rounded-full bg-violet-600 flex items-center justify-center
                                   text-white font-semibold text-xs">
                    {(user.name ?? user.email)[0].toUpperCase()}
                  </span>
                )}
                <span className="hidden sm:inline max-w-24 truncate">
                  {user.name ?? user.email}
                </span>
                <span>▾</span>
              </button>

              {showUserMenu && (
                <div className="absolute right-0 mt-1 w-52 rounded-xl border border-slate-200
                                dark:border-slate-700 bg-white dark:bg-slate-900 shadow-lg
                                py-1 z-50 text-sm">
                  <div className="px-4 py-2 border-b border-slate-100 dark:border-slate-800">
                    <p className="font-medium text-slate-800 dark:text-slate-100 truncate">
                      {user.name ?? ''}
                    </p>
                    <p className="text-xs text-slate-400 truncate">{user.email}</p>
                  </div>
                  <button
                    onClick={() => { setShowUserMenu(false); signOut() }}
                    className="w-full text-left px-4 py-2 text-slate-600 dark:text-slate-400
                               hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
                  >
                    Sign out
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-8">
        {activeTab === 'ask' && (
          <div className="flex flex-col gap-8">
            <section>
              <QuestionForm
                onSubmit={handleSubmit}
                loading={loading}
                disabled={ready === false || hasDocuments === false}
              />
            </section>

            {error && (
              <div className="rounded-xl border border-red-200 dark:border-red-800
                              bg-red-50 dark:bg-red-950/40 px-4 py-3 text-sm
                              text-red-700 dark:text-red-400">
                <strong>Error:</strong> {error}
              </div>
            )}

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

            <section className="flex flex-col gap-4">
              {history.map((result, i) => (
                <AnswerCard key={`${result.question}-${i}`} result={result} />
              ))}
              <div ref={bottomRef} />
            </section>

            {history.length === 0 && !loading && (
              hasDocuments === false
                ? <NoDocumentsState onGoUpload={() => setActiveTab('documents')} />
                : <EmptyState />
            )}
          </div>
        )}

        {activeTab === 'documents' && (
          <div className="flex flex-col gap-8">
            <section className="rounded-2xl border border-slate-200 dark:border-slate-800
                                bg-white dark:bg-slate-900 p-6 flex flex-col gap-5">
              <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wide">
                Upload document
              </h2>
              <DocumentUpload onUploaded={handleUploaded} />
            </section>

            <section className="rounded-2xl border border-slate-200 dark:border-slate-800
                                bg-white dark:bg-slate-900 p-6">
              <DocumentList refreshTrigger={docRefresh} />
            </section>
          </div>
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
      <span className="flex items-center gap-1.5 text-xs text-slate-400 shrink-0">
        <span className="w-2 h-2 rounded-full bg-slate-300 animate-pulse"/>
        Connecting…
      </span>
    )
  }
  return ready ? (
    <span className="flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-400 shrink-0">
      <span className="w-2 h-2 rounded-full bg-emerald-500"/>
      Pipeline ready
    </span>
  ) : (
    <span className="flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400 shrink-0">
      <span className="w-2 h-2 rounded-full bg-amber-500"/>
      Pipeline loading…
    </span>
  )
}

function NoDocumentsState({ onGoUpload }) {
  return (
    <div className="flex flex-col items-center gap-4 py-16 text-center">
      <span className="text-6xl">📂</span>
      <div>
        <p className="text-base font-semibold text-slate-700 dark:text-slate-300">
          Your knowledge base is empty
        </p>
        <p className="text-sm text-slate-400 dark:text-slate-500 mt-1 max-w-xs mx-auto">
          Upload your company documents first — then ask questions about them.
          Your data is private and isolated to your account.
        </p>
      </div>
      <button
        onClick={onGoUpload}
        className="mt-2 px-5 py-2 bg-violet-600 hover:bg-violet-700
                   text-white text-sm font-medium rounded-lg transition-colors"
      >
        Upload documents
      </button>
      <div className="mt-4 grid grid-cols-3 gap-3 text-xs text-center text-slate-400 dark:text-slate-600">
        {[
          ['📄', 'PDF / MD / TXT', 'Any company doc'],
          ['🔒', 'Private', 'Only you can see it'],
          ['⚡', 'Instant', 'Query right after upload'],
        ].map(([icon, label, desc]) => (
          <div key={label} className="rounded-xl border border-slate-200 dark:border-slate-800 p-3 flex flex-col gap-1">
            <span className="text-2xl">{icon}</span>
            <span className="font-medium text-slate-600 dark:text-slate-400">{label}</span>
            <span>{desc}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center gap-3 py-16 text-slate-400 dark:text-slate-600">
      <span className="text-5xl">🕸</span>
      <p className="text-sm text-center max-w-xs leading-relaxed">
        Ask a question about your documents — the pipeline will route it,
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
