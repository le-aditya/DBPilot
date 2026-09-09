import { useMemo, useState } from 'react'

import { Badge } from '../../components/Badge'
import type { ProjectSchema } from '../../lib/types'
import { TablePreview } from './TablePreview'

interface SchemaExplorerProps {
  projectId: number
  schema: ProjectSchema
}

/**
 * PRD 10.9: rail plus detail table, no cards. This screen is distinguished from
 * the query workspace by layout rather than colour, and its whole accent budget
 * goes to the lime outline PK badges.
 */
export function SchemaExplorer({ projectId, schema }: SchemaExplorerProps) {
  const [selected, setSelected] = useState(schema.tables[0]?.name ?? '')
  const [search, setSearch] = useState('')

  // PRD F3: search across table *and* column names, so looking for a field you
  // half-remember finds the table holding it.
  const matches = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (!needle) return schema.tables
    return schema.tables.filter(
      (table) =>
        table.name.toLowerCase().includes(needle) ||
        table.columns.some((column) => column.name.toLowerCase().includes(needle)),
    )
  }, [schema.tables, search])

  const table = schema.tables.find((one) => one.name === selected)

  return (
    <div className="flex flex-col gap-10 md:flex-row">
      <nav className="w-full shrink-0 md:w-[240px]" aria-label="Tables">
        <label htmlFor="schema-search" className="sr-only">
          Search tables and columns
        </label>
        <input
          id="schema-search"
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search"
          className={
            'w-full rounded-2xl border border-border bg-surface px-4 py-2 ' +
            'text-small text-text-primary placeholder:text-text-tertiary ' +
            'hover:border-border-hover focus:border-border-hover ' +
            'focus:outline-2 focus:outline-offset-2 focus:outline-accent'
          }
        />

        <ul className="mt-4 border-t border-border">
          {matches.map((one) => (
            <li key={one.name}>
              <button
                type="button"
                onClick={() => setSelected(one.name)}
                aria-current={one.name === selected}
                aria-label={`${one.name}, ${one.row_count} rows`}
                className={
                  'flex w-full items-baseline justify-between gap-3 border-b ' +
                  'border-border py-3 text-left transition-colors ' +
                  (one.name === selected
                    ? 'text-text-primary'
                    : 'text-text-secondary hover:text-text-primary')
                }
              >
                <span className="text-body">{one.name}</span>
                <span className="text-small text-text-secondary">
                  {one.row_count}
                </span>
              </button>
            </li>
          ))}
          {matches.length === 0 ? (
            <li className="py-3 text-small text-text-secondary">
              Nothing matches “{search}”.
            </li>
          ) : null}
        </ul>
      </nav>

      <div className="min-w-0 flex-1">
        {table ? (
          <>
            <h3 className="text-h3 text-text-primary">{table.name}</h3>
            <p className="mt-1 text-small text-text-secondary">
              {table.row_count} rows · {table.columns.length} columns
            </p>

            <div className="mt-8 overflow-x-auto">
              <table className="w-full border-collapse text-left">
                <thead>
                  <tr className="border-b border-border text-eyebrow uppercase text-text-secondary">
                    <th className="py-3 pr-6 font-normal">Column</th>
                    <th className="py-3 pr-6 font-normal">Type</th>
                    <th className="py-3 pr-6 font-normal">Nullable</th>
                    <th className="py-3 font-normal">Keys</th>
                  </tr>
                </thead>
                <tbody>
                  {table.columns.map((column) => (
                    <tr key={column.name} className="border-b border-border">
                      <td className="py-3 pr-6 text-body text-text-primary">
                        {column.name}
                      </td>
                      <td className="py-3 pr-6 font-mono text-small text-text-secondary">
                        {column.data_type}
                      </td>
                      <td className="py-3 pr-6 text-small text-text-secondary">
                        {column.nullable ? 'yes' : 'no'}
                      </td>
                      <td className="flex flex-wrap gap-2 py-3">
                        {column.is_primary_key ? (
                          <Badge tone="accent">PK</Badge>
                        ) : null}
                        {column.references_table ? (
                          <Badge>
                            {`FK → ${column.references_table}.${column.references_column}`}
                          </Badge>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {table.indexes.length > 0 ? (
              <div className="mt-10">
                <h4 className="text-small uppercase tracking-[0.12em] text-text-secondary">
                  Indexes
                </h4>
                <ul className="mt-3 border-t border-border">
                  {table.indexes.map((index) => (
                    <li
                      key={index.name}
                      className="border-b border-border py-3 font-mono text-small text-text-secondary"
                    >
                      {index.name}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            <TablePreview key={table.name} projectId={projectId} table={table.name} />
          </>
        ) : (
          <p className="text-body text-text-secondary">
            Pick a table from the list to see its columns.
          </p>
        )}
      </div>
    </div>
  )
}
