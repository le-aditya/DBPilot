import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ProjectDetail } from '../ProjectDetail'

const apiFetch = vi.fn()

vi.mock('../../lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
  apiRaw: vi.fn(),
  ApiError: class ApiError extends Error {},
}))

const PROJECT = {
  id: 1,
  name: 'Sales',
  source_type: 'upload',
  schema_name: 'user_1_sales',
  table_count: 1,
  is_demo: false,
  created_at: '2026-09-09T10:00:00Z',
}

const SCHEMA = {
  schema_name: 'user_1_sales',
  tables: [
    {
      name: 'people',
      row_count: 3,
      columns: [
        {
          name: 'name',
          data_type: 'text',
          nullable: false,
          default: null,
          is_primary_key: false,
          references_table: null,
          references_column: null,
        },
      ],
      indexes: [],
    },
  ],
}

const HISTORY = {
  total: 1,
  limit: 25,
  offset: 0,
  queries: [
    {
      id: 9,
      question_text: 'who is in the table?',
      executed_sql: 'SELECT name FROM people',
      status: 'success',
      row_count: 3,
      duration_ms: 11,
      was_edited: false,
      error_message: null,
      created_at: '2026-09-09T10:00:00Z',
    },
  ],
}

const DASHBOARD = {
  table_count: 1,
  total_rows: 3,
  storage_bytes: 8192,
  queries_run: 1,
  queries_this_week: 1,
  blocked_count: 0,
  average_duration_ms: 11,
  slowest: [],
  recent: [],
}

function route(path: string) {
  if (path.startsWith('/projects/1/schema')) return SCHEMA
  if (path.startsWith('/projects/1/dashboard')) return DASHBOARD
  if (path.startsWith('/projects/1/history')) return HISTORY
  if (path === '/projects/1') return PROJECT
  return {}
}

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={['/projects/1']}>
      <Routes>
        <Route path="/projects/:projectId" element={<ProjectDetail />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ProjectDetail', () => {
  beforeEach(() => {
    apiFetch.mockReset()
    apiFetch.mockImplementation((path: string) => Promise.resolve(route(path)))
  })

  it('keeps a half-written query when you visit another tab and come back', async () => {
    // Reported in use: switching tabs used to unmount the workspace, so the
    // question, SQL and results were gone on return.
    renderDetail()
    const editor = await screen.findByLabelText(/^sql$/i)
    await userEvent.type(editor, 'SELECT 1')

    await userEvent.click(screen.getByRole('button', { name: 'Dashboard' }))
    await userEvent.click(screen.getByRole('button', { name: 'Query' }))

    expect(screen.getByLabelText(/^sql$/i)).toHaveValue('SELECT 1')
  })

  it('loads a query from history back into the workspace', async () => {
    // Reported in use: history listed queries but nothing could be opened,
    // because onReuse was never passed and the Reuse button never rendered.
    renderDetail()
    await screen.findByLabelText(/^sql$/i)

    await userEvent.click(screen.getByRole('button', { name: 'History' }))
    await userEvent.click(await screen.findByRole('button', { name: /reuse/i }))

    expect(screen.getByLabelText(/^sql$/i)).toHaveValue('SELECT name FROM people')
  })

  it('returns to the query tab after reusing, so the SQL is visible', async () => {
    renderDetail()
    await screen.findByLabelText(/^sql$/i)
    await userEvent.click(screen.getByRole('button', { name: 'History' }))

    await userEvent.click(await screen.findByRole('button', { name: /reuse/i }))

    expect(screen.getByRole('button', { name: 'Query' })).toHaveAttribute(
      'aria-current',
      'true',
    )
  })

  it('offers Data rather than Schema, since the diagram already lists columns', async () => {
    renderDetail()
    await screen.findByLabelText(/^sql$/i)

    expect(screen.getByRole('button', { name: 'Data' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Schema' })).not.toBeInTheDocument()
  })

  it('shows the upload panel when the project has no tables yet', async () => {
    apiFetch.mockImplementation((path: string) =>
      Promise.resolve(
        path.startsWith('/projects/1/schema')
          ? { schema_name: null, tables: [] }
          : route(path),
      ),
    )
    renderDetail()

    expect(await screen.findByText(/add a csv/i)).toBeInTheDocument()
  })
})
