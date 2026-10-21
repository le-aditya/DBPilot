import { EmptyState } from '../../components/EmptyState'
import { SkeletonRows } from '../../components/Skeleton'
import type { ExecuteResponse } from '../../lib/types'

interface ResultsTableProps {
  execution: ExecuteResponse | null
  /** The query is in flight; show the shape of a table, not a spinner. */
  loading?: boolean
}

/**
 * Results, or the reason there are none.
 *
 * PRD 10.9: errors state the cause and the fix. A blocked query is not a crash
 * and is not the user's fault, so it reads as an explanation with the rule
 * named, not as a failure.
 */
export function ResultsTable({ execution, loading = false }: ResultsTableProps) {
  if (loading) {
    return (
      <div className="mt-8">
        <p className="text-small text-text-secondary">Running read-only…</p>
        <SkeletonRows rows={5} columns={execution?.columns.length ?? 4} />
      </div>
    )
  }

  if (!execution) return null

  if (execution.status === 'blocked') {
    return (
      <div
        role="alert"
        className="relative mt-8 overflow-hidden rounded-2xl border border-border bg-surface p-6 shadow-sm"
      >
        <div
          aria-hidden="true"
          className="absolute inset-x-0 top-0 h-px bg-[image:var(--gradient-hairline)]"
        />
        <p className="text-small uppercase tracking-[0.12em] text-text-secondary">
          Blocked · {execution.rule?.replace(/_/g, ' ')}
        </p>
        <p className="mt-3 text-body text-text-primary">{execution.error}</p>
        <p className="mt-3 text-small text-text-secondary">
          Nothing was executed. The attempt is still in your history.
        </p>
      </div>
    )
  }

  if (execution.status === 'error') {
    return (
      <div
        role="alert"
        className="mt-8 rounded-2xl border border-border bg-surface p-6 shadow-sm"
      >
        <p className="text-small uppercase tracking-[0.12em] text-text-secondary">
          Could not run
        </p>
        <p className="mt-3 font-mono text-small text-text-primary">
          {execution.error}
        </p>
      </div>
    )
  }

  if (execution.row_count === 0) {
    return (
      <div className="mt-8">
        <EmptyState
          compact
          icon="search"
          title="That query ran, and matched no rows"
        >
          The SQL was valid and executed read-only — there is just nothing to
          show. Try a looser filter.
        </EmptyState>
      </div>
    )
  }

  return (
    <div className="mt-8">
      {execution.truncated ? (
        <p className="mb-3 text-small text-text-secondary">
          Showing the first {execution.row_count} rows. Add a LIMIT to export
          more deliberately.
        </p>
      ) : null}
      <div className="overflow-x-auto rounded-2xl border border-border bg-surface/50">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="border-b border-border bg-surface">
              {execution.columns.map((column) => (
                <th
                  key={column}
                  className="px-4 py-3 text-eyebrow font-normal uppercase text-text-secondary"
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {execution.rows.map((row, index) => (
              <tr
                key={index}
                className="border-b border-border transition-colors duration-150 last:border-b-0 hover:bg-accent-soft"
              >
                {row.map((cell, at) => (
                  <td
                    key={at}
                    className="px-4 py-3 font-mono text-small text-text-primary"
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
      <p className="mt-3 text-small text-text-tertiary">
        {execution.row_count} rows · {execution.duration_ms} ms ·{' '}
        {execution.executed_sql ? 'read-only' : ''}
      </p>
    </div>
  )
}
