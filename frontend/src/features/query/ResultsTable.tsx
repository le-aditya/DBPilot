import type { ExecuteResponse } from '../../lib/types'

interface ResultsTableProps {
  execution: ExecuteResponse
}

/**
 * Results, or the reason there are none.
 *
 * PRD 10.9: errors state the cause and the fix. A blocked query is not a crash
 * and is not the user's fault, so it reads as an explanation with the rule
 * named, not as a failure.
 */
export function ResultsTable({ execution }: ResultsTableProps) {
  if (execution.status === 'blocked') {
    return (
      <div
        role="alert"
        className="mt-8 rounded-2xl border border-border bg-surface p-6"
      >
        <p className="text-small uppercase tracking-[0.12em] text-text-secondary">
          Blocked · {execution.rule?.replace(/_/g, ' ')}
        </p>
        <p className="mt-3 text-body text-text-primary">{execution.error}</p>
      </div>
    )
  }

  if (execution.status === 'error') {
    return (
      <div
        role="alert"
        className="mt-8 rounded-2xl border border-border bg-surface p-6"
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
      <p className="mt-8 text-body text-text-secondary">
        That query ran, and matched no rows.
      </p>
    )
  }

  return (
    <div className="mt-8">
      {execution.truncated ? (
        <p className="mb-3 text-small text-text-secondary">
          Showing the first {execution.row_count} rows.
        </p>
      ) : null}
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="border-b border-border">
              {execution.columns.map((column) => (
                <th
                  key={column}
                  className="py-3 pr-6 text-eyebrow font-normal uppercase text-text-secondary"
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {execution.rows.map((row, index) => (
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
    </div>
  )
}
