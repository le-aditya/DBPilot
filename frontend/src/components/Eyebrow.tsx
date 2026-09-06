import type { ReactNode } from 'react'

interface EyebrowProps {
  children: ReactNode
}

/** PRD 10.3 — a small lime dot, then wide-tracked uppercase in secondary text. */
export function Eyebrow({ children }: EyebrowProps) {
  return (
    <p className="flex items-center gap-2 text-eyebrow uppercase text-text-secondary">
      <span
        data-accent-dot
        aria-hidden="true"
        className="inline-block size-1.5 rounded-full bg-accent"
      />
      {children}
    </p>
  )
}
