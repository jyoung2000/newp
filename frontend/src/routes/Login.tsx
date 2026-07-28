import { useEffect, useRef, useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { ApiError } from '../lib/api'
import { AuthShell } from './AuthShell'
import { Input } from '../components/Field'
import { Button } from '../components/Button'
import { Icon } from '../components/Icon'

export function Login() {
  const { status, login, verifyTotp } = useAuth()
  const navigate = useNavigate()
  const [step, setStep] = useState<'credentials' | 'totp'>('credentials')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const codeRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (step === 'totp') codeRef.current?.focus()
  }, [step])

  if (status === 'authed') return <Navigate to="/" replace />

  const submitCredentials = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const { requiresTotp } = await login(email, password)
      if (requiresTotp) setStep('totp')
      else navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Something went wrong. Try again.')
    } finally {
      setBusy(false)
    }
  }

  const submitTotp = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await verifyTotp(code.trim())
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Invalid code. Try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell
      title="Welcome back"
      subtitle="Sign in to your JobPilot workspace"
      footer={
        step === 'credentials' ? (
          <>
            First time here?{' '}
            <Link to="/register" className="font-medium text-accent-600 hover:underline dark:text-accent-400">
              Create your account
            </Link>
          </>
        ) : null
      }
    >
      {error ? (
        <div className="mb-4 flex items-start gap-2 rounded-xl bg-red-50 px-3 py-2.5 text-sm text-red-700 ring-1 ring-inset ring-red-200 dark:bg-red-500/10 dark:text-red-300 dark:ring-red-500/25">
          <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      ) : null}

      {step === 'credentials' ? (
        <form onSubmit={submitCredentials} className="space-y-4">
          <Input
            label="Email"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
          <div className="relative">
            <Input
              label="Password"
              type={showPw ? 'text' : 'password'}
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
            />
            <button
              type="button"
              onClick={() => setShowPw((s) => !s)}
              className="absolute right-2 top-[30px] rounded-lg p-1.5 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300"
              aria-label={showPw ? 'Hide password' : 'Show password'}
            >
              <Icon name={showPw ? 'eyeOff' : 'eye'} className="h-4 w-4" />
            </button>
          </div>
          <Button type="submit" variant="primary" block loading={busy} iconRight="arrowRight">
            Sign in
          </Button>
        </form>
      ) : (
        <form onSubmit={submitTotp} className="space-y-4">
          <div className="flex items-center gap-2 rounded-xl bg-accent-50 px-3 py-2.5 text-sm text-accent-700 ring-1 ring-inset ring-accent-200 dark:bg-accent-500/10 dark:text-accent-300 dark:ring-accent-500/25">
            <Icon name="shield" className="h-4 w-4 shrink-0" />
            Enter the 6-digit code from your authenticator app.
          </div>
          <Input
            ref={codeRef}
            label="Verification code"
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="[0-9]*"
            maxLength={8}
            required
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/[^0-9]/g, ''))}
            placeholder="123456"
            className="text-center text-lg tracking-[0.4em]"
          />
          <Button type="submit" variant="primary" block loading={busy}>
            Verify
          </Button>
          <button
            type="button"
            onClick={() => {
              setStep('credentials')
              setCode('')
              setError(null)
            }}
            className="w-full text-center text-sm text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300"
          >
            Back to sign in
          </button>
        </form>
      )}
    </AuthShell>
  )
}
