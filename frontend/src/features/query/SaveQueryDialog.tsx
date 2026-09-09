import { useState, type FormEvent } from 'react'

import { Button } from '../../components/Button'
import { Field } from '../../components/Field'
import { apiFetch } from '../../lib/api'
import type { SavedQuery } from '../../lib/types'

interface SaveQueryDialogProps {
  sql: string
  onClose: () => void
  onSaved: (name: string) => void
}

/** Saving a query. Parameters are found server-side, so this only needs a name. */
export function SaveQueryDialog({ sql, onClose, onSaved }: SaveQueryDialogProps) {
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError('')
    setBusy(true)
    try {
      const saved = await apiFetch<SavedQuery>('/saved-queries', {
        method: 'POST',
        body: JSON.stringify({ name, sql_template: sql }),
      })
      onSaved(saved.name)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'That could not be saved.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form
      onSubmit={submit}
      aria-label="Save this query"
      className="mt-6 flex flex-wrap items-end gap-4 rounded-2xl border border-border bg-surface p-6"
    >
      <div className="min-w-[240px] flex-1">
        <Field
          id="saved-name"
          label="Name this query"
          required
          value={name}
          onChange={(event) => setName(event.target.value)}
          error={error || undefined}
        />
      </div>
      <Button type="submit" disabled={busy || !name.trim()}>
        {busy ? 'Saving…' : 'Save query'}
      </Button>
      <Button variant="ghost" type="button" onClick={onClose} disabled={busy}>
        Cancel
      </Button>
      <p className="w-full text-small text-text-secondary">
        Use <code className="font-mono">:name</code> in the SQL to make it a
        parameter you fill in each time you run it.
      </p>
    </form>
  )
}
