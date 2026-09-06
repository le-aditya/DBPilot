/**
 * Where tokens live.
 *
 * The access token stays in memory only, so it dies with the tab and never
 * sits in storage an XSS payload could read. The refresh token has to survive
 * a page reload for "stay signed in" to mean anything, so it goes to
 * localStorage — a deliberate trade-off. An httpOnly cookie would be stronger
 * but needs a cookie-based API, which PRD F1 does not describe.
 */

const REFRESH_KEY = 'dbpilot.refresh'

let accessToken: string | null = null

export function getAccessToken(): string | null {
  return accessToken
}

export function setAccessToken(token: string | null): void {
  accessToken = token
}

export function getRefreshToken(): string | null {
  try {
    return localStorage.getItem(REFRESH_KEY)
  } catch {
    return null
  }
}

export function setRefreshToken(token: string | null): void {
  try {
    if (token === null) localStorage.removeItem(REFRESH_KEY)
    else localStorage.setItem(REFRESH_KEY, token)
  } catch {
    // Private browsing can refuse storage. The session still works for this tab.
  }
}

export function clearTokens(): void {
  setAccessToken(null)
  setRefreshToken(null)
}
