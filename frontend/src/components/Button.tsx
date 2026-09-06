import type { ButtonHTMLAttributes, ReactNode } from 'react'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'ghost'
  children: ReactNode
}

/** PRD 10.5: full pills. 10.8: canvas-coloured text on the lime fill. */
export function Button({
  variant = 'primary',
  className = '',
  children,
  ...rest
}: ButtonProps) {
  const base =
    'rounded-full px-6 py-3 text-body font-medium transition-all duration-150 ' +
    'disabled:cursor-not-allowed disabled:opacity-50'
  const look =
    variant === 'primary'
      ? 'bg-accent text-canvas hover:-translate-y-0.5'
      : 'border border-border text-text-secondary hover:border-border-hover hover:text-text-primary'

  return (
    <button className={`${base} ${look} ${className}`} {...rest}>
      {children}
    </button>
  )
}
