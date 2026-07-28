import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../../lib/api'
import { qk } from '../../lib/queryKeys'
import type { RecommendationIn, RecommendationOut } from '../../lib/types'
import { Card } from '../Card'
import { Button } from '../Button'
import { Input } from '../Field'
import { Modal } from '../Modal'
import { Icon } from '../Icon'
import { EmptyState } from '../EmptyState'
import { useToast } from '../../lib/toast'

const EMPTY: RecommendationIn = { name: '', title: null, relationship_to_user: null, contact: null, text: null, file_id: null }

function RecModal({ open, initial, editId, onClose }: { open: boolean; initial: RecommendationIn; editId: number | null; onClose: () => void }) {
  const queryClient = useQueryClient()
  const { push } = useToast()
  const [form, setForm] = useState<RecommendationIn>(initial)

  const save = useMutation({
    mutationFn: () =>
      editId
        ? api.put<RecommendationOut>(`/api/profile/recommendations/${editId}`, form)
        : api.post<RecommendationOut>('/api/profile/recommendations', form),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.profile })
      push({ title: editId ? 'Updated' : 'Added', tone: 'success' })
      onClose()
    },
    onError: (e) => push({ title: 'Could not save', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={editId ? 'Edit reference' : 'Add reference'}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" loading={save.isPending} onClick={() => save.mutate()} disabled={!form.name}>
            Save
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Input label="Name" required value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
          <Input label="Title" value={form.title ?? ''} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value || null }))} />
          <Input label="Relationship" value={form.relationship_to_user ?? ''} onChange={(e) => setForm((f) => ({ ...f, relationship_to_user: e.target.value || null }))} placeholder="e.g. Former manager" />
          <Input label="Contact" value={form.contact ?? ''} onChange={(e) => setForm((f) => ({ ...f, contact: e.target.value || null }))} placeholder="Email or phone" />
        </div>
        <div>
          <label className="label">Recommendation text</label>
          <textarea className="input min-h-[90px]" value={form.text ?? ''} onChange={(e) => setForm((f) => ({ ...f, text: e.target.value || null }))} />
        </div>
      </div>
    </Modal>
  )
}

export function RecommendationsTab({ items }: { items: RecommendationOut[] }) {
  const queryClient = useQueryClient()
  const [modal, setModal] = useState<{ open: boolean; initial: RecommendationIn; editId: number | null }>({ open: false, initial: EMPTY, editId: null })

  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/api/profile/recommendations/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.profile }),
  })

  return (
    <div>
      <div className="mb-4 flex items-center justify-end">
        <Button variant="primary" size="sm" icon="plus" onClick={() => setModal({ open: true, initial: EMPTY, editId: null })}>
          Add reference
        </Button>
      </div>
      {items.length === 0 ? (
        <EmptyState icon="user" title="No references yet" description="Add people who can vouch for you." />
      ) : (
        <ul className="space-y-3">
          {items.map((r) => (
            <li key={r.id}>
              <Card padded={false} className="flex items-start gap-3 p-4">
                <div className="min-w-0 flex-1">
                  <h4 className="font-semibold text-neutral-900 dark:text-neutral-100">{r.name}</h4>
                  <p className="text-sm text-neutral-600 dark:text-neutral-300">
                    {[r.title, r.relationship_to_user].filter(Boolean).join(' · ') || '—'}
                  </p>
                  {r.contact ? <p className="mt-0.5 text-xs text-neutral-400">{r.contact}</p> : null}
                  {r.text ? <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-300">“{r.text}”</p> : null}
                </div>
                <div className="flex shrink-0 gap-1">
                  <button
                    onClick={() => setModal({ open: true, editId: r.id, initial: { name: r.name, title: r.title ?? null, relationship_to_user: r.relationship_to_user ?? null, contact: r.contact ?? null, text: r.text ?? null, file_id: r.file_id ?? null } })}
                    className="rounded-lg p-2 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700 dark:hover:bg-neutral-800"
                    aria-label="Edit"
                  >
                    <Icon name="edit" className="h-4 w-4" />
                  </button>
                  <button onClick={() => remove.mutate(r.id)} className="rounded-lg p-2 text-neutral-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-500/10" aria-label="Delete">
                    <Icon name="trash" className="h-4 w-4" />
                  </button>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
      <RecModal key={`${modal.editId}-${modal.open}`} open={modal.open} initial={modal.initial} editId={modal.editId} onClose={() => setModal((m) => ({ ...m, open: false }))} />
    </div>
  )
}
