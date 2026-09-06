import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Eyebrow } from '../Eyebrow'
import { SplitHeadline } from '../SplitHeadline'

describe('Eyebrow', () => {
  it('renders its label', () => {
    render(<Eyebrow>Schema explorer</Eyebrow>)

    expect(screen.getByText('Schema explorer')).toBeInTheDocument()
  })

  it('carries the lime dot the PRD requires before the label', () => {
    const { container } = render(<Eyebrow>Dashboard</Eyebrow>)

    expect(container.querySelector('[data-accent-dot]')).not.toBeNull()
  })

  it('hides the decorative dot from assistive technology', () => {
    const { container } = render(<Eyebrow>History</Eyebrow>)

    expect(container.querySelector('[data-accent-dot]')).toHaveAttribute(
      'aria-hidden',
      'true',
    )
  })
})

describe('SplitHeadline', () => {
  it('renders the lead clause in primary text and the trail in secondary', () => {
    render(
      <SplitHeadline
        lead="Ask your database a question."
        trail="It answers in SQL you can actually read."
      />,
    )

    expect(screen.getByText('Ask your database a question.')).toHaveClass(
      'text-text-primary',
    )
    expect(
      screen.getByText('It answers in SQL you can actually read.'),
    ).toHaveClass('text-text-secondary')
  })

  it('renders as the requested heading level', () => {
    render(<SplitHeadline as="h2" lead="Lead" trail="Trail" />)

    expect(screen.getByRole('heading', { level: 2 })).toBeInTheDocument()
  })

  it('defaults to h1 so a page has one top-level heading', () => {
    render(<SplitHeadline lead="Lead" trail="Trail" />)

    expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument()
  })
})
