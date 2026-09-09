import { useState } from 'react'

import { Badge } from '../../components/Badge'
import { Button } from '../../components/Button'
import { apiFetch, ApiError } from '../../lib/api'
import type {
  ExecuteResponse,
  ProjectSchema,
  QuestionResponse,
} from '../../lib/types'
import { ResultsTable } from './ResultsTable'
import { SchemaRail } from './SchemaRail'

interface QueryWorkspaceProps {
  projectId: number
  schema: ProjectSchema
}

/**
 * PRD 10.9: three panes — a 240px schema rail, the question and SQL in the
 * centre, results below. This is where the product lives, so it is where the
 * boldness goes: the SQL block is a data surface with the violet glow, and it
 * is the only place monospace appears outside a result cell.
 */
export function QueryWorkspace({ projectId, schema }: QueryWorkspaceProps) {
  const [question, setQuestion] = useState('')
  const [sql, setSql] = useState('')
  const [generatedSql, setGeneratedSql] = useState('')
  const [answer, setAnswer] = useState<QuestionResponse | null>(null)
  const [execution, setExecution] = useState<ExecuteResponse | null>(null)
  const [error, setError] = useState('')
  const [asking, setAsking] = useState(false)
  const [running, setRunning] = useState(false)

  const edited = sql.trim() !== generatedSql.trim()

  async function ask() {
    if (!question.trim()) return
    setError('')
    setAsking(true)
    try {
      const result = await apiFetch<QuestionResponse>(
        `/projects/${projectId}/query`,
        { method: 'POST', body: JSON.stringify({ question }) },
      )
      setAnswer(result)
      setSql(result.sql)
      setGeneratedSql(result.sql)
      setExecution(result.execution)
    } catch (caught) {
      // PRD 13: a model outage must not take the editor with it.
      setError(
        caught instanceof ApiError
          ? caught.message
          : 'Could not reach the assistant. You can still write SQL below.',
      )
    } finally {
      setAsking(false)
    }
  }

  async function run() {
    if (!sql.trim()) return
    setError('')
    setRunning(true)
    try {
      setExecution(
        await apiFetch<ExecuteResponse>(`/projects/${projectId}/execute`, {
          method: 'POST',
          body: JSON.stringify({
            sql,
            question: question || null,
            generated_sql: generatedSql || null,
            was_edited: edited,
          }),
        }),
      )
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not run that.')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="flex flex-col gap-10 lg:flex-row">
      <SchemaRail schema={schema} onInsert={(text) => setSql((s) => s + text)} />

      <div className="min-w-0 flex-1">
        <label htmlFor="question" className="text-small text-text-secondary">
          Ask a question
        </label>
        <div className="mt-2 flex flex-wrap gap-3">
          <input
            id="question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') void ask()
            }}
            placeholder="Which customers spent the most last month?"
            className={
              'min-w-[260px] flex-1 rounded-2xl border border-border bg-surface ' +
              'px-4 py-3 text-body text-text-primary ' +
              'placeholder:text-text-tertiary hover:border-border-hover ' +
              'focus:border-border-hover focus:outline-2 focus:outline-offset-2 ' +
              'focus:outline-accent'
            }
          />
          <Button variant="ghost" onClick={() => void ask()} disabled={asking}>
            {asking ? 'Thinking…' : 'Generate SQL'}
          </Button>
        </div>

        {answer?.missing && !answer.sql ? (
          // PRD F5: say what is missing rather than invent a table.
          <p role="status" className="mt-6 text-body text-text-secondary">
            {answer.missing}
          </p>
        ) : null}

        {answer && answer.assumptions.length > 0 ? (
          <div className="mt-6 flex flex-wrap items-center gap-2">
            <span className="text-small text-text-secondary">Assumed:</span>
            {answer.assumptions.map((assumption) => (
              <Badge key={assumption}>{assumption}</Badge>
            ))}
            {answer.cached ? <Badge>from cache</Badge> : null}
          </div>
        ) : null}

        <div className="mt-8">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <label htmlFor="sql" className="text-small text-text-secondary">
              SQL
            </label>
            {edited && generatedSql ? (
              <span className="text-small text-text-secondary">edited</span>
            ) : null}
          </div>
          {/* PRD 10.9: the SQL block is the one violet-glow data surface. */}
          <div className="mt-2 rounded-2xl bg-glow-violet/15 p-px">
            <textarea
              id="sql"
              value={sql}
              onChange={(event) => setSql(event.target.value)}
              rows={7}
              spellCheck={false}
              placeholder="SELECT * FROM ..."
              className={
                'w-full rounded-2xl border border-border bg-surface px-4 py-3 ' +
                'font-mono text-small text-text-primary ' +
                'placeholder:text-text-tertiary hover:border-border-hover ' +
                'focus:border-border-hover focus:outline-2 focus:outline-offset-2 ' +
                'focus:outline-accent'
              }
            />
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-4">
            {/* The single lime element on this screen. */}
            <Button onClick={() => void run()} disabled={running || !sql.trim()}>
              {running ? 'Running…' : 'Run query'}
            </Button>
            {execution?.status === 'success' ? (
              <span className="text-small text-text-secondary">
                {execution.row_count} rows in {execution.duration_ms} ms
              </span>
            ) : null}
          </div>
        </div>

        {error ? (
          <p role="alert" className="mt-6 text-small text-text-primary">
            {error}
          </p>
        ) : null}

        {execution ? <ResultsTable execution={execution} /> : null}
      </div>
    </div>
  )
}
