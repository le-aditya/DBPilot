import { useEffect, useMemo, useState } from 'react'

const CHAR_MS = 16

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

function linesFor(question: string): string[] {
  const asked = question.trim().replace(/\s+/g, ' ').slice(0, 46)
  return [
    '-- reading the schema',
    asked ? `-- matching "${asked}"` : '-- matching the question',
    '-- drafting SELECT',
  ]
}

/**
 * The waiting room for the model.
 *
 * A real generate takes 8–22 seconds. An indeterminate spinner for that long
 * reads as a hang, so this types the three things the server is actually doing
 * as SQL comments. It is deliberately commentary, never fabricated SQL: the
 * text that eventually appears in the editor is the model's, and only the
 * model's.
 */
export function TypingSql({ question }: { question: string }) {
  const lines = useMemo(() => linesFor(question), [question])
  const [progress, setProgress] = useState({ line: 0, char: 0 })

  useEffect(() => {
    setProgress({ line: 0, char: 0 })
    if (prefersReducedMotion()) {
      setProgress({ line: lines.length, char: 0 })
      return
    }

    let line = 0
    let char = 0
    let timer = 0

    const tick = () => {
      char += 1
      if (char > lines[line].length) {
        line += 1
        char = 0
        if (line >= lines.length) {
          setProgress({ line: lines.length, char: 0 })
          return
        }
      }
      setProgress({ line, char })
      // A beat at the start of each new line, so it reads as three steps.
      timer = window.setTimeout(tick, char === 0 ? 220 : CHAR_MS)
    }

    timer = window.setTimeout(tick, 140)
    return () => window.clearTimeout(timer)
  }, [lines])

  return (
    <div
      role="status"
      className="mt-8 overflow-hidden rounded-2xl border border-border bg-surface shadow-sm shadow-inset"
    >
      <div className="flex items-center justify-between gap-4 border-b border-border px-4 py-2">
        <span className="text-eyebrow uppercase text-text-secondary">
          Drafting SQL
        </span>
        <span className="flex items-center gap-1.5" aria-hidden="true">
          <span className="size-1.5 animate-pulse rounded-full bg-accent" />
          <span className="size-1.5 animate-pulse rounded-full bg-accent [animation-delay:150ms]" />
          <span className="size-1.5 animate-pulse rounded-full bg-accent [animation-delay:300ms]" />
        </span>
      </div>
      <pre
        aria-hidden="true"
        className="m-0 overflow-hidden px-4 py-4 font-mono text-small leading-6 text-text-secondary"
      >
        {lines.map((text, index) => {
          if (index > progress.line) return null
          const shown =
            index < progress.line ? text : text.slice(0, progress.char)
          return (
            <div key={text} className="whitespace-pre">
              <span className={index === progress.line ? 'text-text-primary' : ''}>
                {shown}
              </span>
              {index === progress.line ? (
                <span
                  className="ml-px inline-block h-4 w-[7px] translate-y-0.5 bg-accent"
                  style={{ animation: 'caret-blink 1s steps(1) infinite' }}
                />
              ) : null}
            </div>
          )
        })}
      </pre>
      <p className="border-t border-border px-4 py-2 text-small text-text-secondary">
        Reading your schema and writing a read-only query. This can take up to
        20 seconds.
      </p>
    </div>
  )
}
