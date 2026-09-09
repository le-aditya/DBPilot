import type { ReactNode } from 'react'

interface BadgeProps {
  tone?: 'accent' | 'muted'
  children: ReactNode
}

/**
 * A small outline pill.
 *
 * PRD 10.9 makes the lime outline PK badge the schema explorer's single accent,
 * which is why nothing else on that screen takes the accent — no lime button,
 * no eyebrow dot in the detail pane. Foreign keys use the muted tone so the
 * primary key stays the thing your eye finds first.
 */
export function Badge({ tone = 'muted', children }: BadgeProps) {
  const look =
    tone === 'accent'
      ? 'border-accent text-accent'
      : 'border-border-hover text-text-secondary'

  return (
    <span
      className={`inline-block rounded-full border px-2 py-0.5 text-eyebrow uppercase ${look}`}
    >
      {children}
    </span>
  )
}
