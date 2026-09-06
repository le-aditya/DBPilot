import { useCallback, useEffect, useState, type FormEvent } from 'react'

import { Button } from '../components/Button'
import { Eyebrow } from '../components/Eyebrow'
import { Field } from '../components/Field'
import { SplitHeadline } from '../components/SplitHeadline'
import { useAuth } from '../features/auth/AuthContext'
import { apiFetch } from '../lib/api'

interface Project {
  id: number
  name: string
  source_type: 'upload' | 'connection'
  schema_name: string | null
  table_count: number | null
  is_demo: boolean
  created_at: string
}

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

  return (
    <main className="mx-auto max-w-[1200px] px-6 py-24">
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

      <form
        onSubmit={handleCreate}
        className="mt-16 flex flex-wrap items-end gap-4 rounded-2xl border border-border bg-surface p-6"
      >
        <div className="min-w-[260px] flex-1">
          <Field
            id="project-name"
            label="Project name"
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>
        <Button type="submit" disabled={busy || name.trim().length === 0}>
          {busy ? 'Creating…' : 'Create project'}
        </Button>
      </form>

      {error ? (
        <p role="alert" className="mt-6 text-small text-text-primary">
          {error}
        </p>
      ) : null}

      <section className="mt-16">
        {loaded && projects.length === 0 ? (
          <p className="text-body text-text-secondary">
            No projects yet. Create your first one above.
          </p>
        ) : (
          <ul className="divide-y divide-border border-y border-border">
            {projects.map((project) => (
              <li
                key={project.id}
                className="flex flex-wrap items-center justify-between gap-4 py-5"
              >
                <div>
                  <p className="text-h3 text-text-primary">{project.name}</p>
                  <p className="mt-1 text-small text-text-secondary">
                    {project.source_type === 'upload' ? 'Uploaded data' : 'Connection'}
                    {project.table_count !== null
                      ? ` · ${project.table_count} tables`
                      : ''}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  aria-label={`Delete ${project.name}`}
                  onClick={() => void handleDelete(project)}
                >
                  Delete
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  )
}
