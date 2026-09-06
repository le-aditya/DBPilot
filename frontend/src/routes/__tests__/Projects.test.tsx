import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Projects } from '../Projects'

const apiFetch = vi.fn()

vi.mock('../../lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
  ApiError: class extends Error {},
}))

vi.mock('../../features/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'ada@example.com' },
    status: 'authenticated',
    login: vi.fn(),
    register: vi.fn(),
    signOut: vi.fn(),
  }),
}))

const SALES = {
  id: 1,
  name: 'Sales',
  source_type: 'upload',
  schema_name: null,
  table_count: 3,
  is_demo: false,
  created_at: '2026-09-06T12:00:00Z',
}

function renderProjects() {
  return render(
    <MemoryRouter>
      <Projects />
    </MemoryRouter>,
  )
}

describe('Projects', () => {
  beforeEach(() => {
    apiFetch.mockReset()
  })

  it('invites a first project when the list is empty', async () => {
    apiFetch.mockResolvedValue([])
    renderProjects()

    // PRD 10.9: empty states are invitations, not apologies.
    expect(await screen.findByText(/no projects yet/i)).toBeInTheDocument()
  })

  it('lists the projects it loaded', async () => {
    apiFetch.mockResolvedValue([SALES])
    renderProjects()

    expect(await screen.findByText('Sales')).toBeInTheDocument()
  })

  it('creates a project and shows it without a reload', async () => {
    apiFetch
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce({ ...SALES, id: 2, name: 'Inventory', table_count: null })
    renderProjects()
    await screen.findByText(/no projects yet/i)

    await userEvent.type(screen.getByLabelText(/project name/i), 'Inventory')
    await userEvent.click(screen.getByRole('button', { name: /create project/i }))

    expect(await screen.findByText('Inventory')).toBeInTheDocument()
  })

  it('shows the server message when creation is refused', async () => {
    apiFetch
      .mockResolvedValueOnce([])
      .mockRejectedValueOnce(new Error("You already have a project called 'Sales'."))
    renderProjects()
    await screen.findByText(/no projects yet/i)

    await userEvent.type(screen.getByLabelText(/project name/i), 'Sales')
    await userEvent.click(screen.getByRole('button', { name: /create project/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /already have a project/i,
    )
  })

  it('removes a project from the list after deleting it', async () => {
    apiFetch.mockResolvedValueOnce([SALES]).mockResolvedValueOnce(null)
    renderProjects()
    await screen.findByText('Sales')

    await userEvent.click(screen.getByRole('button', { name: /delete sales/i }))

    await waitFor(() => expect(screen.queryByText('Sales')).not.toBeInTheDocument())
  })
})
