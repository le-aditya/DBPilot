import { useCallback, useEffect, useState } from 'react'

import { Button } from '../../components/Button'
import { apiFetch } from '../../lib/api'
import type { TablePreviewData } from '../../lib/types'

interface TablePreviewProps {
  projectId: number
  table: string
}

/**
 * PRD F3: first 100 rows, paginated and sortable.
 *
 * The caller keys this on the table name, so selecting a different table
 * remounts it and the page and sort reset by construction rather than by an
 * effect that has to notice the change after the fact.
 */
export function TablePreview({ projectId, table }: TablePreviewProps) {
  const [data, setData] = useState<TablePreviewData | null>(null)
  const [offset, setOffset] = useState(0)
  const [sort, setSort] = useState<string | null>(null)
  const [direction, setDirection] = useState<'asc' | 'desc'>('asc')
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setError('')
    const params = new URLSearchParams({ offset: String(offset), limit: '25' })
    if (sort) {
      params.set('sort', sort)
      params.set('direction', direction)
    }
    try {
      setData(
        await apiFetch<TablePreviewData>(
          `/projects/${projectId}/tables/${table}/preview?${params}`,
        ),
      )
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not load the rows.')
    }
  }, [projectId, table, offset, sort, direction])

  useEffect(() => {
    void load()
  }, [load])

  function toggleSort(column: string) {
    if (sort === column) {
      setDirection((current) => (current === 'asc' ? 'desc' : 'asc'))
    } else {
      setSort(column)
      setDirection('asc')
    }
    setOffset(0)
  }

  if (error) {
    return (
      <p role="alert" className="mt-6 text-small text-text-primary">
        {error}
      </p>
    )
  }
  if (!data) return null

  const showing = data.rows.length
  const to = offset + showing

  return (
    <div className="mt-10">
      <h4 className="text-small uppercase tracking-[0.12em] text-text-secondary">
        Data
      </h4>

      <div className="mt-4 overflow-x-auto">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="border-b border-border">
              {data.columns.map((column) => (
                <th key={column} className="py-3 pr-6 font-normal">
                  <button
                    type="button"
                    onClick={() => toggleSort(column)}
                    aria-label={`Sort by ${column}`}
                    className="text-eyebrow uppercase text-text-secondary hover:text-text-primary"
                  >
                    {column}
                    {sort === column ? (direction === 'asc' ? ' ↑' : ' ↓') : ''}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row, index) => (
              <tr key={index} className="border-b border-border">
                {row.map((cell, at) => (
                  <td
                    key={at}
                    className="py-3 pr-6 font-mono text-small text-text-primary"
                  >
                    {cell === null ? (
                      <span className="text-text-tertiary">null</span>
                    ) : (
                      String(cell)
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-4">
        <p className="text-small text-text-secondary">
          {showing === 0 ? 'No rows' : `${offset + 1}–${to} of ${data.total}`}
        </p>
        <Button
          variant="ghost"
          onClick={() => setOffset(Math.max(0, offset - data.limit))}
          disabled={offset === 0}
        >
          Previous
        </Button>
        <Button
          variant="ghost"
          onClick={() => setOffset(offset + data.limit)}
          disabled={to >= data.total}
        >
          Next
        </Button>
      </div>
    </div>
  )
}
