import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { HistoryResponse } from '../../../lib/types'
import { History } from '../History'

const apiFetch = vi.fn()

vi.mock('../../../lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}))

const DATA: HistoryResponse = {
  total: 2,
  limit: 25,
  offset: 0,
  queries: [
    {
      id: 2,
      question_text: 'remove everyone',
      executed_sql: null,
      status: 'blocked',
      row_count: null,
      duration_ms: null,
      was_edited: false,
      error_message: 'DBPilot only runs SELECT statements.',
      created_at: '2026-09-09T11:00:00Z',
    },
    {
      id: 1,
      question_text: null,
      executed_sql: 'SELECT * FROM people',
      status: 'success',
      row_count: 3,
      duration_ms: 12,
      was_edited: true,
      error_message: null,
      created_at: '2026-09-09T10:00:00Z',
    },
  ],
}

describe('History', () => {
  beforeEach(() => {
    apiFetch.mockReset()
    apiFetch.mockResolvedValue(DATA)
  })

  it('lists blocked attempts alongside successful ones', async () => {
    // PRD F8: blocked attempts are the safety record, never hidden.
    render(<History projectId={1} />)

    expect(await screen.findByText('remove everyone')).toBeInTheDocument()
    expect(screen.getByText('SELECT * FROM people')).toBeInTheDocument()
  })

  it('shows why a query was blocked', async () => {
    render(<History projectId={1} />)

    expect(await screen.findByText(/only runs SELECT/)).toBeInTheDocument()
  })

  it('marks an edited query as edited', async () => {
    render(<History projectId={1} />)

    expect(await screen.findByText('edited')).toBeInTheDocument()
  })

  it('filters by status through the API rather than in the browser', async () => {
    render(<History projectId={1} />)
    await screen.findByText('remove everyone')

    await userEvent.click(screen.getByRole('button', { name: 'blocked' }))

    expect(apiFetch).toHaveBeenLastCalledWith(
      expect.stringContaining('status_filter=blocked'),
    )
  })

  it('hands a query back to the workspace when asked', async () => {
    const onReuse = vi.fn()
    render(<History projectId={1} onReuse={onReuse} />)
    await screen.findByText('SELECT * FROM people')

    await userEvent.click(screen.getByRole('button', { name: /reuse/i }))

    expect(onReuse).toHaveBeenCalledWith('SELECT * FROM people')
  })

  it('invites a first question when there is no history', async () => {
    apiFetch.mockResolvedValue({ ...DATA, queries: [], total: 0 })
    render(<History projectId={1} />)

    expect(await screen.findByText(/ask your first question/i)).toBeInTheDocument()
  })
})
