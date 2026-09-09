import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setAccessToken,
  setRefreshToken,
} from './auth-storage'

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000'

export interface ApiFieldError {
  field: string
  message: string
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  /** Per-field reasons from a 422. The envelope's top-level message is generic,
   *  so this is where the actionable detail lives (PRD section 9). */
  readonly fields: ApiFieldError[]

  constructor(
    status: number,
    code: string,
    message: string,
    fields: ApiFieldError[] = [],
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.fields = fields
  }
}

export interface AuthPayload {
  access_token: string
  refresh_token: string
  token_type: string
  user: { id: number; email: string }
}

async function toError(response: Response): Promise<ApiError> {
  let code = 'http_error'
  let message = 'Something went wrong. Try again.'
  let fields: ApiFieldError[] = []
  try {
    const body = await response.json()
    if (body?.error) {
      code = body.error.code ?? code
      message = body.error.message ?? message
      if (Array.isArray(body.error.fields)) fields = body.error.fields
    }
  } catch {
    // A non-JSON body leaves the defaults, which are already readable.
  }
  return new ApiError(response.status, code, message, fields)
}

function request(path: string, options: RequestInit): Promise<Response> {
  const headers = new Headers(options.headers)
  // FormData must set its own Content-Type: the boundary is part of it, and
  // overriding it with application/json makes the server see a malformed body.
  if (
    !headers.has('Content-Type') &&
    options.body !== undefined &&
    !(options.body instanceof FormData)
  ) {
    headers.set('Content-Type', 'application/json')
  }
  const token = getAccessToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  return fetch(`${BASE_URL}${path}`, { ...options, headers })
}

async function exchangeRefreshToken(): Promise<boolean> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) return false

  const response = await fetch(`${BASE_URL}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
  if (!response.ok) {
    clearTokens()
    return false
  }

  const payload: AuthPayload = await response.json()
  setAccessToken(payload.access_token)
  setRefreshToken(payload.refresh_token)
  return true
}

let inFlightRefresh: Promise<boolean> | null = null

/**
 * Exchange the refresh token for a new pair. Returns false if it failed.
 *
 * Single-flighted on purpose. Refresh tokens rotate, so a second request
 * carrying the same token is indistinguishable from a replayed stolen one and
 * the server revokes every session for the user. Concurrent callers are
 * routine — React StrictMode double-invokes mount effects, and any two
 * parallel requests can hit an expired access token at once — so they share
 * one exchange instead of racing.
 */
export function refreshSession(): Promise<boolean> {
  if (inFlightRefresh) return inFlightRefresh

  inFlightRefresh = exchangeRefreshToken().finally(() => {
    inFlightRefresh = null
  })
  return inFlightRefresh
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  let response = await request(path, options)

  // Exactly one retry. The access token expires every 30 minutes, so a 401 on
  // an otherwise valid session is routine and should not reach the user.
  if (response.status === 401 && (await refreshSession())) {
    response = await request(path, options)
  }

  if (!response.ok) throw await toError(response)
  if (response.status === 204) return null as T
  return (await response.json()) as T
}

/** POST a multipart body. Content-Type is left to the browser — see request(). */
export function apiUpload<T>(path: string, body: FormData): Promise<T> {
  return apiFetch<T>(path, { method: 'POST', body })
}

/**
 * Like apiFetch, but returns the Response.
 *
 * Downloads need the body as a blob and the filename from the caller, and a
 * plain <a href> would drop the Authorization header entirely.
 */
export async function apiRaw(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
  let response = await request(path, options)
  if (response.status === 401 && (await refreshSession())) {
    response = await request(path, options)
  }
  if (!response.ok) throw await toError(response)
  return response
}
