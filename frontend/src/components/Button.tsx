import type { ButtonHTMLAttributes, ReactNode } from 'react'

import { buttonClass } from './button-class'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'ghost'
  /** Shows a spinner and blocks the click, without changing the label width. */
  loading?: boolean
  children: ReactNode
}

/** PRD 10.5: full pills. 10.8: canvas-coloured text on the lime fill. */
export function Button({
  variant = 'primary',
  loading = false,
  className = '',
  children,
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      className={buttonClass(variant, className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? (
        <span
          aria-hidden="true"
          className={
            'size-3.5 animate-spin rounded-full border-2 border-current ' +
            'border-t-transparent opacity-70'
          }
        />
      ) : null}
      {children}
    </button>
  )
}
