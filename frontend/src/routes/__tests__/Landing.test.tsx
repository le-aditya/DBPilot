import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { Landing } from '../Landing'

vi.mock('../../features/auth/AuthContext', () => ({
  useAuth: () => ({ status: 'anonymous' }),
}))

function renderLanding() {
  return render(
    <MemoryRouter>
      <Landing />
    </MemoryRouter>,
  )
}

describe('Landing', () => {
  it('explains the product before showing a form', () => {
    renderLanding()

    expect(
      screen.getByRole('heading', { level: 1, name: /ask your database a question/i }),
    ).toBeInTheDocument()
    expect(screen.getByText(/drop in a csv/i)).toBeInTheDocument()
  })

  it('sends a new visitor to registration, not straight to login', () => {
    renderLanding()

    const starts = screen.getAllByRole('link', { name: /start free/i })
    expect(starts.length).toBeGreaterThan(0)
    for (const link of starts) {
      expect(link).toHaveAttribute('href', '/register')
    }
    expect(screen.getByRole('link', { name: /sign in/i })).toHaveAttribute(
      'href',
      '/login',
    )
  })

  it('shows the workspace preview without a checked-in image', () => {
    const { container } = renderLanding()

    expect(container.querySelector('figure')).not.toBeNull()
    expect(screen.getByText(/nothing is hidden/i)).toBeInTheDocument()
  })
})
