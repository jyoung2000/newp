import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../lib/api'
import { qk } from '../lib/queryKeys'
import { useAuth } from '../lib/auth'
import type { AdminUserOut } from '../lib/types'
import { PageHeader } from '../components/PageHeader'
import { Card, CardHeader } from '../components/Card'
import { Button } from '../components/Button'
import { Badge } from '../components/Badge'
import { Input } from '../components/Field'
import { Icon } from '../components/Icon'
import { Modal } from '../components/Modal'
import { SkeletonRows } from '../components/Skeleton'
import { EmptyState } from '../components/EmptyState'
import { useToast } from '../lib/toast'
import { fmtRelative } from '../lib/format'

function detail(e: unknown): string {
  return e instanceof ApiError ? e.detail : ''
}

function AddUser() {
  const { push } = useToast()
  const qc = useQueryClient()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [isAdmin, setIsAdmin] = useState(false)

  const create = useMutation({
    mutationFn: () =>
      api.post<AdminUserOut>('/api/users', { email, password, is_admin: isAdmin }),
    onSuccess: async (row) => {
      await qc.invalidateQueries({ queryKey: qk.users })
      push({ title: `Created ${row.email}`, tone: 'success' })
      setEmail('')
      setPassword('')
      setIsAdmin(false)
    },
    onError: (e) => push({ title: 'Could not create account', tone: 'error', message: detail(e) }),
  })

  return (
    <Card>
      <CardHeader
        title="Add an account"
        icon={<Icon name="plus" />}
        subtitle="They can change this password once they sign in."
      />
      <div className="grid gap-4 sm:max-w-md">
        <Input
          label="Email"
          type="email"
          autoComplete="off"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <Input
          label="Temporary password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          hint="At least 10 characters."
        />
        <label className="flex items-center gap-2 text-sm text-neutral-700 dark:text-neutral-300">
          <input
            type="checkbox"
            className="h-4 w-4 rounded border-neutral-300 text-accent-600"
            checked={isAdmin}
            onChange={(e) => setIsAdmin(e.target.checked)}
          />
          Make this account an administrator
        </label>
        <div>
          <Button
            variant="primary"
            loading={create.isPending}
            disabled={!email || password.length < 10}
            onClick={() => create.mutate()}
          >
            Create account
          </Button>
        </div>
      </div>
    </Card>
  )
}

function ResetPassword({ user, onDone }: { user: AdminUserOut; onDone: () => void }) {
  const { push } = useToast()
  const [next, setNext] = useState('')

  const reset = useMutation({
    mutationFn: () => api.post(`/api/users/${user.id}/password`, { new_password: next }),
    onSuccess: () => {
      push({
        title: `Password reset for ${user.email}`,
        tone: 'success',
        message: 'Their other sessions were signed out.',
      })
      onDone()
    },
    onError: (e) => push({ title: 'Could not reset password', tone: 'error', message: detail(e) }),
  })

  return (
    <Modal open title={`Reset password — ${user.email}`} onClose={onDone}>
      <div className="grid gap-4">
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          Sets a new password without needing the old one. Every session this account currently has
          is signed out.
        </p>
        <Input
          label="New password"
          type="password"
          autoComplete="new-password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          hint="At least 10 characters."
        />
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onDone}>
            Cancel
          </Button>
          <Button
            variant="primary"
            loading={reset.isPending}
            disabled={next.length < 10}
            onClick={() => reset.mutate()}
          >
            Reset password
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function DeleteUser({ user, onDone }: { user: AdminUserOut; onDone: () => void }) {
  const { push } = useToast()
  const qc = useQueryClient()
  const [confirm, setConfirm] = useState('')

  const remove = useMutation({
    mutationFn: () => api.del(`/api/users/${user.id}`),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.users })
      push({ title: `Deleted ${user.email}`, tone: 'info' })
      onDone()
    },
    onError: (e) => push({ title: 'Could not delete account', tone: 'error', message: detail(e) }),
  })

  return (
    <Modal open title={`Delete ${user.email}?`} onClose={onDone}>
      <div className="grid gap-4">
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          This removes the account and everything in it — profile, listings, applications and
          uploaded files. It cannot be undone.
        </p>
        <Input
          label={`Type the email to confirm`}
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          placeholder={user.email}
        />
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onDone}>
            Cancel
          </Button>
          <Button
            variant="danger"
            loading={remove.isPending}
            disabled={confirm !== user.email}
            onClick={() => remove.mutate()}
          >
            Delete account
          </Button>
        </div>
      </div>
    </Modal>
  )
}

interface UserRowProps {
  user: AdminUserOut
  adminCount: number
  onReset: (user: AdminUserOut) => void
  onDelete: (user: AdminUserOut) => void
}

function UserRow({ user, adminCount, onReset, onDelete }: UserRowProps) {
  const { push } = useToast()
  const qc = useQueryClient()

  const role = useMutation({
    mutationFn: (next: boolean) => api.patch(`/api/users/${user.id}`, { is_admin: next }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.users })
      push({ title: `${user.email} updated`, tone: 'success' })
    },
    onError: (e) => push({ title: 'Could not change role', tone: 'error', message: detail(e) }),
  })

  // Mirror the server's rules so the buttons that cannot succeed are visibly
  // unavailable, with the reason, rather than failing on click.
  const lastAdmin = user.is_admin && adminCount <= 1
  const demoteBlocked = lastAdmin ? 'The only administrator — promote another account first' : ''
  const deleteBlocked = user.is_self
    ? 'Use Settings → Danger zone for your own account'
    : lastAdmin
      ? 'The only administrator — promote another account first'
      : ''

  return (
    <tr className="border-t border-neutral-200/70 dark:border-neutral-800/70">
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="font-medium text-neutral-900 dark:text-neutral-100">{user.email}</span>
          {user.is_self ? <Badge tone="neutral">You</Badge> : null}
        </div>
        <p className="mt-0.5 text-xs text-neutral-500">
          Joined {fmtRelative(user.created_at)}
          {user.last_seen_at ? ` · last seen ${fmtRelative(user.last_seen_at)}` : ' · never signed in'}
        </p>
      </td>
      <td className="px-4 py-3">
        {user.is_admin ? <Badge tone="accent">Administrator</Badge> : <Badge tone="neutral">Member</Badge>}
      </td>
      <td className="px-4 py-3 text-sm text-neutral-600 dark:text-neutral-400">
        {user.totp_enabled ? (
          <span className="inline-flex items-center gap-1">
            <Icon name="shield" className="h-4 w-4" /> On
          </span>
        ) : (
          'Off'
        )}
      </td>
      <td className="px-4 py-3 text-sm text-neutral-600 dark:text-neutral-400">
        {user.active_sessions}
      </td>
      <td className="px-4 py-3">
        <div className="flex flex-wrap justify-end gap-2">
          <Button
            size="sm"
            variant="ghost"
            loading={role.isPending}
            disabled={!!demoteBlocked}
            title={demoteBlocked || undefined}
            onClick={() => role.mutate(!user.is_admin)}
          >
            {user.is_admin ? 'Revoke admin' : 'Make admin'}
          </Button>
          <Button size="sm" variant="ghost" icon="key" onClick={() => onReset(user)}>
            Reset password
          </Button>
          <Button
            size="sm"
            variant="ghost"
            icon="trash"
            disabled={!!deleteBlocked}
            title={deleteBlocked || undefined}
            onClick={() => onDelete(user)}
          >
            Delete
          </Button>
        </div>
      </td>
    </tr>
  )
}

export function Users() {
  const { user: me } = useAuth()
  // Modals live outside the table: Modal renders inline rather than through a
  // portal, and a <div> is not valid inside a <tr>.
  const [resetTarget, setResetTarget] = useState<AdminUserOut | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<AdminUserOut | null>(null)
  const users = useQuery({
    queryKey: qk.users,
    queryFn: () => api.get<AdminUserOut[]>('/api/users'),
    enabled: !!me?.is_admin,
  })

  // The nav hides this route for non-admins, but a typed URL still lands here.
  if (me && !me.is_admin) {
    return (
      <div>
        <PageHeader title="Users" />
        <EmptyState
          icon="lock"
          title="Administrator access required"
          description="Only an administrator can manage accounts on this install."
        />
      </div>
    )
  }

  const rows = users.data ?? []
  const adminCount = rows.filter((u) => u.is_admin).length

  return (
    <div>
      <PageHeader
        title="Users"
        subtitle="Accounts on this install. Managing an account never opens its job data — that stays private to whoever owns it."
      />

      <div className="grid gap-5">
        <Card padded={false}>
          <div className="px-4 pt-4">
            <CardHeader title="Accounts" icon={<Icon name="user" />} />
          </div>
          {users.isLoading ? (
            <div className="p-4">
              <SkeletonRows rows={3} />
            </div>
          ) : users.isError ? (
            <div className="p-4">
              <EmptyState
                icon="alert"
                title="Could not load accounts"
                description={detail(users.error)}
              />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[46rem] text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wide text-neutral-500">
                    <th className="px-4 py-2 font-medium">Account</th>
                    <th className="px-4 py-2 font-medium">Role</th>
                    <th className="px-4 py-2 font-medium">Two-factor</th>
                    <th className="px-4 py-2 font-medium">Sessions</th>
                    <th className="px-4 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((u) => (
                    <UserRow
                      key={u.id}
                      user={u}
                      adminCount={adminCount}
                      onReset={setResetTarget}
                      onDelete={setDeleteTarget}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <AddUser />
      </div>

      {resetTarget ? (
        <ResetPassword user={resetTarget} onDone={() => setResetTarget(null)} />
      ) : null}
      {deleteTarget ? (
        <DeleteUser user={deleteTarget} onDone={() => setDeleteTarget(null)} />
      ) : null}
    </div>
  )
}
