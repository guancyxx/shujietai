// M1 auth: JWT token storage + 401 interception.
// Single source of truth for sjt_jwt; apiClient injects Bearer on every request
// and routes to /login on 401.

const TOKEN_KEY = 'sjt_jwt'
const USERNAME_KEY = 'sjt_username'

let onUnauthorized = null

export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn
}

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || ''
  } catch {
    return ''
  }
}

export function getUsername() {
  try {
    return localStorage.getItem(USERNAME_KEY) || ''
  } catch {
    return ''
  }
}

export function setSession(token, username) {
  try {
    localStorage.setItem(TOKEN_KEY, token)
    localStorage.setItem(USERNAME_KEY, username || '')
  } catch {
    // storage unavailable — session stays in-memory only for this tab
  }
}

export function clearSession() {
  try {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USERNAME_KEY)
  } catch {
    // ignore
  }
}

export function authHeaders() {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export function handleUnauthorized(detail) {
  // 401 除登录本身外一律视为会话失效：清 token 跳登录页
  if (detail === 'invalid_credentials') return
  clearSession()
  if (onUnauthorized) onUnauthorized()
}
