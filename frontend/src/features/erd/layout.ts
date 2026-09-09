import dagre from '@dagrejs/dagre'

import type { ErdEdge, ErdNode } from '../../lib/types'

export const NODE_WIDTH = 220
export const HEADER_HEIGHT = 40
export const ROW_HEIGHT = 22
export const ROW_PADDING = 10
/** Beyond this a node lists a count instead of every column, so a wide table
 *  does not become a column of text taller than the canvas. */
export const MAX_VISIBLE_COLUMNS = 12

export interface PlacedNode extends ErdNode {
  x: number
  y: number
  width: number
  height: number
}

/** Characters that fit in `width` px at `size` px, for this font.
 *
 *  SVG <text> does not wrap or clip, so a long table name silently draws over
 *  whatever is beside it — which is how `online_food_delivery_dataset` ended up
 *  on top of its own row count. Truncating up front is the fix.
 */
export function fitText(text: string, width: number, size = 13): string {
  const perChar = size * 0.58  // measured for the Inter stack at these sizes
  const max = Math.floor(width / perChar)
  if (text.length <= max) return text
  return `${text.slice(0, Math.max(1, max - 1))}…`
}


export function nodeHeight(node: ErdNode): number {
  const rows = Math.min(node.columns.length, MAX_VISIBLE_COLUMNS)
  const overflow = node.columns.length > MAX_VISIBLE_COLUMNS ? 1 : 0
  return HEADER_HEIGHT + (rows + overflow) * ROW_HEIGHT + ROW_PADDING * 2
}

/**
 * Place nodes left to right with dagre, keeping any position the user saved.
 *
 * A saved position always wins: the whole point of dragging a node is that it
 * stays where you put it, and re-running the automatic layout over the top of
 * a deliberate arrangement would be the most annoying possible behaviour.
 */
export function layoutNodes(
  nodes: ErdNode[],
  edges: ErdEdge[],
): PlacedNode[] {
  const graph = new dagre.graphlib.Graph()
  graph.setGraph({ rankdir: 'LR', nodesep: 60, ranksep: 120, marginx: 40, marginy: 40 })
  graph.setDefaultEdgeLabel(() => ({}))

  for (const node of nodes) {
    graph.setNode(node.name, { width: NODE_WIDTH, height: nodeHeight(node) })
  }
  for (const edge of edges) {
    // A junction edge joins two parents that dagre should still rank apart.
    if (graph.hasNode(edge.source) && graph.hasNode(edge.target)) {
      graph.setEdge(edge.source, edge.target)
    }
  }
  dagre.layout(graph)

  return nodes.map((node) => {
    const placed = graph.node(node.name)
    const height = nodeHeight(node)
    const saved = node.x !== null && node.y !== null
    return {
      ...node,
      // dagre reports centres; everything downstream draws from a corner.
      x: saved ? (node.x as number) : placed.x - NODE_WIDTH / 2,
      y: saved ? (node.y as number) : placed.y - height / 2,
      width: NODE_WIDTH,
      height,
    }
  })
}

export interface Bounds {
  minX: number
  minY: number
  width: number
  height: number
}

export function boundsOf(nodes: PlacedNode[], padding = 40): Bounds {
  if (nodes.length === 0) {
    return { minX: 0, minY: 0, width: 800, height: 600 }
  }
  const minX = Math.min(...nodes.map((n) => n.x)) - padding
  const minY = Math.min(...nodes.map((n) => n.y)) - padding
  const maxX = Math.max(...nodes.map((n) => n.x + n.width)) + padding
  const maxY = Math.max(...nodes.map((n) => n.y + n.height)) + padding
  return { minX, minY, width: maxX - minX, height: maxY - minY }
}

/** Where an edge should meet a node: the side nearest the other end. */
export function anchor(
  from: PlacedNode,
  to: PlacedNode,
): { x: number; y: number } {
  const y = from.y + HEADER_HEIGHT / 2
  return from.x + from.width / 2 < to.x + to.width / 2
    ? { x: from.x + from.width, y }
    : { x: from.x, y }
}
