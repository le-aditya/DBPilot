import type { ReactNode } from 'react'

import { Glyph, type GlyphName } from './Glyph'

interface EmptyStateProps {
  /** The glyph that names the absence: a table, a history sign, a spark. */
  icon?: GlyphName
  title: string
  children?: ReactNode
  action?: ReactNode
  /** Tighten it for a panel inside a screen that already has a heading. */
  compact?: boolean
  className?: string
}

/**
 * PRD 10.9: an empty state is an invitation, not an apology.
 *
 * A dashed frame and a lit glyph say "this space is ready" instead of leaving a
 * sentence floating in the middle of a page. The copy names the next action.
 */
export function EmptyState({
  icon = 'layers',
  title,
  children,
  action,
  compact = false,
  className = '',
}: EmptyStateProps) {
  return (
    <div
      className={
        'relative overflow-hidden rounded-2xl border border-dashed border-border ' +
        'bg-surface/40 text-center ' +
        (compact ? 'px-6 py-10' : 'px-8 py-16 ') +
        className
      }
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-32 bg-[image:var(--gradient-veil)]"
      />
      <div className="relative mx-auto flex max-w-[46ch] flex-col items-center">
        <span className="grid size-14 place-items-center rounded-2xl border border-border bg-canvas text-accent shadow-sm shadow-inset">
          <Glyph name={icon} className="size-6" />
        </span>
        <h3 className="mt-6 text-h3 text-text-primary">{title}</h3>
        {children ? (
          <div className="mt-3 text-body text-text-secondary">{children}</div>
        ) : null}
        {action ? <div className="mt-7">{action}</div> : null}
      </div>
    </div>
  )
}
