import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../../lib/api'
import { qk } from '../../lib/queryKeys'
import type { CustomFieldIn, CustomFieldOut } from '../../lib/types'
import { Card } from '../Card'
import { Button } from '../Button'
import { Badge } from '../Badge'
import { Input, Select } from '../Field'
import { Toggle } from '../Toggle'
import { ChipInput } from '../ChipInput'
import { Modal } from '../Modal'
import { Icon } from '../Icon'
import { EmptyState } from '../EmptyState'
import { SkeletonRows } from '../Skeleton'
import { useToast } from '../../lib/toast'
import { titleCase } from '../../lib/format'

const TYPES = ['text', 'textarea', 'number', 'boolean', 'select', 'date']

interface FieldForm {
  label: string
  type: string
  options: string[]
  value: string
  boolValue: boolean
}

const EMPTY: FieldForm = { label: '', type: 'text', options: [], value: '', boolValue: false }

function FieldModal({ open, initial, editId, onClose }: { open: boolean; initial: FieldForm; editId: number | null; onClose: () => void }) {
  const queryClient = useQueryClient()
  const { push } = useToast()
  const [form, setForm] = useState<FieldForm>(initial)

  const save = useMutation({
    mutationFn: () => {
      const body: CustomFieldIn = {
        label: form.label,
        type: form.type,
        options: form.type === 'select' ? form.options : [],
        value: form.type === 'boolean' ? form.boolValue : form.value || null,
        file_id: null,
      }
      return editId ? api.put<CustomFieldOut>(`/api/custom-fields/${editId}`, body) : api.post<CustomFieldOut>('/api/custom-fields', body)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.customFields })
      push({ title: editId ? 'Updated' : 'Added', tone: 'success' })
      onClose()
    },
    onError: (e) => push({ title: 'Could not save', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={editId ? 'Edit custom field' : 'Add custom field'}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" loading={save.isPending} onClick={() => save.mutate()} disabled={!form.label}>
            Save
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input label="Label" required value={form.label} onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))} placeholder="e.g. Preferred pronoun on badge" />
        <Select label="Type" value={form.type} onChange={(e) => setForm((f) => ({ ...f, type: e.target.value }))}>
          {TYPES.map((t) => (
            <option key={t} value={t}>
              {titleCase(t)}
            </option>
          ))}
        </Select>
        {form.type === 'select' ? (
          <ChipInput label="Options" value={form.options} onChange={(v) => setForm((f) => ({ ...f, options: v }))} placeholder="Add an option" />
        ) : null}
        {form.type === 'boolean' ? (
          <Toggle checked={form.boolValue} onChange={(v) => setForm((f) => ({ ...f, boolValue: v }))} label="Default value" />
        ) : form.type === 'textarea' ? (
          <div>
            <label className="label">Value</label>
            <textarea className="input min-h-[80px]" value={form.value} onChange={(e) => setForm((f) => ({ ...f, value: e.target.value }))} />
          </div>
        ) : (
          <Input
            label="Value"
            type={form.type === 'number' ? 'number' : form.type === 'date' ? 'date' : 'text'}
            value={form.value}
            onChange={(e) => setForm((f) => ({ ...f, value: e.target.value }))}
          />
        )}
      </div>
    </Modal>
  )
}

export function CustomFieldsTab() {
  const queryClient = useQueryClient()
  const [modal, setModal] = useState<{ open: boolean; initial: FieldForm; editId: number | null }>({ open: false, initial: EMPTY, editId: null })

  const { data, isLoading } = useQuery({
    queryKey: qk.customFields,
    queryFn: () => api.get<CustomFieldOut[]>('/api/custom-fields'),
  })
  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/api/custom-fields/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.customFields }),
  })

  const renderValue = (v: unknown) => (v == null || v === '' ? '—' : typeof v === 'boolean' ? (v ? 'Yes' : 'No') : String(v))

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-neutral-500 dark:text-neutral-400">Reusable answers for anything not covered by the standard profile.</p>
        <Button variant="primary" size="sm" icon="plus" onClick={() => setModal({ open: true, initial: EMPTY, editId: null })}>
          Add field
        </Button>
      </div>
      {isLoading ? (
        <SkeletonRows rows={3} />
      ) : !data || data.length === 0 ? (
        <EmptyState icon="edit" title="No custom fields" description="Add custom question/answer pairs JobPilot can reuse." />
      ) : (
        <ul className="space-y-2">
          {data.map((cf) => (
            <li key={cf.id}>
              <Card padded={false} className="flex items-center gap-3 p-3.5">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-medium text-neutral-900 dark:text-neutral-100">{cf.label}</span>
                    <Badge tone="neutral">{titleCase(cf.type)}</Badge>
                  </div>
                  <p className="truncate text-sm text-neutral-500 dark:text-neutral-400">{renderValue(cf.value)}</p>
                </div>
                <div className="flex shrink-0 gap-1">
                  <button
                    onClick={() =>
                      setModal({
                        open: true,
                        editId: cf.id,
                        initial: {
                          label: cf.label,
                          type: cf.type,
                          options: cf.options ?? [],
                          value: typeof cf.value === 'boolean' ? '' : cf.value == null ? '' : String(cf.value),
                          boolValue: cf.value === true,
                        },
                      })
                    }
                    className="rounded-lg p-2 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700 dark:hover:bg-neutral-800"
                    aria-label="Edit"
                  >
                    <Icon name="edit" className="h-4 w-4" />
                  </button>
                  <button onClick={() => remove.mutate(cf.id)} className="rounded-lg p-2 text-neutral-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-500/10" aria-label="Delete">
                    <Icon name="trash" className="h-4 w-4" />
                  </button>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
      <FieldModal key={`${modal.editId}-${modal.open}`} open={modal.open} initial={modal.initial} editId={modal.editId} onClose={() => setModal((m) => ({ ...m, open: false }))} />
    </div>
  )
}
