import { useRef, useState, type ChangeEvent } from 'react'

import { apiUpload } from '../../lib/api'
import type { TableSpec, UploadAnalysis, UploadResult } from '../../lib/types'
import { SchemaReview } from './SchemaReview'

interface UploadPanelProps {
  projectId: number
  onCommitted: (result: UploadResult) => void
}

/**
 * PRD F2.1 in two steps: analyse, then commit what the user approved.
 *
 * The chosen files are held here because the commit re-sends them. The server
 * deliberately keeps nothing between the two calls — see app/api/uploads.py.
 */
export function UploadPanel({ projectId, onCommitted }: UploadPanelProps) {
  const [files, setFiles] = useState<File[]>([])
  const [tables, setTables] = useState<TableSpec[] | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  function formDataOf(chosen: File[]): FormData {
    const body = new FormData()
    for (const file of chosen) body.append('files', file)
    return body
  }

  async function analyse(chosen: File[]) {
    setError('')
    setBusy(true)
    try {
      const analysis = await apiUpload<UploadAnalysis>(
        `/projects/${projectId}/upload`,
        formDataOf(chosen),
      )
      setFiles(chosen)
      setTables(
        analysis.tables.map((table) => ({
          ...table,
          primary_key: null,
          foreign_keys: [],
        })),
      )
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'That file could not be read.')
    } finally {
      setBusy(false)
    }
  }

  async function commit() {
    if (!tables) return
    setError('')
    setBusy(true)
    try {
      const body = formDataOf(files)
      body.append('spec', JSON.stringify({ tables }))
      const result = await apiUpload<UploadResult>(
        `/projects/${projectId}/upload/commit`,
        body,
      )
      reset()
      onCommitted(result)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Those tables could not be created.')
    } finally {
      setBusy(false)
    }
  }

  function reset() {
    setTables(null)
    setFiles([])
    if (input.current) input.current.value = ''
  }

  function choose(event: ChangeEvent<HTMLInputElement>) {
    const chosen = Array.from(event.target.files ?? [])
    if (chosen.length > 0) void analyse(chosen)
  }

  return (
    <section>
      {tables === null ? (
        <div className="rounded-2xl border border-border bg-surface p-8">
          <h3 className="text-h3 text-text-primary">Add a CSV</h3>
          <p className="mt-2 max-w-[52ch] text-body text-text-secondary">
            Up to 25 MB per file. DBPilot reads the first rows to work out the
            column types, then shows you what it found before creating anything.
          </p>
          <label htmlFor="csv-files" className="sr-only">
            CSV files
          </label>
          <input
            ref={input}
            id="csv-files"
            type="file"
            accept=".csv,text/csv"
            multiple
            onChange={choose}
            disabled={busy}
            className={
              'mt-6 block w-full text-small text-text-secondary ' +
              'file:mr-4 file:rounded-full file:border-0 file:bg-accent ' +
              'file:px-6 file:py-3 file:text-body file:font-medium ' +
              'file:text-canvas hover:file:cursor-pointer'
            }
          />
          {busy ? (
            <p className="mt-4 text-small text-text-secondary">Reading the file…</p>
          ) : null}
        </div>
      ) : (
        <SchemaReview
          tables={tables}
          busy={busy}
          onChange={setTables}
          onCommit={() => void commit()}
          onCancel={reset}
        />
      )}

      {error ? (
        <p role="alert" className="mt-6 text-small text-text-primary">
          {error}
        </p>
      ) : null}
    </section>
  )
}
