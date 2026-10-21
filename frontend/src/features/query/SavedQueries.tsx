import { useCallback, useEffect, useMemo, useState } from 'react'

import { Badge } from '../../components/Badge'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { Select } from '../../components/Select'
import { Skeleton } from '../../components/Skeleton'
import { apiFetch } from '../../lib/api'
import { diffLines, diffSummary } from '../../lib/diff'
import { formatWhen } from '../../lib/format'
import type { SavedQuery, SavedQueryVersion } from '../../lib/types'

interface SavedQueriesProps {
  /** The SQL currently in the editor, offered as a new revision. */
  sql: string
  onLoad: (sql: string) => void
}

/**
 * Saved queries and what changed between their revisions.
 *
 * A saved query used to be a single mutable string: saving over it destroyed
 * the old SQL, so "what did this look like before I added the date filter?"
 * had no answer. Every edit now appends a revision, and this screen puts any
 * two of them side by side.
 */
export function SavedQueries({ sql, onLoad }: SavedQueriesProps) {
  const [queries, setQueries] = useState<SavedQuery[] | null>(null)
  const [open, setOpen] = useState<number | null>(null)
  const [versions, setVersions] = useState<SavedQueryVersion[] | null>(null)
  const [from, setFrom] = useState<number | null>(null)
  const [to, setTo] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState<number | null>(null)

  const load = useCallback(async () => {
    try {
      setQueries(await apiFetch<SavedQuery[]>('/saved-queries'))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not load saved queries.')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function reveal(query: SavedQuery) {
    setError('')
    setNotice('')
    if (open === query.id) {
      setOpen(null)
      return
    }
    setOpen(query.id)
    setVersions(null)
    try {
      const history = await apiFetch<SavedQueryVersion[]>(
        `/saved-queries/${query.id}/versions`,
      )
      setVersions(history)
      // Newest pair by default: the change most likely to be under discussion.
      setTo(history[0]?.revision ?? null)
      setFrom(history[1]?.revision ?? history[0]?.revision ?? null)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not load its history.')
    }
  }

  async function saveRevision(query: SavedQuery) {
    setError('')
    setNotice('')
    setBusy(query.id)
    try {
      const updated = await apiFetch<SavedQuery>(`/saved-queries/${query.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ sql_template: sql }),
      })
      setQueries((current) =>
        current?.map((one) => (one.id === query.id ? updated : one)) ?? null,
      )
      const history = await apiFetch<SavedQueryVersion[]>(
        `/saved-queries/${query.id}/versions`,
      )
      setOpen(query.id)
      setVersions(history)
      setTo(history[0]?.revision ?? null)
      setFrom(history[1]?.revision ?? history[0]?.revision ?? null)
      setNotice(`Saved revision ${history[0]?.revision ?? 1} of “${query.name}”.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'That revision could not be saved.')
    } finally {
      setBusy(null)
    }
  }

  return (
    <section>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h3 className="text-h3 text-text-primary">Saved queries</h3>
          <p className="mt-2 max-w-[56ch] text-body text-text-secondary">
            Every edit is kept as a revision. Compare any two to see exactly what
            changed.
          </p>
        </div>
        {queries && queries.length > 0 ? (
          <span className="text-small text-text-tertiary">
            {queries.length} saved
          </span>
        ) : null}
      </div>

      {error ? (
        <p role="alert" className="mt-6 text-small text-text-primary">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p role="status" className="mt-6 text-small text-text-secondary">
          {notice}
        </p>
      ) : null}

      {queries === null ? (
        <div className="mt-8 space-y-3">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : queries.length === 0 ? (
        <div className="mt-8">
          <EmptyState
            icon="layers"
            title="Nothing saved yet"
            action={
              <span className="text-small text-text-secondary">
                Write SQL in the Query tab, then choose Save.
              </span>
            }
          >
            A saved query keeps its parameters and its full revision history, so
            you can come back to a working query months later.
          </EmptyState>
        </div>
      ) : (
        <ul className="mt-8 border-t border-border">
          {queries.map((query) => {
            const expanded = open === query.id
            return (
              <li key={query.id} className="border-b border-border">
                <div className="flex flex-wrap items-center justify-between gap-4 py-4">
                  <div className="min-w-0">
                    <p className="text-body text-text-primary">{query.name}</p>
                    <p className="mt-1 text-small text-text-secondary">
                      saved {formatWhen(query.created_at)}
                      {query.parameters.length > 0
                        ? ` · ${query.parameters.length} parameter${
                            query.parameters.length === 1 ? '' : 's'
                          }`
                        : ''}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      variant="ghost"
                      className="px-3 py-1.5 text-small"
                      onClick={() => onLoad(query.sql_template)}
                    >
                      Load
                    </Button>
                    <Button
                      variant="ghost"
                      className="px-3 py-1.5 text-small"
                      onClick={() => void saveRevision(query)}
                      disabled={busy !== null || !sql.trim() || sql === query.sql_template}
                      loading={busy === query.id}
                      title={
                        sql === query.sql_template
                          ? 'The editor already matches this query'
                          : 'Save the SQL in the editor as a new revision'
                      }
                    >
                      Save revision
                    </Button>
                    <Button
                      variant="ghost"
                      className="px-3 py-1.5 text-small"
                      aria-expanded={expanded}
                      onClick={() => void reveal(query)}
                    >
                      {expanded ? 'Hide history' : 'History'}
                    </Button>
                  </div>
                </div>

                {expanded ? (
                  <div className="mb-6 rounded-2xl border border-border bg-surface p-5 shadow-sm view-enter">
                    {versions === null ? (
                      <div className="space-y-2">
                        <Skeleton className="h-4 w-40" />
                        <Skeleton className="h-24 w-full" />
                      </div>
                    ) : (
                      <RevisionHistory
                        versions={versions}
                        from={from}
                        to={to}
                        onFrom={setFrom}
                        onTo={setTo}
                      />
                    )}
                  </div>
                ) : null}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

function RevisionHistory({
  versions,
  from,
  to,
  onFrom,
  onTo,
}: {
  versions: SavedQueryVersion[]
  from: number | null
  to: number | null
  onFrom: (revision: number) => void
  onTo: (revision: number) => void
}) {
  const older = versions.find((one) => one.revision === from)
  const newer = versions.find((one) => one.revision === to)
  const lines = useMemo(
    () =>
      older && newer ? diffLines(older.sql_template, newer.sql_template) : [],
    [older, newer],
  )
  const summary = diffSummary(lines)

  return (
    <div>
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-[150px]">
          <Select
            id="diff-from"
            label="Compare"
            value={String(from ?? '')}
            onChange={(event) => onFrom(Number(event.target.value))}
          >
            {versions.map((one) => (
              <option key={one.id} value={one.revision}>
                revision {one.revision}
              </option>
            ))}
          </Select>
        </div>
        <span className="pb-3 text-small text-text-tertiary">with</span>
        <div className="w-[150px]">
          <Select
            id="diff-to"
            label="Against"
            value={String(to ?? '')}
            onChange={(event) => onTo(Number(event.target.value))}
          >
            {versions.map((one) => (
              <option key={one.id} value={one.revision}>
                revision {one.revision}
              </option>
            ))}
          </Select>
        </div>
        <div className="flex flex-wrap items-center gap-2 pb-1">
          <Badge>{`${summary.added} added`}</Badge>
          <Badge>{`${summary.removed} removed`}</Badge>
          {older ? (
            <span className="text-small text-text-tertiary">
              {formatWhen(older.created_at)} → {newer ? formatWhen(newer.created_at) : ''}
            </span>
          ) : null}
        </div>
      </div>

      {from === to ? (
        <p className="mt-5 text-small text-text-secondary">
          These are the same revision. Pick a different one on either side.
        </p>
      ) : summary.added === 0 && summary.removed === 0 ? (
        <p className="mt-5 text-small text-text-secondary">
          These revisions have identical SQL — only the name or parameters changed.
        </p>
      ) : (
        <pre className="mt-5 max-h-[380px] overflow-auto rounded-xl border border-border bg-canvas p-0 font-mono text-small">
          {lines.map((line, index) => (
            <div
              key={index}
              className={
                'flex gap-3 px-3 py-0.5 ' +
                (line.kind === 'added'
                  ? 'bg-accent/10 text-text-primary'
                  : line.kind === 'removed'
                    ? 'text-text-tertiary'
                    : 'text-text-secondary')
              }
            >
              <span
                aria-hidden="true"
                className={
                  'w-3 shrink-0 select-none ' +
                  (line.kind === 'added' ? 'text-accent' : 'text-text-tertiary')
                }
              >
                {line.kind === 'added' ? '+' : line.kind === 'removed' ? '−' : ' '}
              </span>
              <span
                className={
                  'w-8 shrink-0 select-none text-right text-text-tertiary ' +
                  (line.kind === 'removed' ? 'line-through' : '')
                }
              >
                {line.before ?? line.after ?? ''}
              </span>
              <span
                className={
                  'whitespace-pre-wrap break-words ' +
                  (line.kind === 'removed' ? 'line-through decoration-border-hover' : '')
                }
              >
                {line.text || ' '}
              </span>
            </div>
          ))}
        </pre>
      )}

      <p className="mt-4 text-small text-text-tertiary">
        Revision 1 is the SQL as first saved. Each “Save revision” appends the
        editor's SQL as the next one.
      </p>
    </div>
  )
}
