import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SavedQueries } from '../SavedQueries'

const apiFetch = vi.fn()

vi.mock('../../../lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}))

const QUERY = {
  id: 7,
  name: 'Top customers',
  sql_template: "SELECT name FROM people WHERE region = 'EU'",
  parameters: [],
  query_id: null,
  created_at: '2026-09-09T10:00:00Z',
}

const VERSIONS = [
  {
    id: 2,
    revision: 2,
    sql_template:
      "SELECT name FROM people\nWHERE region = 'EU'\nAND active = true",
    parameters: [],
    created_at: '2026-09-10T10:00:00Z',
  },
  {
    id: 1,
    revision: 1,
    sql_template: "SELECT name FROM people\nWHERE region = 'EU'",
    parameters: [],
    created_at: '2026-09-09T10:00:00Z',
  },
]

describe('SavedQueries', () => {
  beforeEach(() => {
    apiFetch.mockReset()
    apiFetch.mockImplementation((path: string) => {
      if (path === '/saved-queries') return Promise.resolve([QUERY])
      if (path === '/saved-queries/7/versions') return Promise.resolve(VERSIONS)
      return Promise.resolve(null)
    })
  })

  it('shows the diff between the two newest revisions', async () => {
    render(<SavedQueries sql="" onLoad={vi.fn()} />)
    await screen.findByText('Top customers')

    await userEvent.click(screen.getByRole('button', { name: /history/i }))

    expect(await screen.findByText(/AND active = true/)).toBeInTheDocument()
    expect(screen.getByText('1 added')).toBeInTheDocument()
    expect(screen.getByText('0 removed')).toBeInTheDocument()
  })

  it('loads a saved query back into the editor', async () => {
    const onLoad = vi.fn()
    render(<SavedQueries sql="" onLoad={onLoad} />)
    await screen.findByText('Top customers')

    await userEvent.click(screen.getByRole('button', { name: 'Load' }))

    expect(onLoad).toHaveBeenCalledWith(QUERY.sql_template)
  })

  it('invites a first save when nothing is stored', async () => {
    apiFetch.mockResolvedValue([])
    render(<SavedQueries sql="SELECT 1" onLoad={vi.fn()} />)

    expect(await screen.findByText(/nothing saved yet/i)).toBeInTheDocument()
  })
})
