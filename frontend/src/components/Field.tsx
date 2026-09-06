import type { InputHTMLAttributes } from 'react'

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  id: string
  label: string
  error?: string
}

/** A labelled input. The label is always rendered, never a placeholder. */
export function Field({ id, label, error, className = '', ...rest }: FieldProps) {
  const errorId = `${id}-error`

  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="text-small text-text-secondary">
        {label}
      </label>
      <input
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        className={
          'rounded-2xl border border-border bg-surface px-4 py-3 text-body ' +
          'text-text-primary transition-colors duration-150 ' +
          'placeholder:text-text-tertiary hover:border-border-hover ' +
          'focus:border-border-hover focus:outline-2 focus:outline-offset-2 ' +
          `focus:outline-accent ${className}`
        }
        {...rest}
      />
      {/* Error text uses primary, not lime: PRD 10.8 bars the accent on small copy. */}
      {error ? (
        <p id={errorId} role="alert" className="text-small text-text-primary">
          {error}
        </p>
      ) : null}
    </div>
  )
}
