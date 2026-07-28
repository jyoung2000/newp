import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api, ApiError } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { Card, CardHeader } from '../Card'
import { Button } from '../Button'
import { Input } from '../Field'
import { Modal } from '../Modal'
import { Icon } from '../Icon'
import { useToast } from '../../lib/toast'

export function DangerSection() {
  const { logout } = useAuth()
  const { push } = useToast()
  const [open, setOpen] = useState(false)
  const [confirm, setConfirm] = useState('')

  const del = useMutation({
    mutationFn: () => api.del('/api/auth/account'),
    onSuccess: async () => {
      push({ title: 'Account deleted', tone: 'info' })
      await logout()
    },
    onError: (e) => push({ title: 'Could not delete account', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })

  return (
    <Card className="border-red-200 dark:border-red-500/30">
      <CardHeader title="Delete account" subtitle="Permanently remove your account and all data" icon={<Icon name="alert" />} />
      <p className="mb-4 text-sm text-neutral-600 dark:text-neutral-300">
        This deletes your profile, files, listings, applications and answers from this server. It cannot be undone.
      </p>
      <Button variant="danger" icon="trash" onClick={() => setOpen(true)}>
        Delete my account
      </Button>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Delete account?"
        description="This permanently erases everything. Type DELETE to confirm."
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button variant="danger" icon="trash" loading={del.isPending} disabled={confirm !== 'DELETE'} onClick={() => del.mutate()}>
              Permanently delete
            </Button>
          </>
        }
      >
        <Input label="Type DELETE to confirm" value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="DELETE" />
      </Modal>
    </Card>
  )
}
