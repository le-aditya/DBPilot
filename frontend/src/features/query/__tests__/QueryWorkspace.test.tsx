import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ExecuteResponse, ProjectSchema } from '../../../lib/types'
import { QueryWorkspace } from '../QueryWorkspace'

const apiFetch = vi.fn()

vi.mock('../../../lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
  ApiError: class ApiError extends Error {},
}))

const SCHEMA: ProjectSchema = {
  schema_name: 'user_1_sales',
  tables: [
    {
      name: 'orders',
      row_count: 2,
      columns: [
        {
          name: 'amount',
          data_type: 'numeric',
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

const SUCCESS: ExecuteResponse = {
  query_id: 1,
  status: 'success',
  columns: ['amount'],
  rows: [['10.50']],
  row_count: 1,
  duration_ms: 12,
  executed_sql: 'SELECT amount FROM orders LIMIT 1000',
  truncated: false,
  error: null,
  rule: null,
}

function renderWorkspace() {
  render(<QueryWorkspace projectId={1} schema={SCHEMA} />)
}

describe('QueryWorkspace', () => {
  beforeEach(() => apiFetch.mockReset())

  it('shows the generated SQL and its results', async () => {
    apiFetch.mockResolvedValueOnce({
      sql: 'SELECT amount FROM orders',
      assumptions: [],
      confidence: 'high',
      missing: null,
      cached: false,
      execution: SUCCESS,
    })
    renderWorkspace()

    await userEvent.type(screen.getByLabelText(/ask a question/i), 'amounts')
    await userEvent.click(screen.getByRole('button', { name: /generate sql/i }))

    expect(await screen.findByDisplayValue('SELECT amount FROM orders')).toBeInTheDocument()
    expect(screen.getByText('10.50')).toBeInTheDocument()
  })

  it('surfaces assumptions as chips rather than burying them', async () => {
    apiFetch.mockResolvedValueOnce({
      sql: 'SELECT 1',
      assumptions: ["assumed 'last month' = previous calendar month"],
      confidence: 'medium',
      missing: null,
      cached: false,
      execution: SUCCESS,
    })
    renderWorkspace()

    await userEvent.type(screen.getByLabelText(/ask a question/i), 'last month')
    await userEvent.click(screen.getByRole('button', { name: /generate sql/i }))

    expect(
      await screen.findByText(/previous calendar month/),
    ).toBeInTheDocument()
  })

  it('says what is missing instead of showing invented SQL', async () => {
    apiFetch.mockResolvedValueOnce({
      sql: '',
      assumptions: [],
      confidence: 'low',
      missing: 'No table contains a purchase date.',
      cached: false,
      execution: null,
    })
    renderWorkspace()

    await userEvent.type(screen.getByLabelText(/ask a question/i), 'sales by date')
    await userEvent.click(screen.getByRole('button', { name: /generate sql/i }))

    expect(await screen.findByText(/no table contains a purchase date/i)).toBeInTheDocument()
  })

  it('explains a blocked query and names the rule', async () => {
    apiFetch.mockResolvedValueOnce({
      ...SUCCESS,
      status: 'blocked',
      rule: 'writes_data',
      error: 'DBPilot only runs SELECT statements.',
      executed_sql: null,
      rows: [],
      row_count: 0,
    })
    renderWorkspace()

    await userEvent.type(screen.getByLabelText(/^sql$/i), 'DELETE FROM orders')
    await userEvent.click(screen.getByRole('button', { name: /run query/i }))

    expect(await screen.findByText(/writes data/i)).toBeInTheDocument()
    expect(screen.getByText(/only runs SELECT/i)).toBeInTheDocument()
  })

  it('keeps the editor usable when the assistant is unavailable', async () => {
    // PRD 13: an outage degrades the feature, it does not remove the product.
    apiFetch.mockRejectedValueOnce(new Error('AI is not configured on this server.'))
    renderWorkspace()
    await userEvent.type(screen.getByLabelText(/ask a question/i), 'anything')
    await userEvent.click(screen.getByRole('button', { name: /generate sql/i }))
    await screen.findByRole('alert')

    apiFetch.mockResolvedValueOnce(SUCCESS)
    await userEvent.type(screen.getByLabelText(/^sql$/i), 'SELECT amount FROM orders')
    await userEvent.click(screen.getByRole('button', { name: /run query/i }))

    expect(await screen.findByText('10.50')).toBeInTheDocument()
  })

  it('reports an edited query as edited', async () => {
    apiFetch.mockResolvedValueOnce({
      sql: 'SELECT 1',
      assumptions: [],
      confidence: 'high',
      missing: null,
      cached: false,
      execution: SUCCESS,
    })
    renderWorkspace()
    await userEvent.type(screen.getByLabelText(/ask a question/i), 'q')
    await userEvent.click(screen.getByRole('button', { name: /generate sql/i }))
    await screen.findByDisplayValue('SELECT 1')

    await userEvent.type(screen.getByLabelText(/^sql$/i), ' + 1')
    apiFetch.mockResolvedValueOnce(SUCCESS)
    await userEvent.click(screen.getByRole('button', { name: /run query/i }))

    await waitFor(() => {
      const call = apiFetch.mock.calls.at(-1)
      expect(call).toBeDefined()
      expect(JSON.parse(call![1].body as string).was_edited).toBe(true)
    })
  })

  it('inserts a column name from the rail into the SQL', async () => {
    renderWorkspace()

    await userEvent.click(screen.getByRole('button', { name: /insert amount/i }))

    expect(screen.getByLabelText(/^sql$/i)).toHaveValue('amount')
  })
})
