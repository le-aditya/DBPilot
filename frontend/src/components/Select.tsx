import type { SelectHTMLAttributes } from 'react'

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string
  /** Hide the label visually but keep it for screen readers, for dense tables. */
  labelHidden?: boolean
  id: string
}

/** A labelled select, styled to match Field. */
export function Select({
  id,
  label,
  labelHidden = false,
  className = '',
  children,
  ...rest
}: SelectProps) {
  return (
    <div className="flex flex-col gap-2">
      <label
        htmlFor={id}
        className={
          labelHidden ? 'sr-only' : 'text-small text-text-secondary'
        }
      >
        {label}
      </label>
      <select
        id={id}
        className={
          'rounded-2xl border border-border bg-surface px-4 py-2 text-small ' +
          'text-text-primary transition-colors duration-150 ' +
          'hover:border-border-hover focus:border-border-hover ' +
          `focus:outline-2 focus:outline-offset-2 focus:outline-accent ${className}`
        }
        {...rest}
      >
        {children}
      </select>
    </div>
  )
}
