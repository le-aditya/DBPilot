import { Eyebrow } from '../components/Eyebrow'
import { SplitHeadline } from '../components/SplitHeadline'

const SURFACES = [
  { name: '--canvas', className: 'bg-canvas' },
  { name: '--surface', className: 'bg-surface' },
  { name: '--border', className: 'bg-border' },
  { name: '--border-hover', className: 'bg-border-hover' },
  { name: '--accent', className: 'bg-accent' },
  { name: '--glow-violet', className: 'bg-glow-violet' },
]

/**
 * A proof sheet for the PRD section 10 token system. Every later screen draws
 * from these, so a design regression shows up here first.
 */
export function Tokens() {
  return (
    <main className="mx-auto max-w-[1200px] px-6 py-32">
      <Eyebrow>Design system</Eyebrow>

      <div className="mt-8">
        <SplitHeadline
          lead="Ask your database a question."
          trail="It answers in SQL you can actually read."
        />
      </div>

      <section className="mt-32">
        <Eyebrow>Surfaces</Eyebrow>
        <div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {SURFACES.map((surface) => (
            <div key={surface.name}>
              <div
                className={`${surface.className} h-24 rounded-2xl border border-border`}
              />
              <p className="mt-3 font-mono text-small text-text-tertiary">
                {surface.name}
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className="mt-32">
        <Eyebrow>Type scale</Eyebrow>
        <div className="mt-8 space-y-6">
          <p className="text-h2 text-text-primary">Heading two, 40px</p>
          <p className="text-h3 text-text-primary">Heading three, 24px</p>
          <p className="max-w-[60ch] text-body text-text-secondary">
            Body copy at 16px and 1.6 leading. Secondary text is the floor for
            running copy — it passes 5.3:1 against the canvas, so it stays
            readable while the white above it carries the emphasis.
          </p>
          <p className="text-small text-text-tertiary">
            Tertiary, 14px — disabled and decorative only, never running copy.
          </p>
        </div>
      </section>

      <section className="mt-32">
        <Eyebrow>Accent budget</Eyebrow>
        <div className="mt-8 flex flex-wrap items-center gap-4">
          <button
            type="button"
            className="rounded-full bg-accent px-6 py-3 text-body font-medium text-canvas transition-transform duration-150 hover:-translate-y-0.5"
          >
            Try DBPilot
          </button>
          <span className="flex items-center gap-2 rounded-full border border-border px-4 py-2 text-small text-text-secondary">
            <span className="inline-block size-1.5 rounded-full bg-accent" />
            Read-only
          </span>
        </div>
        <p className="mt-6 max-w-[60ch] text-small text-text-tertiary">
          Two accent uses on this screen: the call to action and one status dot.
          The budget is three per viewport.
        </p>
      </section>
    </main>
  )
}
