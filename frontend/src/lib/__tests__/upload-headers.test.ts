import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { apiFetch } from '../api'
import { setAccessToken } from '../auth-storage'

describe('request content types', () => {
  beforeEach(() => {
    setAccessToken('token')
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('{}', { status: 200 })),
    )
  })
  afterEach(() => vi.unstubAllGlobals())

  it('leaves Content-Type to the browser for FormData', async () => {
    // The multipart boundary is part of the header, so setting it ourselves
    // makes the server unable to parse the body.
    await apiFetch('/x', { method: 'POST', body: new FormData() })

    const init = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1]
    expect((init.headers as Headers).has('Content-Type')).toBe(false)
  })

  it('still sets JSON for a string body', async () => {
    await apiFetch('/x', { method: 'POST', body: JSON.stringify({ a: 1 }) })

    const init = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1]
    expect((init.headers as Headers).get('Content-Type')).toBe('application/json')
  })
})
