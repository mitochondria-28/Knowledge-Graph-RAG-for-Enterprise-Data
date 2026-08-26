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
