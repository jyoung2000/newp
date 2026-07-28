import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../../lib/api'
import { qk } from '../../lib/queryKeys'
import type { EducationIn, EducationOut } from '../../lib/types'
import { Card } from '../Card'
import { Button } from '../Button'
import { Input } from '../Field'
import { Modal } from '../Modal'
import { Icon } from '../Icon'
import { EmptyState } from '../EmptyState'
import { useToast } from '../../lib/toast'
import { fmtDate } from '../../lib/format'

const EMPTY: EducationIn = { school: '', degree: null, field_of_study: null, start_date: null, end_date: null, gpa: null }

function EduModal({ open, initial, editId, onClose }: { open: boolean; initial: EducationIn; editId: number | null; onClose: () => void }) {
  const queryClient = useQueryClient()
  const { push } = useToast()
  const [form, setForm] = useState<EducationIn>(initial)

  const save = useMutation({
    mutationFn: () => {
      const body: EducationIn = { ...form, gpa: form.gpa != null && String(form.gpa) !== '' ? Number(form.gpa) : null }
      return editId
        ? api.put<EducationOut>(`/api/profile/educations/${editId}`, body)
        : api.post<EducationOut>('/api/profile/educations', body)
    },
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
      title={editId ? 'Edit education' : 'Add education'}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" loading={save.isPending} onClick={() => save.mutate()} disabled={!form.school}>
            Save
          </Button>
        </>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Input label="School" required value={form.school} onChange={(e) => setForm((f) => ({ ...f, school: e.target.value }))} className="sm:col-span-2" />
        <Input label="Degree" value={form.degree ?? ''} onChange={(e) => setForm((f) => ({ ...f, degree: e.target.value || null }))} />
        <Input label="Field of study" value={form.field_of_study ?? ''} onChange={(e) => setForm((f) => ({ ...f, field_of_study: e.target.value || null }))} />
        <Input label="Start date" type="date" value={form.start_date ?? ''} onChange={(e) => setForm((f) => ({ ...f, start_date: e.target.value || null }))} />
        <Input label="End date" type="date" value={form.end_date ?? ''} onChange={(e) => setForm((f) => ({ ...f, end_date: e.target.value || null }))} />
        <Input label="GPA" type="number" step="0.01" value={form.gpa ?? ''} onChange={(e) => setForm((f) => ({ ...f, gpa: e.target.value === '' ? null : Number(e.target.value) }))} />
      </div>
    </Modal>
  )
}

export function EducationTab({ items }: { items: EducationOut[] }) {
  const queryClient = useQueryClient()
  const [modal, setModal] = useState<{ open: boolean; initial: EducationIn; editId: number | null }>({ open: false, initial: EMPTY, editId: null })

  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/api/profile/educations/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.profile }),
  })

  return (
    <div>
      <div className="mb-4 flex items-center justify-end">
        <Button variant="primary" size="sm" icon="plus" onClick={() => setModal({ open: true, initial: EMPTY, editId: null })}>
          Add education
        </Button>
      </div>
      {items.length === 0 ? (
        <EmptyState icon="onboarding" title="No education added" description="Add schools and degrees for education questions." />
      ) : (
        <ul className="space-y-3">
          {items.map((e) => (
            <li key={e.id}>
              <Card padded={false} className="flex items-start gap-3 p-4">
                <div className="min-w-0 flex-1">
                  <h4 className="font-semibold text-neutral-900 dark:text-neutral-100">{e.school}</h4>
                  <p className="text-sm text-neutral-600 dark:text-neutral-300">
                    {[e.degree, e.field_of_study].filter(Boolean).join(', ') || '—'}
                  </p>
                  <p className="mt-0.5 text-xs text-neutral-400">
                    {fmtDate(e.start_date)} – {fmtDate(e.end_date)}
                    {e.gpa != null ? ` · GPA ${e.gpa}` : ''}
                  </p>
                </div>
                <div className="flex shrink-0 gap-1">
                  <button
                    onClick={() => setModal({ open: true, editId: e.id, initial: { school: e.school, degree: e.degree ?? null, field_of_study: e.field_of_study ?? null, start_date: e.start_date ?? null, end_date: e.end_date ?? null, gpa: e.gpa ?? null } })}
                    className="rounded-lg p-2 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700 dark:hover:bg-neutral-800"
                    aria-label="Edit"
                  >
                    <Icon name="edit" className="h-4 w-4" />
                  </button>
                  <button onClick={() => remove.mutate(e.id)} className="rounded-lg p-2 text-neutral-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-500/10" aria-label="Delete">
                    <Icon name="trash" className="h-4 w-4" />
                  </button>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
      <EduModal key={`${modal.editId}-${modal.open}`} open={modal.open} initial={modal.initial} editId={modal.editId} onClose={() => setModal((m) => ({ ...m, open: false }))} />
    </div>
  )
}
