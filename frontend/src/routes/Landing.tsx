import { Link } from 'react-router-dom'

import { buttonClass } from '../components/button-class'
import { Eyebrow } from '../components/Eyebrow'
import { Glyph, type GlyphName } from '../components/Glyph'
import { SplitHeadline } from '../components/SplitHeadline'
import { useAuth } from '../features/auth/AuthContext'

const FEATURES: { icon: GlyphName; title: string; body: string }[] = [
  {
    icon: 'spark',
    title: 'Ask in English',
    body: 'Type the question you would ask a colleague. DBPilot returns SQL you can read, edit and run yourself.',
  },
  {
    icon: 'layers',
    title: 'See the shape first',
    body: 'Every CSV becomes a real PostgreSQL schema, with a diagram, keys and column types you can inspect before trusting it.',
  },
  {
    icon: 'history',
    title: 'Keep the receipts',
    body: 'Every attempt is recorded, blocked ones included. Saved queries keep each revision, so you can see what changed.',
  },
]

const PROOF = [
  { value: 'Read-only', label: 'by construction, not by promise' },
  { value: '25 MB', label: 'per CSV, up to 25 files at once' },
  { value: '100%', label: 'of attempts logged, blocked or not' },
]

export function Landing() {
  const { status } = useAuth()
  const signedIn = status === 'authenticated'

  return (
    <div className="overflow-x-hidden">
      <header className="relative">
        <div
          aria-hidden="true"
          className="canvas-grid absolute inset-x-0 top-0 h-[520px]"
        />
        <nav className="relative mx-auto flex max-w-[1200px] items-center justify-between px-6 py-8">
          <Link to="/" className="flex items-center gap-2 text-body font-medium">
            <span className="size-2 rounded-full bg-accent shadow-accent" />
            DBPilot
          </Link>
          <div className="flex items-center gap-2">
            {signedIn ? (
              <Link to="/projects" className={buttonClass()}>
                Open projects
              </Link>
            ) : (
              <>
                <Link to="/login" className={buttonClass('ghost')}>
                  Sign in
                </Link>
                <Link
                  to="/register"
                  className={buttonClass('primary', 'hidden sm:inline-flex')}
                >
                  Start free
                </Link>
              </>
            )}
          </div>
        </nav>

        <section className="relative mx-auto grid max-w-[1200px] gap-16 px-6 pb-24 pt-16 lg:grid-cols-[1.05fr_1fr] lg:items-center lg:pt-24">
          <div className="rise-in">
            <Eyebrow>AI SQL workspace</Eyebrow>
            <div className="mt-8">
              <SplitHeadline
                lead="Ask your database a question."
                trail="It answers in SQL you can actually read."
                className="max-w-[16ch]"
              />
            </div>
            <p className="mt-8 max-w-[48ch] text-body text-text-secondary">
              Drop in a CSV and DBPilot builds a real PostgreSQL database from
              it. Then ask questions in plain English, inspect the generated
              SQL, and run it read-only.
            </p>
            <div className="mt-10 flex flex-wrap items-center gap-4">
              <Link
                to={signedIn ? '/projects' : '/register'}
                className={buttonClass()}
              >
                {signedIn ? 'Open your projects' : 'Start free'}
              </Link>
              <Link
                to={signedIn ? '/projects' : '/login'}
                className={buttonClass('ghost')}
              >
                {signedIn ? 'Pick up where you left off' : 'I have an account'}
              </Link>
            </div>
            <p className="mt-6 text-small text-text-secondary">
              No credit card. No writes. Your data never leaves your database.
            </p>
          </div>

          <ProductPreview />
        </section>
      </header>

      <section
        aria-label="How DBPilot works"
        className="border-y border-border bg-surface/30"
      >
        <div className="mx-auto grid max-w-[1200px] gap-8 px-6 py-10 sm:grid-cols-3">
          {PROOF.map((item) => (
            <div key={item.value} className="flex items-baseline gap-3">
              <span className="text-h3 text-text-primary">{item.value}</span>
              <span className="text-small text-text-secondary">{item.label}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-[1200px] px-6 py-28">
        <Eyebrow>What you get</Eyebrow>
        <div className="mt-10 grid gap-4 md:grid-cols-3">
          {FEATURES.map((feature) => (
            <article
              key={feature.title}
              className="group relative overflow-hidden rounded-2xl border border-border bg-surface p-8 shadow-sm transition-[transform,border-color,box-shadow] duration-300 ease-[var(--ease-out)] hover:-translate-y-1 hover:border-border-hover hover:shadow-lg"
            >
              <span className="grid size-11 place-items-center rounded-xl border border-border bg-canvas text-accent shadow-inset">
                <Glyph name={feature.icon} className="size-5" />
              </span>
              <h3 className="mt-6 text-h3 text-text-primary">{feature.title}</h3>
              <p className="mt-3 text-body text-text-secondary">{feature.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-[1200px] px-6 pb-28">
        <div className="relative overflow-hidden rounded-2xl border border-border bg-surface p-10 md:p-16">
          <div
            aria-hidden="true"
            className="absolute inset-y-0 right-0 w-1/2 bg-[image:var(--gradient-veil)]"
          />
          <div className="relative max-w-[52ch]">
            <Eyebrow>Safety, not theatre</Eyebrow>
            <h2 className="mt-6 text-h2 text-text-primary">
              Four layers between a question and your data.
            </h2>
            <p className="mt-4 text-body text-text-secondary">
              A parser gate refuses anything that is not a single SELECT. Queries
              run under a per-project role that only holds SELECT, inside a
              read-only transaction that is always rolled back. Nothing is
              written, ever.
            </p>
            <div className="mt-8">
              <Link
                to={signedIn ? '/projects' : '/register'}
                className={buttonClass()}
              >
                {signedIn ? 'Go to your workspace' : 'Try it on your data'}
              </Link>
            </div>
          </div>
        </div>
      </section>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-[1200px] flex-wrap items-center justify-between gap-4 px-6 py-8">
          <p className="flex items-center gap-2 text-small text-text-secondary">
            <span className="size-1.5 rounded-full bg-accent" />
            DBPilot
          </p>
          <p className="text-small text-text-tertiary">
            PostgreSQL · FastAPI · React
          </p>
        </div>
      </footer>
    </div>
  )
}

/**
 * A drawn screenshot, not an image file.
 *
 * It stays sharp at every density, follows the tokens, and cannot drift out of
 * date the way a checked-in PNG does — the SQL and the table are the same
 * strings the workspace renders.
 */
function ProductPreview() {
  return (
    <div className="rise-in [animation-delay:120ms]">
      <div className="relative">
        <div
          aria-hidden="true"
          className="absolute -inset-6 rounded-[2rem] bg-[image:var(--gradient-veil)] blur-2xl"
        />
        <figure className="relative overflow-hidden rounded-2xl border border-border bg-canvas shadow-lg">
          <div className="flex items-center gap-2 border-b border-border px-4 py-3">
            <span className="size-2 rounded-full bg-border-hover" />
            <span className="size-2 rounded-full bg-border-hover" />
            <span className="size-2 rounded-full bg-border-hover" />
            <span className="ml-3 font-mono text-small text-text-tertiary">
              sales · query
            </span>
          </div>

          <div className="grid grid-cols-[86px_1fr] gap-0" aria-hidden="true">
            <div className="border-r border-border p-3">
              <p className="text-[10px] uppercase tracking-[0.12em] text-text-tertiary">
                Tables
              </p>
              {['orders', 'people', 'products'].map((table, index) => (
                <p
                  key={table}
                  className={
                    'mt-2 truncate rounded px-1.5 py-1 font-mono text-[11px] ' +
                    (index === 0
                      ? 'bg-surface text-text-primary'
                      : 'text-text-secondary')
                  }
                >
                  {table}
                </p>
              ))}
            </div>

            <div className="p-4">
              <div className="flex items-center gap-2 rounded-xl border border-border bg-surface px-3 py-2">
                <Glyph name="search" className="size-3.5 text-text-tertiary" />
                <span className="truncate text-[11px] text-text-secondary">
                  Which customers spent the most last month?
                </span>
              </div>

              <div className="mt-3 rounded-xl bg-glow-violet/15 p-px">
                <pre className="m-0 overflow-hidden rounded-xl border border-border bg-surface px-3 py-2.5 font-mono text-[10.5px] leading-5 text-text-secondary">
                  <span className="text-accent">SELECT</span> p.name,
                  sum(o.total){'\n'}
                  <span className="text-accent">FROM</span> orders o{'\n'}
                  <span className="text-accent">JOIN</span> people p{' '}
                  <span className="text-accent">ON</span> p.id = o.person_id
                  {'\n'}
                  <span className="text-accent">GROUP BY</span> p.name{' '}
                  <span className="text-accent">LIMIT</span> 1000;
                </pre>
              </div>

              <div className="mt-3">
                {[
                  ['Ada Lovelace', '12,480.00'],
                  ['Grace Hopper', '9,315.50'],
                  ['Alan Turing', '7,002.25'],
                ].map(([name, total], index) => (
                  <div
                    key={name}
                    className={
                      'flex items-center justify-between border-b border-border py-1.5 font-mono text-[10.5px] ' +
                      (index === 0 ? 'text-text-primary' : 'text-text-secondary')
                    }
                  >
                    <span>{name}</span>
                    <span>{total}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </figure>
      </div>
      <p className="mt-4 text-center text-small text-text-tertiary">
        The SQL is on screen before it runs. Nothing is hidden.
      </p>
    </div>
  )
}
