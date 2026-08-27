const BASE = import.meta.env.VITE_API_URL ?? ''

/**
 * POST /ask — sends a question to the RAG pipeline.
 * @param {string} question
 * @param {number} topK
 * @returns {Promise<import('./types').AskResponse>}
 */
export async function askQuestion(question, topK = 5) {
  const res = await fetch(`${BASE}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, top_k: topK }),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => 'Unknown error')
    throw new Error(`API ${res.status}: ${text}`)
  }
  return res.json()
}

/**
 * GET /ready — checks whether the pipeline has loaded.
 * @returns {Promise<{status: string, chunk_count: number}>}
 */
export async function checkReady() {
  const res = await fetch(`${BASE}/ready`)
  if (!res.ok) return { status: 'not_ready', chunk_count: 0 }
  return res.json()
}

/**
 * POST /documents/upload — upload a file and ingest it into the corpus.
 * @param {File} file
 * @param {string} docType — one of: general, company, project, technology, people
 * @returns {Promise<{filename: string, doc_type: string, stats: object}>}
 */
export async function uploadDocument(file, docType = 'general') {
  const form = new FormData()
  form.append('file', file)
  form.append('doc_type', docType)
  const res = await fetch(`${BASE}/documents/upload`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => 'Unknown error')
    throw new Error(`Upload failed (${res.status}): ${text}`)
  }
  return res.json()
}

/**
 * GET /documents — list all ingested documents.
 * @returns {Promise<Array<{title: string, doc_type: string, chunk_count: number, ingested_at: string}>>}
 */
export async function listDocuments() {
  const res = await fetch(`${BASE}/documents`)
  if (!res.ok) return []
  return res.json()
}
