import type { QueryStatus } from '../../lib/types'

/** PRD 10.9: a status dot per row. Lime only for success, so it stays scarce. */
export function StatusDot({ status }: { status: QueryStatus }) {
  const tone =
    status === 'success'
      ? 'bg-accent'
      : status === 'blocked'
        ? 'bg-text-secondary'
        : 'bg-text-tertiary'

  return (
    <span
      role="img"
      aria-label={status}
      title={status}
      className={`inline-block size-1.5 shrink-0 rounded-full ${tone}`}
    />
  )
}
