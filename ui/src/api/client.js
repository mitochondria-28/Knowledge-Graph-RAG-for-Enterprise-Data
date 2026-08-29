const BASE = import.meta.env.VITE_API_URL ?? ''

const TOKEN_KEY = 'kg_rag_token'

export function saveToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

function authHeaders() {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function apiRequest(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      ...authHeaders(),
      ...(options.headers ?? {}),
    },
  })
  if (!res.ok) {
    const text = await res.text().catch(() => 'Unknown error')
    const err = new Error(`API ${res.status}: ${text}`)
    err.status = res.status
    throw err
  }
  return res.json()
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export async function register(email, password, name) {
  return apiRequest('/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, name }),
  })
}

export async function login(email, password) {
  return apiRequest('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
}

export async function googleAuth(credential) {
  return apiRequest('/auth/google', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ credential }),
  })
}

export async function fetchMe() {
  return apiRequest('/auth/me')
}

// ── Pipeline ──────────────────────────────────────────────────────────────────

export async function askQuestion(question, topK = 5) {
  return apiRequest('/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, top_k: topK }),
  })
}

export async function checkReady() {
  try {
    return await apiRequest('/ready')
  } catch {
    return { status: 'not_ready', chunk_count: 0 }
  }
}

export async function uploadDocument(file, docType = 'general') {
  const form = new FormData()
  form.append('file', file)
  form.append('doc_type', docType)
  return apiRequest('/documents/upload', { method: 'POST', body: form })
}

export async function listDocuments() {
  try {
    return await apiRequest('/documents')
  } catch {
    return []
  }
}
