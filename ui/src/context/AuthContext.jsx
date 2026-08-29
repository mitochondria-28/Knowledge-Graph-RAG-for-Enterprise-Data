import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { clearToken, fetchMe, getToken, saveToken } from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser]       = useState(null)
  const [loading, setLoading] = useState(true)  // true while checking stored token

  // On mount: try to restore session from localStorage
  useEffect(() => {
    const token = getToken()
    if (!token) { setLoading(false); return }
    fetchMe()
      .then(u => setUser(u))
      .catch(() => clearToken())  // token expired/invalid — drop it
      .finally(() => setLoading(false))
  }, [])

  const signIn = useCallback((tokenWithUser) => {
    saveToken(tokenWithUser.access_token)
    setUser(tokenWithUser.user)
  }, [])

  const signOut = useCallback(() => {
    clearToken()
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{ user, loading, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
