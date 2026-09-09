import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ProjectSchema } from '../../../lib/types'
import { SchemaExplorer } from '../SchemaExplorer'

const apiFetch = vi.fn()

vi.mock('../../../lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}))

const SCHEMA: ProjectSchema = {
  schema_name: 'user_1_sales',
  tables: [
    {
      name: 'customers',
      row_count: 2,
      columns: [
        {
          name: 'id',
          data_type: 'bigint',
          nullable: false,
          default: null,
          is_primary_key: true,
          references_table: null,
          references_column: null,
        },
        {
          name: 'email',
          data_type: 'text',
          nullable: true,
          default: null,
          is_primary_key: false,
          references_table: null,
          references_column: null,
        },
      ],
      indexes: [{ name: 'customers_pkey', definition: 'CREATE UNIQUE INDEX ...' }],
    },
    {
      name: 'orders',
      row_count: 7,
      columns: [
        {
          name: 'customer_id',
          data_type: 'bigint',
          nullable: false,
          default: null,
          is_primary_key: false,
          references_table: 'customers',
          references_column: 'id',
        },
      ],
      indexes: [],
    },
  ],
}

describe('SchemaExplorer', () => {
  beforeEach(() => {
    apiFetch.mockReset()
    apiFetch.mockResolvedValue({
      columns: ['id'],
      rows: [[1]],
      total: 1,
      limit: 25,
      offset: 0,
    })
  })

  it('lists every table with its row count', () => {
    render(<SchemaExplorer projectId={1} schema={SCHEMA} />)

    expect(screen.getByRole('button', { name: 'customers, 2 rows' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'orders, 7 rows' })).toBeInTheDocument()
  })

  it('shows the first table on open', () => {
    render(<SchemaExplorer projectId={1} schema={SCHEMA} />)

    expect(screen.getByRole('heading', { name: 'customers' })).toBeInTheDocument()
  })

  it('marks the primary key', () => {
    render(<SchemaExplorer projectId={1} schema={SCHEMA} />)

    expect(screen.getByText('PK')).toBeInTheDocument()
  })

  it('shows a foreign key with its target', async () => {
    render(<SchemaExplorer projectId={1} schema={SCHEMA} />)

    await userEvent.click(screen.getByRole('button', { name: 'orders, 7 rows' }))

    expect(screen.getByText(/FK → customers\.id/)).toBeInTheDocument()
  })

  it('searches across column names, not only table names', async () => {
    render(<SchemaExplorer projectId={1} schema={SCHEMA} />)

    await userEvent.type(screen.getByLabelText(/search/i), 'email')

    expect(screen.getByRole('button', { name: 'customers, 2 rows' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'orders, 7 rows' })).not.toBeInTheDocument()
  })

  it('says so when a search matches nothing', async () => {
    render(<SchemaExplorer projectId={1} schema={SCHEMA} />)

    await userEvent.type(screen.getByLabelText(/search/i), 'zzz')

    expect(screen.getByText(/nothing matches/i)).toBeInTheDocument()
  })

  it('loads a preview for the selected table', async () => {
    render(<SchemaExplorer projectId={1} schema={SCHEMA} />)

    expect(apiFetch).toHaveBeenCalledWith(
      expect.stringContaining('/projects/1/tables/customers/preview'),
    )
  })
})
