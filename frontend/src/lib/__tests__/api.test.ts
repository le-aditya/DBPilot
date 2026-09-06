import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError, apiFetch, refreshSession } from '../api'
import { clearTokens, setAccessToken, setRefreshToken } from '../auth-storage'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const AUTH_PAYLOAD = {
  access_token: 'fresh-token',
  refresh_token: 'refresh-def',
  token_type: 'bearer',
  user: { id: 1, email: 'ada@example.com' },
}

function unauthorized(): Response {
  return jsonResponse({ error: { code: 'unauthorized', message: 'no' } }, 401)
}

describe('apiFetch', () => {
  beforeEach(() => {
    clearTokens()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    clearTokens()
  })

  it('returns the parsed body on success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ id: 1, name: 'Sales' })),
    )

    await expect(apiFetch('/projects/1')).resolves.toEqual({
      id: 1,
      name: 'Sales',
    })
  })

  it('attaches the access token as a bearer header', async () => {
    setAccessToken('token-abc')
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]))
    vi.stubGlobal('fetch', fetchMock)

    await apiFetch('/projects')

    const headers = new Headers(fetchMock.mock.calls[0][1].headers)
    expect(headers.get('Authorization')).toBe('Bearer token-abc')
  })

  it('sends no Authorization header when signed out', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]))
    vi.stubGlobal('fetch', fetchMock)

    await apiFetch('/projects')

    const headers = new Headers(fetchMock.mock.calls[0][1].headers)
    expect(headers.get('Authorization')).toBeNull()
  })

  it('refreshes once on 401 and replays the original request', async () => {
    setAccessToken('stale-token')
    setRefreshToken('refresh-abc')
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(unauthorized())
      .mockResolvedValueOnce(jsonResponse(AUTH_PAYLOAD))
      .mockResolvedValueOnce(jsonResponse([{ id: 1, name: 'Sales' }]))
    vi.stubGlobal('fetch', fetchMock)

    const result = await apiFetch('/projects')

    expect(result).toEqual([{ id: 1, name: 'Sales' }])
    expect(fetchMock).toHaveBeenCalledTimes(3)
    const replayHeaders = new Headers(fetchMock.mock.calls[2][1].headers)
    expect(replayHeaders.get('Authorization')).toBe('Bearer fresh-token')
  })

  it('does not retry more than once', async () => {
    setAccessToken('stale-token')
    setRefreshToken('refresh-abc')
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(unauthorized())
      .mockResolvedValueOnce(jsonResponse(AUTH_PAYLOAD))
      .mockResolvedValueOnce(unauthorized())
    vi.stubGlobal('fetch', fetchMock)

    await expect(apiFetch('/projects')).rejects.toBeInstanceOf(ApiError)
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('clears the session when the refresh itself fails', async () => {
    setAccessToken('stale-token')
    setRefreshToken('dead-refresh')
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(unauthorized())
        .mockResolvedValueOnce(unauthorized()),
    )

    await expect(apiFetch('/projects')).rejects.toBeInstanceOf(ApiError)
    const { getAccessToken } = await import('../auth-storage')
    expect(getAccessToken()).toBeNull()
  })

  it('surfaces the error envelope message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          { error: { code: 'conflict', message: 'That name is taken.' } },
          409,
        ),
      ),
    )

    await expect(apiFetch('/projects', { method: 'POST' })).rejects.toMatchObject({
      status: 409,
      code: 'conflict',
      message: 'That name is taken.',
    })
  })

  it('carries the per-field reasons from a 422', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            error: {
              code: 'validation_error',
              message: 'The request body was not valid.',
              fields: [{ field: 'email', message: 'not a valid email address' }],
            },
          },
          422,
        ),
      ),
    )

    // The top-level message is generic; the reason lives in fields.
    await expect(apiFetch('/auth/register', { method: 'POST' })).rejects.toMatchObject({
      fields: [{ field: 'email', message: 'not a valid email address' }],
    })
  })

  it('shares one refresh between concurrent callers', async () => {
    // Two POSTs with the same refresh token look like a replay to the server,
    // which revokes the whole family and signs the user out. React StrictMode
    // double-invokes mount effects, so this fires on every dev page load.
    setRefreshToken('refresh-abc')
    const fetchMock = vi.fn().mockImplementation(
      () =>
        new Promise((resolve) =>
          setTimeout(() => resolve(jsonResponse(AUTH_PAYLOAD)), 10),
        ),
    )
    vi.stubGlobal('fetch', fetchMock)

    const results = await Promise.all([refreshSession(), refreshSession()])

    expect(results).toEqual([true, true])
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('returns null for a 204', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(null, { status: 204 })),
    )

    await expect(apiFetch('/projects/1', { method: 'DELETE' })).resolves.toBeNull()
  })
})
