import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ErdResponse } from '../../../lib/types'
import { ErdCanvas } from '../ErdCanvas'

const apiFetch = vi.fn()

vi.mock('../../../lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}))

const ERD: ErdResponse = {
  nodes: [
    {
      name: 'customers',
      row_count: 2,
      is_junction: false,
      x: null,
      y: null,
      columns: [
        {
          name: 'id',
          data_type: 'bigint',
          nullable: false,
          is_primary_key: true,
          is_foreign_key: false,
        },
      ],
    },
    {
      name: 'orders',
      row_count: 7,
      is_junction: false,
      x: null,
      y: null,
      columns: [
        {
          name: 'customer_id',
          data_type: 'bigint',
          nullable: false,
          is_primary_key: false,
          is_foreign_key: true,
        },
      ],
    },
  ],
  edges: [
    {
      source: 'orders',
      target: 'customers',
      source_column: 'customer_id',
      target_column: 'id',
      cardinality: '1:N',
      via: null,
    },
  ],
}

describe('ErdCanvas', () => {
  beforeEach(() => {
    apiFetch.mockReset()
    apiFetch.mockResolvedValue({ node_positions: {} })
  })

  it('draws a node for each table', () => {
    // jsdom applies no media queries, so the mobile fallback list renders too;
    // scope to the canvas rather than asserting on a name that legitimately
    // appears in both.
    render(<ErdCanvas projectId={1} erd={ERD} />)
    const canvas = screen.getByRole('img', { name: /entity relationship/i })

    // Each node also carries a <title> with the untruncated name, so match the
    // drawn <text> specifically rather than any element holding the string.
    const drawn = [...canvas.querySelectorAll('text')].map((one) => one.textContent)
    expect(drawn).toContain('customers')
    expect(drawn).toContain('orders')
  })

  it('labels the edge with its cardinality', () => {
    render(<ErdCanvas projectId={1} erd={ERD} />)

    expect(screen.getByText('1:N')).toBeInTheDocument()
  })

  it('names the junction table on a many-to-many edge', () => {
    render(
      <ErdCanvas
        projectId={1}
        erd={{
          ...ERD,
          edges: [{ ...ERD.edges[0], cardinality: 'N:M', via: 'customer_tags' }],
        }}
      />,
    )

    expect(screen.getByText(/N:M via customer_tags/)).toBeInTheDocument()
  })

  it('renders the diagram as real SVG, which is what makes export a serialisation', () => {
    render(<ErdCanvas projectId={1} erd={ERD} />)

    expect(screen.getByRole('img', { name: /entity relationship/i }).tagName).toBe('svg')
  })

  it('offers a scrollable list instead of a canvas on small screens', () => {
    // PRD 9: below 768px the diagram degrades rather than becoming unusable.
    render(<ErdCanvas projectId={1} erd={ERD} />)

    const list = screen.getByRole('list', { name: 'Tables' })
    expect(list.className).toContain('md:hidden')
    expect(within(list).getByText('customers')).toBeInTheDocument()
  })

  it('invites a first upload when there is nothing to draw', () => {
    render(<ErdCanvas projectId={1} erd={{ nodes: [], edges: [] }} />)

    expect(screen.getByText(/no tables yet/i)).toBeInTheDocument()
  })

  it('re-arranges without crashing', async () => {
    render(<ErdCanvas projectId={1} erd={ERD} />)

    await userEvent.click(screen.getByRole('button', { name: /re-arrange/i }))

    const canvas = screen.getByRole('img', { name: /entity relationship/i })
    const drawn = [...canvas.querySelectorAll('text')].map((one) => one.textContent)
    expect(drawn).toContain('customers')
  })

  it('truncates a long table name so it cannot draw over the row count', () => {
    // The bug in the wild: `online_food_delivery_dataset` overlapped its count.
    const long = 'online_food_delivery_dataset'
    render(
      <ErdCanvas
        projectId={1}
        erd={{ nodes: [{ ...ERD.nodes[0], name: long }], edges: [] }}
      />,
    )
    const canvas = screen.getByRole('img', { name: /entity relationship/i })

    const drawn = [...canvas.querySelectorAll('text')].map((one) => one.textContent)
    expect(drawn).not.toContain(long)
    expect(drawn.some((one) => one?.endsWith('…'))).toBe(true)
    // The full name is still reachable, as the SVG tooltip.
    expect(canvas.querySelector('title')?.textContent).toBe(long)
  })

  it('explains why a single-table diagram has no lines', () => {
    render(
      <ErdCanvas projectId={1} erd={{ nodes: [ERD.nodes[0]], edges: [] }} />,
    )

    expect(screen.getByText(/no relationships to draw yet/i)).toBeInTheDocument()
  })

  it('offers both export formats', () => {
    render(<ErdCanvas projectId={1} erd={ERD} />)

    expect(screen.getByRole('button', { name: /export svg/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /export png/i })).toBeInTheDocument()
  })
})
