import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { Button } from '../components/Button'
import { EmptyState } from '../components/EmptyState'
import { Eyebrow } from '../components/Eyebrow'
import { Field } from '../components/Field'
import { Glyph } from '../components/Glyph'
import { Skeleton } from '../components/Skeleton'
import { SplitHeadline } from '../components/SplitHeadline'
import { useAuth } from '../features/auth/AuthContext'
import { apiFetch } from '../lib/api'
import { formatWhen } from '../lib/format'

interface Project {
  id: number
  name: string
  source_type: 'upload' | 'connection'
  schema_name: string | null
  table_count: number | null
  is_demo: boolean
  created_at: string
}

const STEPS = [
  { step: '01', title: 'Create a project', body: 'One project per dataset, so queries and history stay separate.' },
  { step: '02', title: 'Drop in CSVs', body: 'Types are inferred, then you approve the columns before anything is built.' },
  { step: '03', title: 'Ask questions', body: 'Plain English in, readable SQL out — and every attempt is logged.' },
]

export function Projects() {
  const { user, signOut } = useAuth()
  const [projects, setProjects] = useState<Project[]>([])
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)

  const load = useCallback(async () => {
    try {
      setProjects(await apiFetch<Project[]>('/projects'))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not load projects.')
    } finally {
      setLoaded(true)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function handleCreate(event: FormEvent) {
    event.preventDefault()
    setError('')
    setBusy(true)
    try {
      const created = await apiFetch<Project>('/projects', {
        method: 'POST',
        body: JSON.stringify({ name, source_type: 'upload' }),
      })
      setProjects((current) => [...current, created])
      setName('')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not create it.')
    } finally {
      setBusy(false)
    }
  }

  async function handleDelete(project: Project) {
    setError('')
    try {
      await apiFetch<null>(`/projects/${project.id}`, { method: 'DELETE' })
      setProjects((current) => current.filter((one) => one.id !== project.id))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not delete it.')
    }
  }

  const tableTotal = projects.reduce(
    (sum, project) => sum + (project.table_count ?? 0),
    0,
  )

  return (
    <main className="mx-auto max-w-[1200px] px-6 pb-28 pt-16">
      <div className="flex flex-wrap items-start justify-between gap-6">
        <div>
          <Eyebrow>Projects</Eyebrow>
          <div className="mt-6">
            <SplitHeadline
              as="h2"
              lead="Your databases."
              trail="Pick one, or start another."
            />
          </div>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-small text-text-secondary">{user?.email}</span>
          <Button variant="ghost" onClick={signOut}>
            Sign out
          </Button>
        </div>
      </div>

      <div className="mt-12 grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <form
          onSubmit={handleCreate}
          className="relative overflow-hidden rounded-2xl border border-border bg-surface p-6 shadow-sm"
        >
          <div
            aria-hidden="true"
            className="absolute inset-x-0 top-0 h-px bg-[image:var(--gradient-hairline)]"
          />
          <div className="flex flex-wrap items-end gap-4">
            <div className="min-w-[240px] flex-1">
              <Field
                id="project-name"
                label="Project name"
                required
                placeholder="Q4 sales"
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </div>
            <Button
              type="submit"
              loading={busy}
              disabled={name.trim().length === 0}
            >
              {busy ? 'Creating…' : 'Create project'}
            </Button>
          </div>
          <p className="mt-4 text-small text-text-secondary">
            A project is an empty schema until you upload a CSV. Nothing is
            created in your database until you approve the columns.
          </p>
        </form>

        <div className="grid grid-cols-2 gap-4">
          <Stat
            label="Projects"
            value={loaded ? String(projects.length) : null}
            icon="database"
          />
          <Stat label="Tables" value={loaded ? String(tableTotal) : null} icon="table" />
        </div>
      </div>

      {error ? (
        <p role="alert" className="mt-6 text-small text-text-primary">
          {error}
        </p>
      ) : null}

      <section className="mt-14">
        <div className="flex items-baseline justify-between gap-4">
          <h3 className="text-small uppercase tracking-[0.12em] text-text-secondary">
            All projects
          </h3>
          {loaded && projects.length > 0 ? (
            <span className="text-small text-text-tertiary">
              {projects.length} {projects.length === 1 ? 'project' : 'projects'}
            </span>
          ) : null}
        </div>

        {!loaded ? (
          <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {[0, 1, 2].map((index) => (
              <div
                key={index}
                className="rounded-2xl border border-border bg-surface p-6"
              >
                <Skeleton className="h-5 w-32" />
                <Skeleton className="mt-4 h-4 w-44" />
                <Skeleton className="mt-8 h-4 w-24" />
              </div>
            ))}
          </div>
        ) : projects.length === 0 ? (
          <div className="mt-6">
            <EmptyState
              icon="database"
              title="No projects yet"
              action={
                <span className="text-small text-text-secondary">
                  Name one above, then upload a CSV.
                </span>
              }
            >
              A project holds one dataset: its tables, its query history and its
              diagrams. Your first one takes about a minute.
            </EmptyState>
          </div>
        ) : (
          <ul className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {projects.map((project, index) => (
              <li
                key={project.id}
                className="group flex h-full flex-col justify-between rounded-2xl border border-border bg-surface p-6 shadow-sm transition-[transform,border-color,box-shadow] duration-300 ease-[var(--ease-out)] hover:-translate-y-1 hover:border-border-hover hover:shadow-lg"
              >
                <div>
                  <div className="flex items-start justify-between gap-3">
                    <span className="font-mono text-small text-text-tertiary">
                      {String(index + 1).padStart(2, '0')}
                    </span>
                    <span className="rounded-full border border-border px-2 py-0.5 text-eyebrow uppercase text-text-secondary">
                      {project.source_type === 'upload' ? 'Uploaded' : 'Connected'}
                    </span>
                  </div>
                  <h4 className="mt-6 text-h3 text-text-primary">
                    <Link
                      to={`/projects/${project.id}`}
                      className="transition-colors hover:text-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                    >
                      {project.name}
                    </Link>
                  </h4>
                  <p className="mt-2 text-small text-text-secondary">
                    {project.table_count === null
                      ? 'Waiting for its first upload'
                      : `${project.table_count} ${project.table_count === 1 ? 'table' : 'tables'}`}
                    {' · '}
                    {formatWhen(project.created_at)}
                  </p>
                </div>
                <div className="mt-8 flex items-center justify-between gap-3">
                  <Link
                    to={`/projects/${project.id}`}
                    className="text-small text-text-secondary transition-colors group-hover:text-text-primary"
                  >
                    Open workspace →
                  </Link>
                  <Button
                    variant="ghost"
                    aria-label={`Delete ${project.name}`}
                    onClick={() => void handleDelete(project)}
                    className="px-3 py-1 text-small opacity-0 transition-opacity duration-200 focus-visible:opacity-100 group-hover:opacity-100"
                  >
                    Delete
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mt-20 border-t border-border pt-10">
        <Eyebrow>How it works</Eyebrow>
        <div className="mt-6 grid gap-8 md:grid-cols-3">
          {STEPS.map((item) => (
            <div key={item.step}>
              <p className="font-mono text-small text-text-tertiary">{item.step}</p>
              <h4 className="mt-2 text-body text-text-primary">{item.title}</h4>
              <p className="mt-1 max-w-[36ch] text-small text-text-secondary">
                {item.body}
              </p>
            </div>
          ))}
        </div>
      </section>
    </main>
  )
}

function Stat({
  label,
  value,
  icon,
}: {
  label: string
  value: string | null
  icon: 'database' | 'table'
}) {
  return (
    <div className="rounded-2xl border border-border bg-surface p-6 shadow-sm shadow-inset">
      <div className="flex items-center justify-between">
        <p className="text-eyebrow uppercase text-text-secondary">{label}</p>
        <Glyph name={icon} className="size-4 text-text-tertiary" />
      </div>
      {value === null ? (
        <Skeleton className="mt-4 h-8 w-12" />
      ) : (
        <p className="mt-3 text-h2 text-text-primary">{value}</p>
      )}
    </div>
  )
}
