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
      <h3 className="text-eyebrow uppercase text-text-secondary">Tables</h3>
      <ul className="mt-4 border-t border-border">
        {schema.tables.map((table) => (
          <li key={table.name} className="border-b border-border">
            <div className="flex items-center justify-between gap-2 py-3">
              <button
                type="button"
                onClick={() => setOpen(open === table.name ? null : table.name)}
                aria-expanded={open === table.name}
                className="text-left text-body text-text-primary hover:underline"
              >
                {table.name}
              </button>
              <button
                type="button"
                onClick={() => onInsert(table.name)}
                aria-label={`Insert ${table.name} into the SQL`}
                className="text-small text-text-secondary hover:text-text-primary"
              >
                +
              </button>
            </div>
            {open === table.name ? (
              <ul className="pb-3">
                {table.columns.map((column) => (
                  <li key={column.name}>
                    <button
                      type="button"
                      onClick={() => onInsert(column.name)}
                      aria-label={`Insert ${column.name} into the SQL`}
                      className={
                        'flex w-full items-baseline justify-between gap-2 py-1 ' +
                        'text-left font-mono text-small text-text-secondary ' +
                        'hover:text-text-primary'
                      }
                    >
                      <span>{column.name}</span>
                      <span className="text-text-tertiary">{column.data_type}</span>
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
