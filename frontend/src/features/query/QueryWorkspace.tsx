import { useState } from 'react'

import { Badge } from '../../components/Badge'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { TypingSql } from '../../components/TypingSql'
import { apiFetch, apiRaw, ApiError } from '../../lib/api'
import type {
  ExecuteResponse,
  ExplanationResponse,
  ProjectSchema,
  QuestionResponse,
} from '../../lib/types'
import { ExplanationPanel } from './ExplanationPanel'
import { SaveQueryDialog } from './SaveQueryDialog'
import { ResultsTable } from './ResultsTable'
import { SchemaRail } from './SchemaRail'

const SUGGESTIONS = [
  'How many rows are in each table?',
  'Which rows are duplicated?',
  'Show the 10 largest values',
]

interface QueryWorkspaceProps {
  projectId: number
  schema: ProjectSchema
  /** Controlled by the project page, so History can load a query into here
   *  and so the text survives switching tabs. */
  sql: string
  onSqlChange: (sql: string) => void
}

/**
 * PRD 10.9: three panes — a 240px schema rail, the question and SQL in the
 * centre, results below. This is where the product lives, so it is where the
 * boldness goes: the SQL block is a data surface with the violet glow, and it
 * is the only place monospace appears outside a result cell.
 */
export function QueryWorkspace({
  projectId,
  schema,
  sql,
  onSqlChange: setSql,
}: QueryWorkspaceProps) {
  const [question, setQuestion] = useState('')
  const [generatedSql, setGeneratedSql] = useState('')
  const [answer, setAnswer] = useState<QuestionResponse | null>(null)
  const [execution, setExecution] = useState<ExecuteResponse | null>(null)
  const [error, setError] = useState('')
  const [asking, setAsking] = useState(false)
  const [running, setRunning] = useState(false)
  const [explanation, setExplanation] = useState<ExplanationResponse | null>(null)
  const [notes, setNotes] = useState<ExplanationResponse | null>(null)
  const [busyPanel, setBusyPanel] = useState<'explain' | 'optimize' | null>(null)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState('')

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
      setExplanation(null)
      setNotes(null)
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

  function exportAs(format: 'csv' | 'json' | 'markdown') {
    const params = new URLSearchParams({ format })
    if (format !== 'markdown') params.set('sql', sql)
    // A plain link would drop the Authorization header, so the request goes
    // through the API client and the blob is handed to the browser here.
    void (async () => {
      setError('')
      try {
        const response = await apiRaw(`/projects/${projectId}/export?${params}`)
        const blob = await response.blob()
        const url = URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.href = url
        link.download = format === 'markdown' ? 'schema.md' : `results.${format}`
        document.body.appendChild(link)
        link.click()
        link.remove()
        URL.revokeObjectURL(url)
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : 'That export failed.')
      }
    })()
  }

  async function describe(kind: 'explain' | 'optimize') {
    if (!sql.trim()) return
    setError('')
    setBusyPanel(kind)
    try {
      const result = await apiFetch<ExplanationResponse>(
        `/projects/${projectId}/${kind}`,
        { method: 'POST', body: JSON.stringify({ sql }) },
      )
      if (kind === 'explain') setExplanation(result)
      else setNotes(result)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'That could not be analysed.')
    } finally {
      setBusyPanel(null)
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
      <SchemaRail schema={schema} onInsert={(text) => setSql(sql + text)} />

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

        {asking ? <TypingSql question={question} /> : null}

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
            <Button
              onClick={() => void run()}
              disabled={running || !sql.trim()}
              loading={running}
            >
              {running ? 'Running…' : 'Run query'}
            </Button>
            <Button
              variant="ghost"
              onClick={() => void describe('explain')}
              disabled={busyPanel !== null || !sql.trim()}
            >
              {busyPanel === 'explain' ? 'Explaining…' : 'Explain'}
            </Button>
            <Button
              variant="ghost"
              onClick={() => void describe('optimize')}
              disabled={busyPanel !== null || !sql.trim()}
            >
              {busyPanel === 'optimize' ? 'Analysing…' : 'Optimise'}
            </Button>
            <Button
              variant="ghost"
              onClick={() => setSaving(true)}
              disabled={!sql.trim()}
            >
              Save
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

        {notice ? (
          <p role="status" className="mt-6 text-small text-text-secondary">
            {notice}
          </p>
        ) : null}

        {saving ? (
          <SaveQueryDialog
            sql={sql}
            onClose={() => setSaving(false)}
            onSaved={(name) => {
              setSaving(false)
              setNotice(`Saved as “${name}”.`)
            }}
          />
        ) : null}

        {execution?.status === 'success' ? (
          <div className="mt-6 flex flex-wrap items-center gap-3">
            <span className="text-small text-text-secondary">Export</span>
            {(['csv', 'json', 'markdown'] as const).map((format) => (
              <button
                key={format}
                type="button"
                onClick={() => exportAs(format)}
                className="text-small text-text-secondary underline hover:text-text-primary"
              >
                {format === 'markdown' ? 'schema as Markdown' : format.toUpperCase()}
              </button>
            ))}
          </div>
        ) : null}

        {running ? <ResultsTable loading execution={execution} /> : null}
        {!running && execution ? <ResultsTable execution={execution} /> : null}

        {!running && !execution && !asking ? (
          <div className="mt-8">
            <EmptyState
              compact
              icon="chart"
              title="No results yet"
              className="text-left"
            >
              <p className="mx-auto max-w-[52ch]">
                Ask a question above, or write SQL in the editor and run it.
                Every query is checked before it touches your data.
              </p>
              <div className="mt-5 flex flex-wrap justify-center gap-2">
                {SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    onClick={() => setQuestion(suggestion)}
                    className="rounded-full border border-border px-4 py-2 text-small text-text-secondary transition-colors duration-200 hover:border-border-hover hover:bg-surface hover:text-text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </EmptyState>
          </div>
        ) : null}

        {explanation ? (
          <ExplanationPanel
            sql={sql}
            summary={explanation.summary}
            clauses={explanation.clauses}
          />
        ) : null}

        {notes ? (
          <ExplanationPanel
            sql={sql}
            summary={notes.summary}
            clauses={notes.clauses}
            variant="optimize"
          />
        ) : null}
      </div>
    </div>
  )
}
