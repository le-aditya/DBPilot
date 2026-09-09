import { describe, expect, it } from 'vitest'

import type { ErdEdge, ErdNode } from '../../../lib/types'
import { boundsOf, layoutNodes, MAX_VISIBLE_COLUMNS, nodeHeight } from '../layout'

function node(name: string, columns = 2, x: number | null = null): ErdNode {
  return {
    name,
    row_count: 3,
    is_junction: false,
    x,
    y: x === null ? null : 0,
    columns: Array.from({ length: columns }, (_, index) => ({
      name: `c${index}`,
      data_type: 'text',
      nullable: true,
      is_primary_key: index === 0,
      is_foreign_key: false,
    })),
  }
}

const EDGE: ErdEdge = {
  source: 'orders',
  target: 'customers',
  source_column: 'customer_id',
  target_column: 'id',
  cardinality: '1:N',
  via: null,
}

describe('layout', () => {
  it('places every node somewhere', () => {
    const placed = layoutNodes([node('customers'), node('orders')], [EDGE])

    expect(placed).toHaveLength(2)
    for (const one of placed) {
      expect(Number.isFinite(one.x)).toBe(true)
      expect(Number.isFinite(one.y)).toBe(true)
    }
  })

  it('separates connected nodes rather than stacking them', () => {
    const placed = layoutNodes([node('customers'), node('orders')], [EDGE])

    expect(placed[0].x).not.toBe(placed[1].x)
  })

  it('keeps a position the user saved', () => {
    // Dragging a node must survive a reload, or dragging is pointless.
    const placed = layoutNodes([node('customers', 2, 512), node('orders')], [EDGE])

    expect(placed[0].x).toBe(512)
  })

  it('grows a node with its column count', () => {
    expect(nodeHeight(node('wide', 8))).toBeGreaterThan(nodeHeight(node('narrow', 2)))
  })

  it('caps the height of a very wide table', () => {
    const capped = nodeHeight(node('huge', MAX_VISIBLE_COLUMNS + 50))
    const atLimit = nodeHeight(node('big', MAX_VISIBLE_COLUMNS + 1))

    expect(capped).toBe(atLimit)
  })

  it('bounds every node with padding', () => {
    const placed = layoutNodes([node('a'), node('b')], [])
    const bounds = boundsOf(placed)

    for (const one of placed) {
      expect(one.x).toBeGreaterThan(bounds.minX)
      expect(one.x + one.width).toBeLessThan(bounds.minX + bounds.width)
    }
  })

  it('gives an empty diagram a usable canvas rather than a zero-sized one', () => {
    const bounds = boundsOf([])

    expect(bounds.width).toBeGreaterThan(0)
    expect(bounds.height).toBeGreaterThan(0)
  })

  it('ignores an edge naming a table that is not on the diagram', () => {
    expect(() =>
      layoutNodes([node('customers')], [{ ...EDGE, source: 'ghost' }]),
    ).not.toThrow()
  })
})
