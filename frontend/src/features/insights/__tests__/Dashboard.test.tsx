import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { DashboardResponse } from '../../../lib/types'
import { Dashboard } from '../Dashboard'

const apiFetch = vi.fn()

vi.mock('../../../lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}))

const DATA: DashboardResponse = {
  table_count: 4,
  total_rows: 1234,
  storage_bytes: 49152,
  queries_run: 40,
  queries_this_week: 12,
  blocked_count: 3,
  average_duration_ms: 84,
  slowest: [
    {
      id: 1,
      question_text: null,
      executed_sql: 'SELECT * FROM orders',
      status: 'success',
      row_count: 100,
      duration_ms: 940,
      was_edited: false,
      error_message: null,
      created_at: '2026-09-09T10:00:00Z',
    },
  ],
  recent: [
    {
      id: 2,
      question_text: 'who spent the most?',
      executed_sql: 'SELECT 1',
      status: 'blocked',
      row_count: null,
      duration_ms: null,
      was_edited: false,
      error_message: 'blocked',
      created_at: '2026-09-09T11:00:00Z',
    },
  ],
}

describe('Dashboard', () => {
  beforeEach(() => {
    apiFetch.mockReset()
    apiFetch.mockResolvedValue(DATA)
  })

  it('highlights exactly one metric', async () => {
    // PRD 10.9: one highlighted metric per view, so the accent keeps meaning.
    const { container } = render(<Dashboard projectId={1} />)
    await screen.findByText('12')

    expect(container.querySelectorAll('.text-accent')).toHaveLength(1)
  })

  it('reports totals alongside the highlighted figure', async () => {
    render(<Dashboard projectId={1} />)

    expect(await screen.findByText(/40 in total/)).toBeInTheDocument()
    expect(screen.getByText(/3 blocked/)).toBeInTheDocument()
  })

  it('formats the data size rather than printing raw bytes', async () => {
    render(<Dashboard projectId={1} />)

    expect(await screen.findByText(/48 kB/)).toBeInTheDocument()
  })

  it('shows recent activity with a status marker', async () => {
    render(<Dashboard projectId={1} />)

    expect(await screen.findByText('who spent the most?')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'blocked' })).toBeInTheDocument()
  })

  it('invites a first question when nothing has run', async () => {
    apiFetch.mockResolvedValue({ ...DATA, recent: [], slowest: [], queries_run: 0 })
    render(<Dashboard projectId={1} />)

    expect(await screen.findByText(/ask your first question/i)).toBeInTheDocument()
  })
})
