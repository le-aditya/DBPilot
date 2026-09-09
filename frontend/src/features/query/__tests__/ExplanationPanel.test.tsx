import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { ExplanationPanel, segmentSql } from '../ExplanationPanel'

const SQL = 'SELECT name FROM people WHERE id = 1'

const CLAUSES = [
  { clause: 'SELECT name', text: 'picks the name column', start: 0, end: 11 },
  { clause: 'WHERE id = 1', text: 'keeps one row', start: 24, end: 36 },
]

describe('segmentSql', () => {
  it('covers the whole statement with no text lost', () => {
    const segments = segmentSql(SQL, CLAUSES)

    expect(segments.map((s) => s.text).join('')).toBe(SQL)
  })

  it('marks each clause span with its index', () => {
    const segments = segmentSql(SQL, CLAUSES)

    const selected = segments.filter((s) => s.index !== null)
    expect(selected.map((s) => s.text)).toEqual(['SELECT name', 'WHERE id = 1'])
  })

  it('drops a span that runs past the end of the SQL', () => {
    const segments = segmentSql(SQL, [
      { clause: 'x', text: 'y', start: 10, end: 900 },
    ])

    expect(segments.map((s) => s.text).join('')).toBe(SQL)
    expect(segments.every((s) => s.index === null)).toBe(true)
  })

  it('drops a zeroed span rather than highlighting the first character', () => {
    const segments = segmentSql(SQL, [{ clause: 'x', text: 'y', start: 0, end: 0 }])

    expect(segments.every((s) => s.index === null)).toBe(true)
  })

  it('keeps the earlier of two overlapping spans instead of duplicating text', () => {
    const segments = segmentSql(SQL, [
      { clause: 'a', text: '1', start: 0, end: 11 },
      { clause: 'b', text: '2', start: 5, end: 20 },
    ])

    expect(segments.map((s) => s.text).join('')).toBe(SQL)
  })
})

describe('ExplanationPanel', () => {
  it('shows the summary and every clause', () => {
    render(<ExplanationPanel sql={SQL} summary="Finds one person." clauses={CLAUSES} />)

    expect(screen.getByText('Finds one person.')).toBeInTheDocument()
    expect(screen.getByText('picks the name column')).toBeInTheDocument()
  })

  it('highlights the matching clause on hover', async () => {
    // PRD F6: hovering an explanation highlights the code it describes.
    render(<ExplanationPanel sql={SQL} summary="s" clauses={CLAUSES} />)

    await userEvent.hover(screen.getByLabelText('WHERE id = 1'))

    const highlighted = document.querySelectorAll('[data-highlighted="true"]')
    expect(highlighted).toHaveLength(1)
    expect(highlighted[0].textContent).toBe('WHERE id = 1')
  })

  it('highlights on keyboard focus too', async () => {
    render(<ExplanationPanel sql={SQL} summary="s" clauses={CLAUSES} />)

    await userEvent.tab()

    expect(document.querySelector('[data-highlighted="true"]')?.textContent).toBe(
      'SELECT name',
    )
  })

  it('stops highlighting when the pointer leaves', async () => {
    render(<ExplanationPanel sql={SQL} summary="s" clauses={CLAUSES} />)
    const item = screen.getByLabelText('WHERE id = 1')

    await userEvent.hover(item)
    await userEvent.unhover(item)

    expect(document.querySelectorAll('[data-highlighted="true"]')).toHaveLength(0)
  })

  it('says the query is already efficient when optimisation found nothing', () => {
    render(
      <ExplanationPanel sql={SQL} summary="Fast." clauses={[]} variant="optimize" />,
    )

    expect(screen.getByText(/already efficient/i)).toBeInTheDocument()
  })
})
