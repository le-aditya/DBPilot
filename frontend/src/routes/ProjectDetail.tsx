import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { Button } from '../components/Button'
import { Eyebrow } from '../components/Eyebrow'
import { SchemaExplorer } from '../features/schema/SchemaExplorer'
import { UploadPanel } from '../features/upload/UploadPanel'
import { apiFetch } from '../lib/api'
import type { Project, ProjectSchema } from '../lib/types'

export function ProjectDetail() {
  const { projectId } = useParams()
  const id = Number(projectId)
  const [project, setProject] = useState<Project | null>(null)
  const [schema, setSchema] = useState<ProjectSchema | null>(null)
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setError('')
    try {
      const [loadedProject, loadedSchema] = await Promise.all([
        apiFetch<Project>(`/projects/${id}`),
        apiFetch<ProjectSchema>(`/projects/${id}/schema`),
      ])
      setProject(loadedProject)
      setSchema(loadedSchema)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not open that project.')
    }
  }, [id])

  useEffect(() => {
    void load()
  }, [load])

  if (error) {
    return (
      <main className="mx-auto max-w-[1200px] px-6 py-24">
        <p role="alert" className="text-body text-text-primary">
          {error}
        </p>
        <Link to="/projects" className="mt-6 inline-block text-small text-text-secondary underline">
          Back to projects
        </Link>
      </main>
    )
  }

  if (!project || !schema) return null

  const hasData = schema.tables.length > 0

  return (
    <main className="mx-auto max-w-[1200px] px-6 py-24">
      <Link to="/projects" className="text-small text-text-secondary hover:text-text-primary">
        ← Projects
      </Link>

      <div className="mt-6 flex flex-wrap items-start justify-between gap-6">
        <div>
          <Eyebrow>{hasData ? 'Schema' : 'New project'}</Eyebrow>
          <h2 className="mt-6 text-h2 text-text-primary">{project.name}</h2>
          {hasData ? (
            <p className="mt-2 text-small text-text-secondary">
              {schema.tables.length} tables in {schema.schema_name}
            </p>
          ) : null}
        </div>
        {hasData && !adding ? (
          <Button variant="ghost" onClick={() => setAdding(true)}>
            Add more data
          </Button>
        ) : null}
      </div>

      <div className="mt-16">
        {!hasData || adding ? (
          <>
            {!hasData ? (
              // PRD 10.9 — empty states are invitations, not apologies.
              <p className="mb-8 text-body text-text-secondary">
                No data yet. Upload a CSV and DBPilot will build the tables for you.
              </p>
            ) : null}
            <UploadPanel
              projectId={id}
              onCommitted={() => {
                setAdding(false)
                void load()
              }}
            />
            {adding ? (
              <Button variant="ghost" className="mt-6" onClick={() => setAdding(false)}>
                Cancel
              </Button>
            ) : null}
          </>
        ) : (
          <SchemaExplorer projectId={id} schema={schema} />
        )}
      </div>
    </main>
  )
}
