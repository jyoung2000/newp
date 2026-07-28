import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../../lib/api'
import { qk } from '../../lib/queryKeys'
import type { WorkExperienceIn, WorkExperienceOut } from '../../lib/types'
import { Card } from '../Card'
import { Button } from '../Button'
import { Badge } from '../Badge'
import { Input } from '../Field'
import { Toggle } from '../Toggle'
import { Modal } from '../Modal'
import { Icon } from '../Icon'
import { EmptyState } from '../EmptyState'
import { useToast } from '../../lib/toast'
import { fmtDate } from '../../lib/format'

const EMPTY: WorkExperienceIn = { title: '', company: '', location: null, start_date: null, end_date: null, is_current: false, bullets: [] }

function WorkModal({
  open,
  initial,
  editId,
  onClose,
}: {
  open: boolean
  initial: WorkExperienceIn
  editId: number | null
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const { push } = useToast()
  const [form, setForm] = useState<WorkExperienceIn>(initial)
  const [bullets, setBullets] = useState((initial.bullets ?? []).join('\n'))

  const save = useMutation({
    mutationFn: () => {
      const body: WorkExperienceIn = {
        ...form,
        bullets: bullets.split('\n').map((b) => b.trim()).filter(Boolean),
      }
      return editId
        ? api.put<WorkExperienceOut>(`/api/profile/work-experiences/${editId}`, body)
        : api.post<WorkExperienceOut>('/api/profile/work-experiences', body)
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
      title={editId ? 'Edit experience' : 'Add experience'}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" loading={save.isPending} onClick={() => save.mutate()} disabled={!form.title || !form.company}>
            Save
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Input label="Job title" required value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} />
          <Input label="Company" required value={form.company} onChange={(e) => setForm((f) => ({ ...f, company: e.target.value }))} />
          <Input label="Location" value={form.location ?? ''} onChange={(e) => setForm((f) => ({ ...f, location: e.target.value || null }))} />
          <div />
          <Input label="Start date" type="date" value={form.start_date ?? ''} onChange={(e) => setForm((f) => ({ ...f, start_date: e.target.value || null }))} />
          <Input label="End date" type="date" value={form.end_date ?? ''} disabled={form.is_current} onChange={(e) => setForm((f) => ({ ...f, end_date: e.target.value || null }))} />
        </div>
        <Toggle checked={Boolean(form.is_current)} onChange={(v) => setForm((f) => ({ ...f, is_current: v, end_date: v ? null : f.end_date }))} label="I currently work here" />
        <div>
          <label className="label">Highlights (one per line)</label>
          <textarea className="input min-h-[100px]" value={bullets} onChange={(e) => setBullets(e.target.value)} placeholder="Led a team of 5…&#10;Shipped X that improved Y…" />
        </div>
      </div>
    </Modal>
  )
}

export function WorkTab({ items }: { items: WorkExperienceOut[] }) {
  const queryClient = useQueryClient()
  const { push } = useToast()
  const [modal, setModal] = useState<{ open: boolean; initial: WorkExperienceIn; editId: number | null }>({
    open: false,
    initial: EMPTY,
    editId: null,
  })

  const sorted = [...items].sort((a, b) => a.order_index - b.order_index)

  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/api/profile/work-experiences/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.profile }),
  })
  const reorder = useMutation({
    mutationFn: (ids: number[]) => api.post('/api/profile/work-experiences/reorder', { ids }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.profile }),
    onError: (e) => push({ title: 'Could not reorder', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })

  const move = (index: number, dir: -1 | 1) => {
    const next = [...sorted]
    const target = index + dir
    if (target < 0 || target >= next.length) return
    ;[next[index], next[target]] = [next[target], next[index]]
    reorder.mutate(next.map((w) => w.id))
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-neutral-500 dark:text-neutral-400">Drag order matters — the top entry is your most recent role.</p>
        <Button variant="primary" size="sm" icon="plus" onClick={() => setModal({ open: true, initial: EMPTY, editId: null })}>
          Add experience
        </Button>
      </div>

      {sorted.length === 0 ? (
        <EmptyState icon="applications" title="No work experience yet" description="Add your roles so JobPilot can answer experience questions." />
      ) : (
        <ul className="space-y-3">
          {sorted.map((w, i) => (
            <li key={w.id}>
              <Card padded={false} className="p-4">
                <div className="flex gap-3">
                  <div className="flex flex-col gap-1 pt-0.5">
                    <button onClick={() => move(i, -1)} disabled={i === 0} className="rounded p-0.5 text-neutral-400 hover:text-neutral-700 disabled:opacity-30 dark:hover:text-neutral-200" aria-label="Move up">
                      <Icon name="chevronDown" className="h-4 w-4 rotate-180" />
                    </button>
                    <button onClick={() => move(i, 1)} disabled={i === sorted.length - 1} className="rounded p-0.5 text-neutral-400 hover:text-neutral-700 disabled:opacity-30 dark:hover:text-neutral-200" aria-label="Move down">
                      <Icon name="chevronDown" className="h-4 w-4" />
                    </button>
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <h4 className="font-semibold text-neutral-900 dark:text-neutral-100">{w.title}</h4>
                      {w.is_current ? <Badge tone="success">Current</Badge> : null}
                    </div>
                    <p className="text-sm text-neutral-600 dark:text-neutral-300">
                      {w.company}
                      {w.location ? ` · ${w.location}` : ''}
                    </p>
                    <p className="mt-0.5 text-xs text-neutral-400">
                      {fmtDate(w.start_date)} – {w.is_current ? 'Present' : fmtDate(w.end_date)}
                    </p>
                    {w.bullets && w.bullets.length > 0 ? (
                      <ul className="mt-2 list-disc space-y-0.5 pl-5 text-sm text-neutral-600 dark:text-neutral-300">
                        {w.bullets.map((b, bi) => (
                          <li key={bi}>{b}</li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <button
                      onClick={() =>
                        setModal({
                          open: true,
                          editId: w.id,
                          initial: {
                            title: w.title,
                            company: w.company,
                            location: w.location ?? null,
                            start_date: w.start_date ?? null,
                            end_date: w.end_date ?? null,
                            is_current: w.is_current,
                            bullets: w.bullets ?? [],
                          },
                        })
                      }
                      className="rounded-lg p-2 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700 dark:hover:bg-neutral-800"
                      aria-label="Edit"
                    >
                      <Icon name="edit" className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => remove.mutate(w.id)}
                      className="rounded-lg p-2 text-neutral-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-500/10"
                      aria-label="Delete"
                    >
                      <Icon name="trash" className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}

      <WorkModal
        key={`${modal.editId}-${modal.open}`}
        open={modal.open}
        initial={modal.initial}
        editId={modal.editId}
        onClose={() => setModal((m) => ({ ...m, open: false }))}
      />
    </div>
  )
}
