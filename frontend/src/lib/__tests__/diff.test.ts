import { describe, expect, it } from 'vitest'

import { diffLines, diffSummary } from '../diff'

describe('diffLines', () => {
  it('marks identical text as unchanged', () => {
    const lines = diffLines('SELECT 1\n', 'SELECT 1\n')

    expect(lines).toEqual([
      { kind: 'same', text: 'SELECT 1', before: 1, after: 1 },
      { kind: 'same', text: '', before: 2, after: 2 },
    ])
  })

  it('reports a changed line as one removal and one addition', () => {
    const lines = diffLines('SELECT name FROM people', 'SELECT email FROM people')

    const changed = lines.filter((line) => line.kind !== 'same')
    expect(changed).toEqual([
      { kind: 'removed', text: 'SELECT name FROM people', before: 1, after: null },
      { kind: 'added', text: 'SELECT email FROM people', before: null, after: 1 },
    ])
  })

  it('keeps the unchanged context when a line is inserted', () => {
    const lines = diffLines(
      'SELECT name\nFROM people\nLIMIT 10',
      "SELECT name\nFROM people\nWHERE region = 'EU'\nLIMIT 10",
    )

    expect(lines.map((line) => line.kind)).toEqual([
      'same',
      'same',
      'added',
      'same',
    ])
    expect(lines[2]).toMatchObject({
      kind: 'added',
      text: "WHERE region = 'EU'",
      after: 3,
    })
  })

  it('numbers the two sides independently', () => {
    const lines = diffLines('a\nb\nc', 'a\nc')

    expect(lines).toEqual([
      { kind: 'same', text: 'a', before: 1, after: 1 },
      { kind: 'removed', text: 'b', before: 2, after: null },
      { kind: 'same', text: 'c', before: 3, after: 2 },
    ])
  })

  it('counts additions and removals for the summary chips', () => {
    const lines = diffLines('a\nb', 'a\nc\nd')

    expect(diffSummary(lines)).toEqual({ added: 2, removed: 1 })
  })
})
