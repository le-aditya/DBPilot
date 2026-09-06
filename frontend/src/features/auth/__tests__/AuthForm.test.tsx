import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthForm } from '../AuthForm'

const login = vi.fn()
const register = vi.fn()

vi.mock('../AuthContext', () => ({
  useAuth: () => ({
    user: null,
    status: 'anonymous',
    login,
    register,
    signOut: vi.fn(),
  }),
}))

function renderForm(mode: 'login' | 'register') {
  return render(
    <MemoryRouter>
      <AuthForm mode={mode} />
    </MemoryRouter>,
  )
}

describe('AuthForm', () => {
  beforeEach(() => {
    login.mockReset().mockResolvedValue(undefined)
    register.mockReset().mockResolvedValue(undefined)
  })

  it('labels every input, so the form is usable by keyboard and screen reader', () => {
    renderForm('login')

    expect(screen.getByLabelText(/email/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
  })

  it('submits the credentials on login', async () => {
    renderForm('login')
    await userEvent.type(screen.getByLabelText(/email/i), 'ada@example.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'a-good-password')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() =>
      expect(login).toHaveBeenCalledWith('ada@example.com', 'a-good-password'),
    )
  })

  it('calls register in register mode', async () => {
    renderForm('register')
    await userEvent.type(screen.getByLabelText(/email/i), 'ada@example.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'a-good-password')
    await userEvent.click(screen.getByRole('button', { name: /create account/i }))

    await waitFor(() =>
      expect(register).toHaveBeenCalledWith('ada@example.com', 'a-good-password'),
    )
  })

  it('rejects a short password before calling the API', async () => {
    renderForm('register')
    await userEvent.type(screen.getByLabelText(/email/i), 'ada@example.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'short')
    await userEvent.click(screen.getByRole('button', { name: /create account/i }))

    expect(await screen.findByText(/at least 8 characters/i)).toBeInTheDocument()
    expect(register).not.toHaveBeenCalled()
  })

  it('shows the server message when sign-in fails', async () => {
    login.mockRejectedValue(
      Object.assign(
        new Error('That email and password combination is not correct.'),
        { status: 401, code: 'unauthorized' },
      ),
    )
    renderForm('login')
    await userEvent.type(screen.getByLabelText(/email/i), 'ada@example.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'a-good-password')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByText(/combination is not correct/i)).toBeInTheDocument()
  })

  it('shows the field-level reason next to the offending input', async () => {
    // A generic "request body was not valid" tells the user nothing about
    // what to change. PRD section 9: say what happened and what to do next.
    register.mockRejectedValue(
      Object.assign(new Error('The request body was not valid.'), {
        status: 422,
        code: 'validation_error',
        fields: [
          {
            field: 'email',
            message: 'The part after the @-sign is a reserved name.',
          },
        ],
      }),
    )
    renderForm('register')
    await userEvent.type(screen.getByLabelText(/email/i), 'ada@dbpilot.test')
    await userEvent.type(screen.getByLabelText(/password/i), 'a-good-password')
    await userEvent.click(screen.getByRole('button', { name: /create account/i }))

    expect(await screen.findByText(/reserved name/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/email/i)).toHaveAttribute('aria-invalid', 'true')
    expect(screen.queryByText(/request body was not valid/i)).not.toBeInTheDocument()
  })

  it('announces errors to assistive technology', async () => {
    renderForm('register')
    await userEvent.type(screen.getByLabelText(/email/i), 'ada@example.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'short')
    await userEvent.click(screen.getByRole('button', { name: /create account/i }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })
})
