import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { Button } from '../../components/Button'
import { Eyebrow } from '../../components/Eyebrow'
import { Field } from '../../components/Field'
import { SplitHeadline } from '../../components/SplitHeadline'
import { useAuth } from './AuthContext'

const MIN_PASSWORD_LENGTH = 8

interface FieldReason {
  field: string
  message: string
}

/** A 422 carries the real reason per field; the top-level message is generic.
 *  Read it structurally rather than by instanceof, so the shape is all that
 *  matters and the module boundary cannot break the check. */
function fieldReasons(error: unknown): FieldReason[] {
  const fields = (error as { fields?: unknown })?.fields
  if (!Array.isArray(fields)) return []
  return fields.filter(
    (entry): entry is FieldReason =>
      typeof entry?.field === 'string' && typeof entry?.message === 'string',
  )
}

const COPY = {
  login: {
    eyebrow: 'Sign in',
    lead: 'Welcome back.',
    trail: 'Your projects are where you left them.',
    submit: 'Sign in',
    switchText: 'No account yet?',
    switchLabel: 'Create one',
    switchTo: '/register',
  },
  register: {
    eyebrow: 'Create account',
    lead: 'Ask your database a question.',
    trail: 'It answers in SQL you can actually read.',
    submit: 'Create account',
    switchText: 'Already have an account?',
    switchLabel: 'Sign in',
    switchTo: '/login',
  },
} as const

export function AuthForm({ mode }: { mode: 'login' | 'register' }) {
  const copy = COPY[mode]
  const { login, register } = useAuth()
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [emailError, setEmailError] = useState('')
  const [passwordError, setPasswordError] = useState('')
  const [formError, setFormError] = useState('')
  const [busy, setBusy] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setFormError('')
    setEmailError('')
    setPasswordError('')

    if (mode === 'register' && password.length < MIN_PASSWORD_LENGTH) {
      setPasswordError(`Use at least ${MIN_PASSWORD_LENGTH} characters.`)
      return
    }

    setBusy(true)
    try {
      if (mode === 'login') await login(email, password)
      else await register(email, password)
      navigate('/projects', { replace: true })
    } catch (error) {
      const reasons = fieldReasons(error)
      const emailReason = reasons.find((reason) => reason.field === 'email')
      const passwordReason = reasons.find((reason) => reason.field === 'password')

      if (emailReason) setEmailError(emailReason.message)
      if (passwordReason) setPasswordError(passwordReason.message)
      if (!emailReason && !passwordReason) {
        setFormError(
          error instanceof Error ? error.message : 'Something went wrong. Try again.',
        )
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-[440px] flex-col justify-center px-6 py-24">
      <Eyebrow>{copy.eyebrow}</Eyebrow>

      <div className="mt-8">
        <SplitHeadline as="h2" lead={copy.lead} trail={copy.trail} />
      </div>

      <form onSubmit={handleSubmit} className="mt-12 flex flex-col gap-6" noValidate>
        <Field
          id="email"
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={email}
          error={emailError}
          onChange={(event) => setEmail(event.target.value)}
        />
        <Field
          id="password"
          label="Password"
          type="password"
          autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
          required
          value={password}
          error={passwordError}
          onChange={(event) => setPassword(event.target.value)}
        />

        {formError ? (
          <p role="alert" className="text-small text-text-primary">
            {formError}
          </p>
        ) : null}

        <Button type="submit" disabled={busy}>
          {busy ? 'Working…' : copy.submit}
        </Button>
      </form>

      <p className="mt-8 text-small text-text-secondary">
        {copy.switchText}{' '}
        <Link
          to={copy.switchTo}
          className="text-text-primary underline underline-offset-4"
        >
          {copy.switchLabel}
        </Link>
      </p>
    </main>
  )
}
