import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../../lib/api'
import { qk } from '../../lib/queryKeys'
import { useAuth } from '../../lib/auth'
import type { SessionOut, TotpSetupResponse } from '../../lib/types'
import { Card, CardHeader } from '../Card'
import { Button } from '../Button'
import { Badge } from '../Badge'
import { Input } from '../Field'
import { Icon } from '../Icon'
import { SkeletonRows } from '../Skeleton'
import { useToast } from '../../lib/toast'
import { fmtRelative } from '../../lib/format'

function ChangePassword() {
  const { push } = useToast()
  const [cur, setCur] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')

  const save = useMutation({
    mutationFn: () => api.post('/api/auth/change-password', { current_password: cur, new_password: next }),
    onSuccess: () => {
      push({ title: 'Password changed', tone: 'success' })
      setCur('')
      setNext('')
      setConfirm('')
    },
    onError: (e) => push({ title: 'Could not change password', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })

  const mismatch = confirm !== '' && next !== confirm
  return (
    <Card>
      <CardHeader title="Password" icon={<Icon name="lock" />} />
      <div className="grid gap-4 sm:max-w-md">
        <Input label="Current password" type="password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} />
        <Input label="New password" type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} hint="At least 8 characters." />
        <Input label="Confirm new password" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} error={mismatch ? 'Passwords do not match' : undefined} />
        <div>
          <Button variant="primary" loading={save.isPending} disabled={!cur || next.length < 8 || mismatch} onClick={() => save.mutate()}>
            Update password
          </Button>
        </div>
      </div>
    </Card>
  )
}

function TotpSetup() {
  const { user, refreshUser } = useAuth()
  const { push } = useToast()
  const [setup, setSetup] = useState<TotpSetupResponse | null>(null)
  const [code, setCode] = useState('')

  const begin = useMutation({
    mutationFn: () => api.post<TotpSetupResponse>('/api/auth/totp/setup'),
    onSuccess: (res) => setSetup(res),
    onError: (e) => push({ title: 'Could not start setup', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })
  const enable = useMutation({
    mutationFn: () => api.post('/api/auth/totp/enable', { code: code.trim() }),
    onSuccess: async () => {
      await refreshUser()
      setSetup(null)
      setCode('')
      push({ title: 'Two-factor enabled', tone: 'success' })
    },
    onError: (e) => push({ title: 'Invalid code', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })
  const disable = useMutation({
    mutationFn: () => api.post('/api/auth/totp/disable', { code: code.trim() }),
    onSuccess: async () => {
      await refreshUser()
      setCode('')
      push({ title: 'Two-factor disabled', tone: 'info' })
    },
    onError: (e) => push({ title: 'Invalid code', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })

  return (
    <Card>
      <CardHeader
        title="Two-factor authentication"
        subtitle="Add a time-based one-time code to your login"
        icon={<Icon name="shield" />}
        action={user?.totp_enabled ? <Badge tone="success" dot>Enabled</Badge> : <Badge tone="neutral">Off</Badge>}
      />

      {user?.totp_enabled ? (
        <div className="sm:max-w-md">
          <p className="mb-3 text-sm text-neutral-500 dark:text-neutral-400">Enter a current code from your authenticator to turn 2FA off.</p>
          <div className="flex items-end gap-2">
            <Input label="Authenticator code" inputMode="numeric" value={code} onChange={(e) => setCode(e.target.value.replace(/[^0-9]/g, ''))} placeholder="123456" className="max-w-[160px]" />
            <Button variant="danger" loading={disable.isPending} disabled={code.length < 6} onClick={() => disable.mutate()}>
              Disable 2FA
            </Button>
          </div>
        </div>
      ) : setup ? (
        <div className="grid gap-5 sm:grid-cols-[auto,1fr]">
          <div className="flex justify-center">
            <div className="rounded-xl border border-neutral-200 bg-white p-3 [&_svg]:h-40 [&_svg]:w-40 dark:border-neutral-700" dangerouslySetInnerHTML={{ __html: setup.qr_svg }} />
          </div>
          <div>
            <p className="text-sm text-neutral-600 dark:text-neutral-300">Scan the QR code with your authenticator app, or enter the secret manually:</p>
            <code className="mt-2 block break-all rounded-lg bg-neutral-100 px-3 py-2 font-mono text-xs dark:bg-neutral-800">{setup.secret}</code>
            <div className="mt-4 flex items-end gap-2">
              <Input label="Enter code to confirm" inputMode="numeric" value={code} onChange={(e) => setCode(e.target.value.replace(/[^0-9]/g, ''))} placeholder="123456" className="max-w-[160px]" />
              <Button variant="primary" loading={enable.isPending} disabled={code.length < 6} onClick={() => enable.mutate()}>
                Verify & enable
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <Button variant="secondary" icon="key" loading={begin.isPending} onClick={() => begin.mutate()}>
          Set up two-factor
        </Button>
      )}
    </Card>
  )
}

function Sessions() {
  const queryClient = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: qk.sessions,
    queryFn: () => api.get<SessionOut[]>('/api/auth/sessions'),
  })
  const revoke = useMutation({
    mutationFn: (id: number) => api.del(`/api/auth/sessions/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.sessions }),
  })

  return (
    <Card>
      <CardHeader title="Active sessions" subtitle="Browsers signed in to your account" icon={<Icon name="monitor" />} />
      {isLoading ? (
        <SkeletonRows rows={2} />
      ) : (
        <ul className="space-y-2">
          {(data ?? []).map((sess) => (
            <li key={sess.id} className="flex items-center gap-3 rounded-xl border border-neutral-200 p-3 dark:border-neutral-800">
              <Icon name="monitor" className="h-5 w-5 text-neutral-400" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="truncate text-sm font-medium text-neutral-800 dark:text-neutral-200">{sess.user_agent || 'Unknown device'}</p>
                  {sess.current ? <Badge tone="accent">This device</Badge> : null}
                </div>
                <p className="text-xs text-neutral-400">
                  {sess.ip || '—'} · active {fmtRelative(sess.last_seen_at)}
                </p>
              </div>
              {!sess.current ? (
                <Button size="sm" variant="ghost" onClick={() => revoke.mutate(sess.id)}>
                  Revoke
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

export function SecuritySection() {
  return (
    <div className="space-y-5">
      <ChangePassword />
      <TotpSetup />
      <Sessions />
    </div>
  )
}
