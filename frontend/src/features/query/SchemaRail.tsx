import { useState } from 'react'

import type { ProjectSchema } from '../../lib/types'

interface SchemaRailProps {
  schema: ProjectSchema
  onInsert: (text: string) => void
}

/**
 * PRD 10.9: the 240px rail of the three-pane workspace.
 *
 * Names are clickable because the alternative is retyping a column you can see
 * on screen. No accent here — the workspace spends its whole budget on Run.
 */
export function SchemaRail({ schema, onInsert }: SchemaRailProps) {
  const [open, setOpen] = useState<string | null>(schema.tables[0]?.name ?? null)

  return (
    <nav className="w-full shrink-0 lg:w-[240px]" aria-label="Schema">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-eyebrow uppercase text-text-secondary">Tables</h3>
        <span className="text-small text-text-tertiary">{schema.tables.length}</span>
      </div>
      <ul className="mt-4 border-t border-border">
        {schema.tables.map((table) => (
          <li key={table.name} className="border-b border-border">
            <div
              className={
                'group flex items-center justify-between gap-2 px-2 py-2.5 ' +
                'transition-colors duration-150 hover:bg-surface '
              }
            >
              <button
                type="button"
                onClick={() => setOpen(open === table.name ? null : table.name)}
                aria-expanded={open === table.name}
                className="flex min-w-0 items-center gap-1.5 text-left text-body text-text-primary"
              >
                <span
                  aria-hidden="true"
                  className={
                    'inline-block text-small text-text-tertiary transition-transform duration-200 ' +
                    (open === table.name ? 'rotate-90' : '')
                  }
                >
                  ›
                </span>
                <span className="truncate">{table.name}</span>
              </button>
              <button
                type="button"
                onClick={() => onInsert(table.name)}
                aria-label={`Insert ${table.name} into the SQL`}
                className="rounded-full px-2 text-small text-text-tertiary opacity-0 transition-[opacity,color] duration-150 hover:text-accent focus-visible:opacity-100 group-hover:opacity-100"
              >
                +
              </button>
            </div>
            {open === table.name ? (
              <ul className="pb-2">
                {table.columns.map((column) => (
                  <li key={column.name}>
                    <button
                      type="button"
                      onClick={() => onInsert(column.name)}
                      aria-label={`Insert ${column.name} into the SQL`}
                      className={
                        'flex w-full items-baseline justify-between gap-2 px-2 py-1.5 ' +
                        'text-left font-mono text-small text-text-secondary ' +
                        'transition-colors duration-150 hover:bg-surface ' +
                        'hover:text-text-primary'
                      }
                    >
                      <span className="truncate">{column.name}</span>
                      <span className="shrink-0 text-text-tertiary">
                        {column.data_type}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </li>
        ))}
      </ul>
    </nav>
  )
}
