import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { Button } from '../components/Button'
import { Eyebrow } from '../components/Eyebrow'
import { ErdPanel } from '../features/erd/ErdPanel'
import { Dashboard } from '../features/insights/Dashboard'
import { History } from '../features/insights/History'
import { QueryWorkspace } from '../features/query/QueryWorkspace'
import { SavedQueries } from '../features/query/SavedQueries'
import { SchemaExplorer } from '../features/schema/SchemaExplorer'
import { UploadPanel } from '../features/upload/UploadPanel'
import { apiFetch } from '../lib/api'
import type { Project, ProjectSchema } from '../lib/types'

type View = 'query' | 'diagram' | 'data' | 'saved' | 'dashboard' | 'history'

const VIEWS: View[] = ['query', 'diagram', 'data', 'saved', 'dashboard', 'history']

const LABELS: Record<View, string> = {
  query: 'Query',
  diagram: 'Diagram',
  // "Data" rather than "Schema": the diagram already shows the columns, so what
  // is uniquely here is the rows (PRD F3's preview, search and index list).
  data: 'Data',
  saved: 'Saved',
  dashboard: 'Dashboard',
  history: 'History',
}

export function ProjectDetail() {
  const { projectId } = useParams()
  const id = Number(projectId)
  const [project, setProject] = useState<Project | null>(null)
  const [schema, setSchema] = useState<ProjectSchema | null>(null)
  const [adding, setAdding] = useState(false)
  const [view, setView] = useState<View>('query')
  // Lifted out of QueryWorkspace so History can load a query into it, and so it
  // survives switching tabs.
  const [sql, setSql] = useState('')
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
          <Eyebrow>{hasData ? 'Workspace' : 'New project'}</Eyebrow>
          <h2 className="mt-6 text-h2 text-text-primary">{project.name}</h2>
          {hasData ? (
            <p className="mt-2 text-small text-text-secondary">
              {schema.tables.length} tables ·{' '}
              {schema.tables.reduce((sum, table) => sum + table.row_count, 0).toLocaleString()}{' '}
              rows · schema{' '}
              <span className="font-mono">{schema.schema_name}</span>
            </p>
          ) : null}
        </div>
        {hasData && !adding ? (
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="ghost" onClick={() => setAdding(true)}>
              Add data
            </Button>
          </div>
        ) : null}
      </div>

      {hasData && !adding ? (
        <nav
          aria-label="Workspace views"
          className="sticky top-0 z-10 -mx-6 mt-10 border-b border-border bg-canvas/85 px-6 backdrop-blur"
        >
          <div className="flex flex-wrap items-center gap-1 py-2">
            {VIEWS.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setView(option)}
                aria-current={view === option}
                className={
                  'relative rounded-full px-4 py-2 text-small ' +
                  'transition-[background-color,color,box-shadow] duration-200 ' +
                  'ease-[var(--ease-out)] focus-visible:outline-2 ' +
                  'focus-visible:outline-offset-2 focus-visible:outline-accent ' +
                  (view === option
                    ? 'bg-surface text-text-primary shadow-sm shadow-inset'
                    : 'text-text-secondary hover:bg-surface/60 hover:text-text-primary')
                }
              >
                {LABELS[option]}
                <span
                  aria-hidden="true"
                  className={
                    'absolute inset-x-4 -bottom-0.5 h-px transition-opacity duration-200 ' +
                    (view === option ? 'bg-accent opacity-100' : 'opacity-0')
                  }
                />
              </button>
            ))}
          </div>
        </nav>
      ) : null}

      <div className="mt-12">
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
          <>
            {/* Kept mounted, not unmounted, so a half-written question and its
                results are still there when you come back from another tab. */}
            <div hidden={view !== 'query'}>
              <QueryWorkspace
                projectId={id}
                schema={schema}
                sql={sql}
                onSqlChange={setSql}
              />
            </div>
            {view === 'diagram' ? (
              <div className="view-enter">
                <ErdPanel projectId={id} />
              </div>
            ) : null}
            {view === 'data' ? (
              <div className="view-enter">
                <SchemaExplorer projectId={id} schema={schema} />
              </div>
            ) : null}
            {view === 'saved' ? (
              <div className="view-enter">
                <SavedQueries
                  sql={sql}
                  onLoad={(loaded) => {
                    setSql(loaded)
                    setView('query')
                  }}
                />
              </div>
            ) : null}
            {view === 'dashboard' ? (
              <div className="view-enter">
                <Dashboard projectId={id} />
              </div>
            ) : null}
            {view === 'history' ? (
              <div className="view-enter">
                <History
                  projectId={id}
                  onReuse={(reused) => {
                    setSql(reused)
                    setView('query')
                  }}
                />
              </div>
            ) : null}
          </>
        )}
      </div>
    </main>
  )
}
