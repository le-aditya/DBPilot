export type DiffKind = 'same' | 'added' | 'removed'

export interface DiffLine {
  kind: DiffKind
  text: string
  /** 1-based line number in the older text, for unchanged and removed lines. */
  before: number | null
  /** 1-based line number in the newer text, for unchanged and added lines. */
  after: number | null
}

/**
 * A line-level diff, smallest edit first.
 *
 * This is the classic longest-common-subsequence table. SQL templates are
 * tens of lines, so the O(n·m) table is cheap and exact; no token-level diff
 * library is needed for something this small.
 *
 * Blank lines are compared as-is. Collapsing them would make two templates with
 * different spacing look identical, which is precisely the kind of edit someone
 * checking a saved query wants to see.
 */
export function diffLines(before: string, after: string): DiffLine[] {
  const oldLines = before.split(/\r?\n/)
  const newLines = after.split(/\r?\n/)

  // lengths[i][j] = LCS length of oldLines[i:] and newLines[j:].
  const lengths: number[][] = Array.from({ length: oldLines.length + 1 }, () =>
    new Array<number>(newLines.length + 1).fill(0),
  )

  for (let i = oldLines.length - 1; i >= 0; i -= 1) {
    for (let j = newLines.length - 1; j >= 0; j -= 1) {
      lengths[i][j] =
        oldLines[i] === newLines[j]
          ? lengths[i + 1][j + 1] + 1
          : Math.max(lengths[i + 1][j], lengths[i][j + 1])
    }
  }

  const lines: DiffLine[] = []
  let i = 0
  let j = 0
  let oldNumber = 1
  let newNumber = 1

  while (i < oldLines.length && j < newLines.length) {
    if (oldLines[i] === newLines[j]) {
      lines.push({
        kind: 'same',
        text: oldLines[i],
        before: oldNumber,
        after: newNumber,
      })
      i += 1
      j += 1
      oldNumber += 1
      newNumber += 1
    } else if (lengths[i + 1][j] >= lengths[i][j + 1]) {
      lines.push({ kind: 'removed', text: oldLines[i], before: oldNumber, after: null })
      i += 1
      oldNumber += 1
    } else {
      lines.push({ kind: 'added', text: newLines[j], before: null, after: newNumber })
      j += 1
      newNumber += 1
    }
  }

  for (; i < oldLines.length; i += 1) {
    lines.push({ kind: 'removed', text: oldLines[i], before: oldNumber, after: null })
    oldNumber += 1
  }
  for (; j < newLines.length; j += 1) {
    lines.push({ kind: 'added', text: newLines[j], before: null, after: newNumber })
    newNumber += 1
  }

  return lines
}

/** Counts for the "2 added, 1 removed" summary above a diff. */
export function diffSummary(lines: DiffLine[]): { added: number; removed: number } {
  return lines.reduce(
    (totals, line) => {
      if (line.kind === 'added') totals.added += 1
      if (line.kind === 'removed') totals.removed += 1
      return totals
    },
    { added: 0, removed: 0 },
  )
}
