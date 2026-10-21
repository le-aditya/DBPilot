import { useCallback, useEffect, useState } from 'react'

import { EmptyState } from '../../components/EmptyState'
import { Skeleton } from '../../components/Skeleton'
import { apiFetch } from '../../lib/api'
import { formatBytes, formatCount, formatDuration, formatWhen } from '../../lib/format'
import type { DashboardResponse, QuerySummary } from '../../lib/types'
import { StatusDot } from './StatusDot'

interface DashboardProps {
  projectId: number
}

/**
 * PRD 10.9: a bento grid — one wide card, two stat cards, one tall activity
 * feed — with a single highlighted metric. Queries this week is the highlighted
 * one; every other number stays in primary text so the accent still means
 * something.
 */
export function Dashboard({ projectId }: DashboardProps) {
  const [data, setData] = useState<DashboardResponse | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      setData(await apiFetch<DashboardResponse>(`/projects/${projectId}/dashboard`))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not load the dashboard.')
    }
  }, [projectId])

  useEffect(() => {
    void load()
  }, [load])

  if (error) {
    return (
      <p role="alert" className="text-small text-text-primary">
        {error}
      </p>
    )
  }
  if (!data) {
    return (
      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-2xl border border-border bg-surface p-6 md:col-span-2">
          <Skeleton className="h-3 w-32" />
          <Skeleton className="mt-6 h-14 w-32" />
          <Skeleton className="mt-5 h-4 w-64" />
        </div>
        <div className="rounded-2xl border border-border bg-surface p-6 md:row-span-2">
          <Skeleton className="h-3 w-28" />
          {[0, 1, 2].map((index) => (
            <Skeleton key={index} className="mt-5 h-10 w-full" />
          ))}
        </div>
        <div className="rounded-2xl border border-border bg-surface p-6">
          <Skeleton className="h-3 w-16" />
          <Skeleton className="mt-6 h-10 w-20" />
        </div>
        <div className="rounded-2xl border border-border bg-surface p-6">
          <Skeleton className="h-3 w-28" />
          <Skeleton className="mt-6 h-10 w-full" />
        </div>
      </div>
    )
  }

  return (
    <div className="grid gap-4 md:grid-cols-3">
      <Card className="md:col-span-2">
        <p className="text-eyebrow uppercase text-text-secondary">Queries this week</p>
        {/* The single highlighted metric for this screen. */}
        <p className="mt-4 text-display text-accent">{formatCount(data.queries_this_week)}</p>
        <p className="mt-3 text-small text-text-secondary">
          {formatCount(data.queries_run)} in total ·{' '}
          {formatCount(data.blocked_count)} blocked ·{' '}
          {formatDuration(data.average_duration_ms)} average
        </p>
      </Card>

      <Card className="md:row-span-2">
        <p className="text-eyebrow uppercase text-text-secondary">Recent activity</p>
        {data.recent.length === 0 ? (
          <div className="mt-5">
            <EmptyState compact icon="spark" title="No queries yet">
              Ask your first question in the Query tab and it will appear here.
            </EmptyState>
          </div>
        ) : (
          <ul className="mt-4">
            {data.recent.map((one) => (
              <li key={one.id} className="border-b border-border py-3 last:border-b-0">
                <div className="flex items-baseline gap-2">
                  <StatusDot status={one.status} />
                  <p className="min-w-0 flex-1 truncate text-small text-text-primary">
                    {one.question_text || one.executed_sql || '—'}
                  </p>
                </div>
                <p className="mt-1 pl-4 text-small text-text-secondary">
                  {formatWhen(one.created_at)}
                </p>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <p className="text-eyebrow uppercase text-text-secondary">Data</p>
        <p className="mt-4 text-h2 text-text-primary">{formatCount(data.table_count)}</p>
        <p className="mt-2 text-small text-text-secondary">
          tables · {formatCount(data.total_rows)} rows · {formatBytes(data.storage_bytes)}
        </p>
      </Card>

      <Card>
        <p className="text-eyebrow uppercase text-text-secondary">Slowest queries</p>
        {data.slowest.length === 0 ? (
          <p className="mt-4 max-w-[40ch] text-small text-text-secondary">
            No timings yet. Once you run a few queries, the slowest ones surface
            here so you know what to index.
          </p>
        ) : (
          <ul className="mt-4">
            {data.slowest.map((one: QuerySummary) => (
              <li
                key={one.id}
                className="flex items-baseline justify-between gap-3 border-b border-border py-2 last:border-b-0"
              >
                <span className="min-w-0 flex-1 truncate font-mono text-small text-text-secondary">
                  {one.executed_sql}
                </span>
                <span className="text-small text-text-primary">
                  {formatDuration(one.duration_ms)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}

function Card({
  className = '',
  children,
}: {
  className?: string
  children: React.ReactNode
}) {
  return (
    <section
      className={`rounded-2xl border border-border bg-surface p-6 ${className}`}
    >
      {children}
    </section>
  )
}
