import { describe, expect, it } from 'vitest'

import { formatBytes, formatDuration, formatWhen } from '../format'

describe('formatBytes', () => {
  it('reports zero rather than NaN for an empty schema', () => {
    expect(formatBytes(0)).toBe('0 B')
  })

  it('keeps bytes whole and larger units readable', () => {
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(1536)).toBe('1.5 kB')
    expect(formatBytes(48 * 1024 * 1024)).toBe('48 MB')
  })
})

describe('formatDuration', () => {
  it('shows a dash when there is no timing rather than 0 ms', () => {
    expect(formatDuration(null)).toBe('—')
  })

  it('switches to seconds once milliseconds stop reading well', () => {
    expect(formatDuration(940)).toBe('940 ms')
    expect(formatDuration(2400)).toBe('2.4 s')
  })
})

describe('formatWhen', () => {
  const now = new Date('2026-09-09T12:00:00Z')

  it('reads relatively while that is still useful', () => {
    expect(formatWhen('2026-09-09T11:59:30Z', now)).toBe('just now')
    expect(formatWhen('2026-09-09T11:30:00Z', now)).toBe('30 min ago')
    expect(formatWhen('2026-09-08T12:00:00Z', now)).toBe('1 d ago')
  })

  it('falls back to a date once a relative time stops being useful', () => {
    expect(formatWhen('2026-01-05T12:00:00Z', now)).toMatch(/Jan/)
  })
})
