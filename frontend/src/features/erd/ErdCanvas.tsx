import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { Button } from '../../components/Button'
import { apiFetch } from '../../lib/api'
import type { ErdResponse } from '../../lib/types'
import { download, toPngBlob, toSvgBlob } from './export'
import {
  anchor,
  boundsOf,
  fitText,
  HEADER_HEIGHT,
  layoutNodes,
  MAX_VISIBLE_COLUMNS,
  type PlacedNode,
  ROW_HEIGHT,
  ROW_PADDING,
} from './layout'

interface ErdCanvasProps {
  projectId: number
  erd: ErdResponse
}

const SAVE_DEBOUNCE_MS = 600

/**
 * PRD 10.9: a full-bleed canvas that breaks the 1200px max width, with floating
 * controls and the accent reserved for the selected node's border.
 *
 * Drawn as real SVG rather than positioned HTML so the export is a
 * serialisation of exactly what is on screen (design section 8).
 */
export function ErdCanvas({ projectId, erd }: ErdCanvasProps) {
  const initial = useMemo(() => layoutNodes(erd.nodes, erd.edges), [erd])
  const [nodes, setNodes] = useState<PlacedNode[]>(initial)
  const [selected, setSelected] = useState<string | null>(null)
  const [dragging, setDragging] = useState<string | null>(null)
  const [zoom, setZoom] = useState(1)
  const [status, setStatus] = useState('')
  const svgRef = useRef<SVGSVGElement>(null)
  const origin = useRef({ x: 0, y: 0, nodeX: 0, nodeY: 0 })

  useEffect(() => setNodes(initial), [initial])

  const bounds = useMemo(() => boundsOf(nodes), [nodes])
  const byName = useMemo(
    () => new Map(nodes.map((node) => [node.name, node])),
    [nodes],
  )

  const save = useCallback(
    async (placed: PlacedNode[]) => {
      const node_positions = Object.fromEntries(
        placed.map((node) => [node.name, { x: node.x, y: node.y }]),
      )
      try {
        await apiFetch(`/projects/${projectId}/erd/layout`, {
          method: 'PUT',
          body: JSON.stringify({ node_positions }),
        })
      } catch {
        // A failed save is not worth interrupting a drag over; the positions
        // are still correct on screen and the next drag retries.
      }
    },
    [projectId],
  )

  // Debounced: a drag fires dozens of moves, and each one is not a save.
  useEffect(() => {
    if (dragging !== null || nodes === initial) return
    const timer = setTimeout(() => void save(nodes), SAVE_DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [nodes, dragging, initial, save])

  function startDrag(event: React.PointerEvent, node: PlacedNode) {
    event.currentTarget.setPointerCapture(event.pointerId)
    origin.current = {
      x: event.clientX,
      y: event.clientY,
      nodeX: node.x,
      nodeY: node.y,
    }
    setDragging(node.name)
    setSelected(node.name)
  }

  function onDrag(event: React.PointerEvent) {
    if (!dragging) return
    const dx = (event.clientX - origin.current.x) / zoom
    const dy = (event.clientY - origin.current.y) / zoom
    setNodes((current) =>
      current.map((node) =>
        node.name === dragging
          ? { ...node, x: origin.current.nodeX + dx, y: origin.current.nodeY + dy }
          : node,
      ),
    )
  }

  async function exportAs(format: 'svg' | 'png') {
    if (!svgRef.current) return
    setStatus('')
    try {
      const blob =
        format === 'svg'
          ? toSvgBlob(svgRef.current)
          : await toPngBlob(svgRef.current)
      download(blob, `erd.${format}`)
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'The export failed.')
    }
  }

  if (erd.nodes.length === 0) {
    return (
      <p className="text-body text-text-secondary">
        No tables yet. Upload a CSV and the diagram will draw itself.
      </p>
    )
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Button variant="ghost" onClick={() => setZoom((z) => Math.min(2, z + 0.2))}>
          Zoom in
        </Button>
        <Button variant="ghost" onClick={() => setZoom((z) => Math.max(0.4, z - 0.2))}>
          Zoom out
        </Button>
        <Button variant="ghost" onClick={() => setNodes(layoutNodes(erd.nodes, erd.edges))}>
          Re-arrange
        </Button>
        <Button variant="ghost" onClick={() => void exportAs('svg')}>
          Export SVG
        </Button>
        <Button variant="ghost" onClick={() => void exportAs('png')}>
          Export PNG
        </Button>
      </div>

      {status ? (
        <p role="alert" className="mb-4 text-small text-text-primary">
          {status}
        </p>
      ) : null}

      {erd.edges.length === 0 ? (
        <p className="mb-4 text-small text-text-secondary">
          {erd.nodes.length === 1
            ? 'One table, so there are no relationships to draw yet. Upload a second CSV and link them with a foreign key on the review screen, and the lines will appear here.'
            : 'No foreign keys yet. Declare one on the upload review screen and the relationships will appear here.'}
        </p>
      ) : null}

      {/* PRD 9: below 768px the diagram gives way to the table list. */}
      <div className="hidden overflow-auto rounded-2xl border border-border bg-surface p-4 md:flex md:justify-center">
        <svg
          ref={svgRef}
          role="img"
          aria-label="Entity relationship diagram"
          width={bounds.width * zoom}
          height={bounds.height * zoom}
          viewBox={`${bounds.minX} ${bounds.minY} ${bounds.width} ${bounds.height}`}
          onPointerMove={onDrag}
          onPointerUp={() => setDragging(null)}
          className="block touch-none"
        >
          <defs>
            <marker
              id="erd-arrow"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" className="fill-border-hover" />
            </marker>
          </defs>

          {erd.edges.map((edge, index) => {
            const from = byName.get(edge.source)
            const to = byName.get(edge.target)
            if (!from || !to) return null
            const a = anchor(from, to)
            const b = anchor(to, from)
            const midX = (a.x + b.x) / 2
            return (
              <g key={`${edge.source}-${edge.target}-${index}`}>
                <path
                  d={`M ${a.x} ${a.y} C ${midX} ${a.y}, ${midX} ${b.y}, ${b.x} ${b.y}`}
                  fill="none"
                  className="stroke-border-hover"
                  strokeWidth={1.5}
                  markerEnd="url(#erd-arrow)"
                />
                <text
                  x={midX}
                  y={(a.y + b.y) / 2 - 6}
                  textAnchor="middle"
                  className="fill-text-secondary text-[11px]"
                >
                  {edge.cardinality}
                  {edge.via ? ` via ${edge.via}` : ''}
                </text>
              </g>
            )
          })}

          {nodes.map((node) => {
            const visible = node.columns.slice(0, MAX_VISIBLE_COLUMNS)
            const hidden = node.columns.length - visible.length
            return (
              <g
                key={node.name}
                transform={`translate(${node.x} ${node.y})`}
                onPointerDown={(event) => startDrag(event, node)}
                className="cursor-grab"
              >
                <rect
                  width={node.width}
                  height={node.height}
                  rx={12}
                  className={
                    'fill-canvas ' +
                    (selected === node.name ? 'stroke-accent' : 'stroke-border')
                  }
                  strokeWidth={selected === node.name ? 2 : 1}
                />
                <text x={14} y={25} className="fill-text-primary text-[13px] font-medium">
                  {/* Room reserved for the row count on the right. */}
                  {fitText(node.name, node.width - 70)}
                </text>
                <title>{node.name}</title>
                <text
                  x={node.width - 14}
                  y={25}
                  textAnchor="end"
                  className="fill-text-secondary text-[11px]"
                >
                  {node.row_count}
                </text>
                <line
                  x1={0}
                  y1={HEADER_HEIGHT}
                  x2={node.width}
                  y2={HEADER_HEIGHT}
                  className="stroke-border"
                />
                {visible.map((column, index) => (
                  <g key={column.name}>
                    <text
                      x={14}
                      y={HEADER_HEIGHT + ROW_PADDING + (index + 1) * ROW_HEIGHT - 6}
                      className={
                        column.is_primary_key
                          ? 'fill-accent text-[11px]'
                          : 'fill-text-secondary text-[11px]'
                      }
                    >
                      {column.is_primary_key ? '● ' : column.is_foreign_key ? '○ ' : '  '}
                      {fitText(column.name, node.width - 100, 11)}
                    </text>
                    <text
                      x={node.width - 14}
                      y={HEADER_HEIGHT + ROW_PADDING + (index + 1) * ROW_HEIGHT - 6}
                      textAnchor="end"
                      className="fill-text-tertiary text-[10px]"
                    >
                      {column.data_type}
                    </text>
                  </g>
                ))}
                {hidden > 0 ? (
                  <text
                    x={14}
                    y={
                      HEADER_HEIGHT +
                      ROW_PADDING +
                      (visible.length + 1) * ROW_HEIGHT -
                      6
                    }
                    className="fill-text-tertiary text-[11px]"
                  >
                    +{hidden} more
                  </text>
                ) : null}
              </g>
            )
          })}
        </svg>
      </div>

      <ul
        aria-label="Tables"
        className="divide-y divide-border border-y border-border md:hidden"
      >
        {erd.nodes.map((node) => (
          <li key={node.name} className="py-4">
            <p className="text-body text-text-primary">{node.name}</p>
            <p className="mt-1 text-small text-text-secondary">
              {node.columns.length} columns · {node.row_count} rows
            </p>
          </li>
        ))}
      </ul>
    </div>
  )
}
