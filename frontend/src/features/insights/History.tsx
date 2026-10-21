import { useCallback, useEffect, useState } from 'react'

import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { Skeleton } from '../../components/Skeleton'
import { apiFetch } from '../../lib/api'
import { formatDuration, formatWhen } from '../../lib/format'
import type { HistoryResponse, QueryStatus } from '../../lib/types'
import { StatusDot } from './StatusDot'

interface HistoryProps {
  projectId: number
  onReuse?: (sql: string) => void
}

const PAGE = 25
const FILTERS: (QueryStatus | 'all')[] = ['all', 'success', 'error', 'blocked']

/** PRD 10.9: a dense list with 1px dividers and no cards. */
export function History({ projectId, onReuse }: HistoryProps) {
  const [data, setData] = useState<HistoryResponse | null>(null)
  const [offset, setOffset] = useState(0)
  const [filter, setFilter] = useState<QueryStatus | 'all'>('all')
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setError('')
    const params = new URLSearchParams({ limit: String(PAGE), offset: String(offset) })
    if (filter !== 'all') params.set('status_filter', filter)
    try {
      setData(await apiFetch<HistoryResponse>(`/projects/${projectId}/history?${params}`))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not load history.')
    }
  }, [projectId, offset, filter])

  useEffect(() => {
    void load()
  }, [load])

  if (error) {
    return (
      <p role="alert" className="text-small text-text-primary">
        {error}
      </p>
    )
  }
  if (!data) {
    return (
      <div className="space-y-3">
        <div className="flex gap-2">
          {[0, 1, 2, 3].map((index) => (
            <Skeleton key={index} className="h-9 w-20 rounded-full" />
          ))}
        </div>
        {[0, 1, 2, 3].map((index) => (
          <Skeleton key={index} className="h-16 w-full" />
        ))}
      </div>
    )
  }

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {FILTERS.map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => {
              setFilter(option)
              setOffset(0)
            }}
            aria-current={filter === option}
            className={
              'rounded-full border px-4 py-2 text-small capitalize transition-colors ' +
              (filter === option
                ? 'border-border-hover text-text-primary'
                : 'border-border text-text-secondary hover:border-border-hover')
            }
          >
            {option}
          </button>
        ))}
      </div>

      {data.queries.length === 0 ? (
        <div className="mt-10">
          <EmptyState
            icon="history"
            title={filter === 'all' ? 'No queries yet' : `No ${filter} queries yet`}
          >
            {filter === 'all'
              ? 'Ask your first question in the Query tab. Every attempt lands here, blocked ones included.'
              : 'Nothing has been recorded with that status. Try another filter.'}
          </EmptyState>
        </div>
      ) : (
        <ul className="mt-8 border-t border-border">
          {data.queries.map((one) => (
            <li
              key={one.id}
              className="border-b border-border px-2 py-4 transition-colors duration-150 hover:bg-surface/60"
            >
              <div className="flex flex-wrap items-baseline gap-3">
                <StatusDot status={one.status} />
                <p className="min-w-0 flex-1 text-body text-text-primary">
                  {one.question_text || one.executed_sql || '—'}
                </p>
                <span className="text-small text-text-secondary">
                  {one.row_count === null ? '' : `${one.row_count} rows · `}
                  {formatDuration(one.duration_ms)} · {formatWhen(one.created_at)}
                </span>
              </div>
              {one.question_text && one.executed_sql ? (
                <p className="mt-2 pl-4 font-mono text-small text-text-secondary">
                  {one.executed_sql}
                </p>
              ) : null}
              {one.error_message ? (
                <p className="mt-2 pl-4 text-small text-text-secondary">
                  {one.error_message}
                </p>
              ) : null}
              <div className="mt-2 flex items-center gap-3 pl-4">
                {one.was_edited ? (
                  <span className="text-small text-text-tertiary">edited</span>
                ) : null}
                {onReuse && one.executed_sql ? (
                  <button
                    type="button"
                    onClick={() => onReuse(one.executed_sql as string)}
                    className="text-small text-text-secondary underline hover:text-text-primary"
                  >
                    Reuse
                  </button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-6 flex flex-wrap items-center gap-4">
        <p className="text-small text-text-secondary">
          {data.total === 0
            ? 'Nothing yet'
            : `${offset + 1}–${offset + data.queries.length} of ${data.total}`}
        </p>
        <Button variant="ghost" onClick={() => setOffset(Math.max(0, offset - PAGE))} disabled={offset === 0}>
          Previous
        </Button>
        <Button
          variant="ghost"
          onClick={() => setOffset(offset + PAGE)}
          disabled={offset + data.queries.length >= data.total}
        >
          Next
        </Button>
      </div>
    </div>
  )
}
