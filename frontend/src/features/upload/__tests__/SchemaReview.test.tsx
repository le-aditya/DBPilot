import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { TableSpec } from '../../../lib/types'
import { SchemaReview } from '../SchemaReview'

const PEOPLE: TableSpec = {
  name: 'people',
  source_filename: 'people.csv',
  sampled_rows: 3,
  columns: [
    {
      name: 'id',
      source_name: 'Id',
      type: 'integer',
      nullable: false,
      samples: ['1', '2'],
    },
    {
      name: 'nickname',
      source_name: 'Nickname',
      type: 'text',
      nullable: true,
      samples: ['ada'],
    },
  ],
  primary_key: null,
  foreign_keys: [],
}

function renderReview(tables: TableSpec[] = [PEOPLE]) {
  const onChange = vi.fn()
  const onCommit = vi.fn()
  render(
    <SchemaReview
      tables={tables}
      busy={false}
      onChange={onChange}
      onCommit={onCommit}
      onCancel={vi.fn()}
    />,
  )
  return { onChange, onCommit }
}

describe('SchemaReview', () => {
  it('shows the inferred type for each column', () => {
    renderReview()

    expect(screen.getByLabelText('Type for id')).toHaveValue('integer')
    expect(screen.getByLabelText('Type for nickname')).toHaveValue('text')
  })

  it('reports a corrected type to its parent', async () => {
    const { onChange } = renderReview()

    await userEvent.selectOptions(screen.getByLabelText('Type for id'), 'text')

    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({
        columns: [
          expect.objectContaining({ name: 'id', type: 'text' }),
          expect.objectContaining({ name: 'nickname', type: 'text' }),
        ],
      }),
    ])
  })

  it('offers a generated key and does not offer a nullable column as one', () => {
    renderReview()

    const options = Array.from(
      screen.getByLabelText('Primary key').querySelectorAll('option'),
    ).map((option) => option.textContent)

    expect(options).toEqual(['Add an id column for me', 'id'])
  })

  it('reports a nominated primary key', async () => {
    const { onChange } = renderReview()

    await userEvent.selectOptions(screen.getByLabelText('Primary key'), 'id')

    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ primary_key: 'id' }),
    ])
  })

  it('offers no foreign keys when there is only one table', () => {
    renderReview()

    expect(screen.queryByText('References')).not.toBeInTheDocument()
  })

  it('reports a declared foreign key against another uploaded table', async () => {
    const orders: TableSpec = {
      ...PEOPLE,
      name: 'orders',
      source_filename: 'orders.csv',
      columns: [
        {
          name: 'person_id',
          source_name: 'Person Id',
          type: 'integer',
          nullable: false,
          samples: ['1'],
        },
      ],
    }
    const { onChange } = renderReview([orders, PEOPLE])

    await userEvent.selectOptions(
      screen.getByLabelText('Foreign key for person_id'),
      'people.id',
    )

    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({
        foreign_keys: [
          {
            column: 'person_id',
            references_table: 'people',
            references_column: 'id',
          },
        ],
      }),
      PEOPLE,
    ])
  })

  it('commits when asked', async () => {
    const { onCommit } = renderReview()

    await userEvent.click(screen.getByRole('button', { name: /create tables/i }))

    expect(onCommit).toHaveBeenCalled()
  })
})
