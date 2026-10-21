import type { CSSProperties } from 'react'

interface SkeletonProps {
  className?: string
  style?: CSSProperties
}

/** One loading plate. The sweep lives in tokens.css so motion can be disabled. */
export function Skeleton({ className = '', style }: SkeletonProps) {
  return (
    <div
      aria-hidden="true"
      className={`skeleton rounded-lg ${className}`}
      style={style}
    />
  )
}

interface SkeletonRowsProps {
  rows?: number
  columns?: number
  /** Column widths cycle through this set so the placeholder reads as data. */
  widths?: string[]
}

/** Placeholder rows shaped like the table that is about to replace them. */
export function SkeletonRows({
  rows = 6,
  columns = 4,
  widths = ['28%', '22%', '18%', '14%'],
}: SkeletonRowsProps) {
  return (
    <div className="mt-8" role="status">
      <div aria-hidden="true" className="flex gap-6 border-b border-border pb-3">
        {Array.from({ length: columns }, (_, column) => (
          <Skeleton key={column} className="h-3 w-20" />
        ))}
      </div>
      {Array.from({ length: rows }, (_, row) => (
        <div
          key={row}
          aria-hidden="true"
          className="flex gap-6 border-b border-border py-4"
          style={{ opacity: 1 - row * 0.1 }}
        >
          {/* Fixed widths, not random: an unrelated re-render must not reshape
              the placeholder the user is currently looking at. */}
          {Array.from({ length: columns }, (_, column) => (
            <Skeleton
              key={column}
              className="h-4"
              style={{ width: widths[column % widths.length] }}
            />
          ))}
        </div>
      ))}
      <span className="sr-only">Loading results…</span>
    </div>
  )
}
