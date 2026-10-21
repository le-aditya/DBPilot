import { useState } from 'react'

import { Badge } from '../../components/Badge'
import { Button } from '../../components/Button'
import { Select } from '../../components/Select'
import {
  COLUMN_TYPES,
  type ColumnType,
  type TableSpec,
  type UploadTableDiff,
} from '../../lib/types'

interface SchemaReviewProps {
  tables: TableSpec[]
  busy: boolean
  onChange: (tables: TableSpec[]) => void
  onCommit: () => void
  onCancel: () => void
}

const SURROGATE = ''

/**
 * PRD F2.1's review step: nothing has been created yet, and every inference is
 * a suggestion the user can overrule before it becomes a table.
 */
export function SchemaReview({
  tables,
  busy,
  onChange,
  onCommit,
  onCancel,
}: SchemaReviewProps) {
  const [openTable, setOpenTable] = useState(0)

  function updateTable(index: number, next: Partial<TableSpec>) {
    onChange(tables.map((table, at) => (at === index ? { ...table, ...next } : table)))
  }

  function updateColumnType(index: number, column: string, type: ColumnType) {
    updateTable(index, {
      columns: tables[index].columns.map((one) =>
        one.name === column ? { ...one, type } : one,
      ),
    })
  }

  return (
    <section className="mt-12">
      <h3 className="text-h3 text-text-primary">Check the columns</h3>
      <p className="mt-2 max-w-[60ch] text-body text-text-secondary">
        These types were inferred from the first rows of each file. Change
        anything that looks wrong — nothing has been created yet. Re-uploading a
        file replaces the table of the same name.
      </p>

      {tables.length > 1 ? (
        <div className="mt-8 flex flex-wrap gap-2">
          {tables.map((table, index) => (
            <button
              key={table.name}
              type="button"
              onClick={() => setOpenTable(index)}
              aria-current={index === openTable}
              className={
                'rounded-full border px-4 py-2 text-small transition-colors ' +
                (index === openTable
                  ? 'border-border-hover text-text-primary'
                  : 'border-border text-text-secondary hover:border-border-hover')
              }
            >
              {table.name}
            </button>
          ))}
        </div>
      ) : null}

      {tables[openTable] ? (
        <TableEditor
          key={tables[openTable].name}
          table={tables[openTable]}
          others={tables.filter((_, at) => at !== openTable)}
          onTypeChange={(column, type) => updateColumnType(openTable, column, type)}
          onPrimaryKeyChange={(value) =>
            updateTable(openTable, { primary_key: value === SURROGATE ? null : value })
          }
          onForeignKeysChange={(foreign_keys) =>
            updateTable(openTable, { foreign_keys })
          }
        />
      ) : null}

      <div className="mt-10 flex flex-wrap gap-4">
        <Button onClick={onCommit} disabled={busy}>
          {busy ? 'Creating tables…' : 'Create tables'}
        </Button>
        <Button variant="ghost" onClick={onCancel} disabled={busy}>
          Start over
        </Button>
      </div>
    </section>
  )
}

interface TableEditorProps {
  table: TableSpec
  others: TableSpec[]
  onTypeChange: (column: string, type: ColumnType) => void
  onPrimaryKeyChange: (value: string) => void
  onForeignKeysChange: (keys: TableSpec['foreign_keys']) => void
}

function TableEditor({
  table,
  others,
  onTypeChange,
  onPrimaryKeyChange,
  onForeignKeysChange,
}: TableEditorProps) {
  // A column with blanks cannot be a key, so it is not offered as one.
  const keyCandidates = table.columns.filter((column) => !column.nullable)

  function setReference(column: string, value: string) {
    const remaining = table.foreign_keys.filter((key) => key.column !== column)
    if (!value) {
      onForeignKeysChange(remaining)
      return
    }
    const [references_table, references_column] = value.split('.')
    onForeignKeysChange([
      ...remaining,
      { column, references_table, references_column },
    ])
  }

  const targets = others.flatMap((other) =>
    other.columns
      .filter((column) => !column.nullable)
      .map((column) => `${other.name}.${column.name}`),
  )

  return (    <div className="mt-8">
      <p className="text-small text-text-secondary">
        {table.source_filename} · {table.sampled_rows} rows sampled
      </p>

      {table.diff?.existing ? <TableDiffNotice diff={table.diff} /> : null}

      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[760px] border-collapse text-left">
          <thead>
            <tr className="border-b border-border text-eyebrow uppercase text-text-secondary">
              <th className="py-3 pr-4 font-normal">Column</th>
              <th className="py-3 pr-4 font-normal">Type</th>
              <th className="py-3 pr-4 font-normal">Sample values</th>
              {targets.length > 0 ? (
                <th className="py-3 font-normal">References</th>
              ) : null}
            </tr>
          </thead>
          <tbody>
            {table.columns.map((column) => (
              <tr key={column.name} className="border-b border-border align-top">
                <td className="py-4 pr-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-body text-text-primary">{column.name}</p>
                    {table.diff?.added_columns.includes(column.name) ? (
                      <Badge tone="accent">new</Badge>
                    ) : null}
                  </div>
                  {column.name !== column.source_name ? (
                    <p className="mt-1 text-small text-text-secondary">
                      from “{column.source_name}”
                    </p>
                  ) : null}
                  {table.diff?.type_changes.find(
                    (change) => change.column === column.name,
                  ) ? (
                    <p className="mt-1 text-small text-text-secondary">
                      was{' '}
                      <span className="font-mono">
                        {
                          table.diff.type_changes.find(
                            (change) => change.column === column.name,
                          )?.was
                        }
                      </span>
                    </p>
                  ) : null}
                </td>
                <td className="py-4 pr-4">
                  <Select
                    id={`type-${table.name}-${column.name}`}
                    label={`Type for ${column.name}`}
                    labelHidden
                    value={column.type}
                    onChange={(event) =>
                      onTypeChange(column.name, event.target.value as ColumnType)
                    }
                  >
                    {COLUMN_TYPES.map((type) => (
                      <option key={type} value={type}>
                        {type}
                      </option>
                    ))}
                  </Select>
                </td>
                <td className="py-4 pr-4 text-small text-text-secondary">
                  {column.samples.join(', ') || '—'}
                </td>
                {targets.length > 0 ? (
                  <td className="py-4">
                    <Select
                      id={`fk-${table.name}-${column.name}`}
                      label={`Foreign key for ${column.name}`}
                      labelHidden
                      value={
                        table.foreign_keys.find((key) => key.column === column.name)
                          ? `${table.foreign_keys.find((key) => key.column === column.name)?.references_table}.${table.foreign_keys.find((key) => key.column === column.name)?.references_column}`
                          : ''
                      }
                      onChange={(event) =>
                        setReference(column.name, event.target.value)
                      }
                    >
                      <option value="">—</option>
                      {targets.map((target) => (
                        <option key={target} value={target}>
                          {target}
                        </option>
                      ))}
                    </Select>
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-8 max-w-[320px]">
        <Select
          id={`pk-${table.name}`}
          label="Primary key"
          value={table.primary_key ?? SURROGATE}
          onChange={(event) => onPrimaryKeyChange(event.target.value)}
        >
          <option value={SURROGATE}>Add an id column for me</option>
          {keyCandidates.map((column) => (
            <option key={column.name} value={column.name}>
              {column.name}
            </option>
          ))}
        </Select>
      </div>
    </div>
  )
}

/** What a re-upload changes, shown before anything is dropped. */
function TableDiffNotice({ diff }: { diff: UploadTableDiff }) {
  const changed =
    diff.added_columns.length > 0 ||
    diff.removed_columns.length > 0 ||
    diff.type_changes.length > 0

  return (
    <div className="mt-4 rounded-2xl border border-border bg-canvas/60 p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-eyebrow uppercase text-text-secondary">
          This table already exists
        </p>
        <span className="text-small text-text-tertiary">
          {diff.previous_row_count?.toLocaleString() ?? 0} rows now
        </span>
      </div>

      {!changed ? (
        <p className="mt-3 text-small text-text-secondary">
          The columns are identical. Committing reloads this table's rows from
          the new file and leaves its structure alone.
        </p>
      ) : (
        <div className="mt-3 space-y-1.5">
          {diff.added_columns.length > 0 ? (
            <p className="text-small text-text-primary">
              <span className="mr-2 font-mono text-accent">+</span>
              added{' '}
              <span className="font-mono text-text-secondary">
                {diff.added_columns.join(', ')}
              </span>
            </p>
          ) : null}
          {diff.removed_columns.length > 0 ? (
            <p className="text-small text-text-primary">
              <span className="mr-2 font-mono text-text-tertiary">−</span>
              dropped{' '}
              <span className="font-mono text-text-secondary">
                {diff.removed_columns.join(', ')}
              </span>
            </p>
          ) : null}
          {diff.type_changes.map((change) => (
            <p key={change.column} className="text-small text-text-primary">
              <span className="mr-2 font-mono text-text-tertiary">±</span>
              retyped{' '}
              <span className="font-mono text-text-secondary">{change.column}</span>{' '}
              from <span className="font-mono">{change.was}</span> to{' '}
              <span className="font-mono">{change.now}</span>
            </p>
          ))}
        </div>
      )}

      <p className="mt-4 text-small text-text-tertiary">
        Committing drops this table and recreates it, so its existing rows are
        replaced. Saved SQL that used a dropped column will stop working.
      </p>
    </div>
  )
}
