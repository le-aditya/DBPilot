import { useState } from 'react'

import { Button } from '../../components/Button'
import { Select } from '../../components/Select'
import { COLUMN_TYPES, type ColumnType, type TableSpec } from '../../lib/types'

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
        anything that looks wrong — nothing has been created yet.
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

  return (
    <div className="mt-8">
      <p className="text-small text-text-secondary">
        {table.source_filename} · {table.sampled_rows} rows sampled
      </p>

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
                  <p className="text-body text-text-primary">{column.name}</p>
                  {column.name !== column.source_name ? (
                    <p className="mt-1 text-small text-text-secondary">
                      from “{column.source_name}”
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
