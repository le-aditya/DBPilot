import { useMemo, useState } from 'react'

import type { ExplanationClause } from '../../lib/types'

interface ExplanationPanelProps {
  sql: string
  summary: string
  clauses: ExplanationClause[]
  /** Optimisation notes have no spans to point at, only advice. */
  variant?: 'explain' | 'optimize'
}

interface Segment {
  text: string
  index: number | null
}

/**
 * Split `sql` into spans, marking which explanation each belongs to.
 *
 * Done once here rather than per hover: highlighting is a class change on
 * already-rendered spans, so moving down the list does not re-slice the string
 * on every mouse move.
 */
export function segmentSql(sql: string, clauses: ExplanationClause[]): Segment[] {
  const usable = clauses
    .map((clause, index) => ({ ...clause, index }))
    .filter((clause) => clause.end > clause.start && clause.end <= sql.length)
    .sort((a, b) => a.start - b.start)

  const segments: Segment[] = []
  let cursor = 0
  for (const clause of usable) {
    // Overlapping spans would render text twice; the earlier one wins.
    if (clause.start < cursor) continue
    if (clause.start > cursor) {
      segments.push({ text: sql.slice(cursor, clause.start), index: null })
    }
    segments.push({ text: sql.slice(clause.start, clause.end), index: clause.index })
    cursor = clause.end
  }
  if (cursor < sql.length) {
    segments.push({ text: sql.slice(cursor), index: null })
  }
  return segments
}

/** PRD F6: hovering an explanation highlights the clause it describes. */
export function ExplanationPanel({
  sql,
  summary,
  clauses,
  variant = 'explain',
}: ExplanationPanelProps) {
  const [active, setActive] = useState<number | null>(null)
  const segments = useMemo(
    () => (variant === 'explain' ? segmentSql(sql, clauses) : []),
    [sql, clauses, variant],
  )

  return (
    <section className="mt-8 rounded-2xl border border-border bg-surface p-6">
      <h4 className="text-eyebrow uppercase text-text-secondary">
        {variant === 'explain' ? 'What this query does' : 'Performance'}
      </h4>
      {summary ? (
        <p className="mt-3 text-body text-text-primary">{summary}</p>
      ) : null}

      {variant === 'explain' && segments.length > 0 ? (
        <pre className="mt-6 overflow-x-auto rounded-2xl border border-border p-4 font-mono text-small">
          {segments.map((segment, index) => (
            <span
              key={index}
              data-highlighted={segment.index !== null && segment.index === active}
              className={
                segment.index !== null && segment.index === active
                  ? 'rounded bg-glow-violet/40 text-text-primary'
                  : 'text-text-secondary'
              }
            >
              {segment.text}
            </span>
          ))}
        </pre>
      ) : null}

      {clauses.length > 0 ? (
        <ul className="mt-6 border-t border-border">
          {clauses.map((clause, index) => (
            <li
              key={`${clause.clause}-${index}`}
              onMouseEnter={() => setActive(index)}
              onMouseLeave={() => setActive(null)}
              onFocus={() => setActive(index)}
              onBlur={() => setActive(null)}
              tabIndex={0}
              aria-label={clause.clause}
              className={
                'cursor-default border-b border-border py-4 transition-colors ' +
                'focus:outline-2 focus:outline-offset-2 focus:outline-accent ' +
                (index === active ? 'bg-canvas' : '')
              }
            >
              <p className="font-mono text-small text-text-primary">{clause.clause}</p>
              <p className="mt-1 text-small text-text-secondary">{clause.text}</p>
            </li>
          ))}
        </ul>
      ) : variant === 'optimize' ? (
        <p className="mt-4 text-small text-text-secondary">
          Nothing to change — this query is already efficient.
        </p>
      ) : null}
    </section>
  )
}
