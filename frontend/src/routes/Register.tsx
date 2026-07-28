import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { api, ApiError } from '../lib/api'
import type { UserOut } from '../lib/types'
import { AuthShell } from './AuthShell'
import { Input } from '../components/Field'
import { Button } from '../components/Button'
import { Icon } from '../components/Icon'

export function Register() {
  const { status, login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (status === 'authed') return <Navigate to="/" replace />

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (password.length < 8) {
      setError('Use a password of at least 8 characters.')
      return
    }
    if (password !== confirm) {
      setError('Passwords do not match.')
      return
    }
    setBusy(true)
    try {
      await api.post<UserOut>('/api/auth/register', { email, password })
      // Registration succeeds without a session — sign in to get one.
      await login(email, password)
      navigate('/onboarding', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Could not create your account.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell
      title="Create your account"
      subtitle="One account runs your whole job search"
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" className="font-medium text-accent-600 hover:underline dark:text-accent-400">
            Sign in
          </Link>
        </>
      }
    >
      {error ? (
        <div className="mb-4 flex items-start gap-2 rounded-xl bg-red-50 px-3 py-2.5 text-sm text-red-700 ring-1 ring-inset ring-red-200 dark:bg-red-500/10 dark:text-red-300 dark:ring-red-500/25">
          <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      ) : null}
      <form onSubmit={submit} className="space-y-4">
        <Input
          label="Email"
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
        />
        <Input
          label="Password"
          type="password"
          autoComplete="new-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="At least 8 characters"
          hint="Stored hashed on your own server."
        />
        <Input
          label="Confirm password"
          type="password"
          autoComplete="new-password"
          required
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          placeholder="Re-enter password"
        />
        <Button type="submit" variant="primary" block loading={busy} iconRight="arrowRight">
          Create account
        </Button>
      </form>
    </AuthShell>
  )
}
