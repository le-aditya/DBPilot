/**
 * The pill, as a class string.
 *
 * Exported separately from the component because a navigation action is an
 * `<a>`: wrapping a `<button>` in a `<Link>` nests two interactive elements,
 * which is invalid and makes the focus order ambiguous. The two uses must look
 * identical, so they share this. Keeping it in its own module also leaves
 * Button.tsx exporting components only, so fast refresh keeps working.
 */
export function buttonClass(
  variant: 'primary' | 'ghost' = 'primary',
  className = '',
): string {
  const base =
    'group relative inline-flex items-center justify-center gap-2 rounded-full ' +
    'px-6 py-3 text-body font-medium ' +
    'transition-[transform,box-shadow,background-color,border-color,color] ' +
    'duration-200 ease-[var(--ease-out)] ' +
    'focus-visible:outline-2 focus-visible:outline-offset-2 ' +
    'focus-visible:outline-accent ' +
    'disabled:cursor-not-allowed disabled:opacity-50 disabled:transform-none ' +
    'disabled:shadow-none'
  const look =
    variant === 'primary'
      ? 'bg-accent bg-[image:var(--gradient-accent)] text-canvas ' +
        'shadow-accent hover:-translate-y-0.5 hover:shadow-accent-strong ' +
        'active:translate-y-0 active:shadow-sm'
      : 'border border-border text-text-secondary ' +
        'hover:-translate-y-0.5 hover:border-border-hover hover:bg-surface ' +
        'hover:text-text-primary hover:shadow-sm active:translate-y-0'

  return `${base} ${look} ${className}`
}
