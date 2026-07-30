import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../../lib/api'
import { qk } from '../../lib/queryKeys'
import type { RoleOut, RolePreview } from '../../lib/types'
import { Button } from '../Button'
import { Badge } from '../Badge'
import { Input } from '../Field'
import { Icon } from '../Icon'
import { Spinner } from '../Spinner'
import { useToast } from '../../lib/toast'
import { cx } from '../../lib/format'

/**
 * "What do you want to be paid to do?" — as many answers as they like.
 *
 * Each role shows the variations that will also count, because the proposal
 * comes from a curated vocabulary that cannot know every industry. Showing it
 * turns a silent guess into something the user can correct, and it explains why
 * a "Software Developer" posting later shows up under "Software Engineer".
 */
export function RolesStep({ onCountChange }: { onCountChange?: (n: number) => void }) {
  const queryClient = useQueryClient()
  const { push } = useToast()
  const [draft, setDraft] = useState('')
  const [editing, setEditing] = useState<number | null>(null)

  const roles = useQuery({
    queryKey: qk.roles,
    queryFn: async () => {
      const list = await api.get<RoleOut[]>('/api/roles')
      onCountChange?.(list.length)
      return list
    },
  })

  // Previewed live as they type, so the variations appear before they commit.
  const trimmed = draft.trim()
  const preview = useQuery({
    queryKey: qk.rolePreview(trimmed),
    queryFn: () => api.get<RolePreview>(`/api/roles/preview?title=${encodeURIComponent(trimmed)}`),
    enabled: trimmed.length >= 3,
    staleTime: 60_000,
  })

  const add = useMutation({
    mutationFn: (title: string) => api.post<RoleOut>('/api/roles', { title }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: qk.roles })
      setDraft('')
    },
    onError: (e) =>
      push({ title: 'Could not add that role', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })

  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/api/roles/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.roles }),
  })

  const saveVariations = useMutation({
    mutationFn: (input: { role: RoleOut; variations: string[] }) =>
      api.put<RoleOut>(`/api/roles/${input.role.id}`, {
        title: input.role.title,
        variations: input.variations,
        location: input.role.location,
        remote: input.role.remote,
        salary_floor: input.role.salary_floor,
        schedule_minutes: input.role.schedule_minutes,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: qk.roles })
      setEditing(null)
    },
    onError: (e) =>
      push({ title: 'Could not save', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })

  const submit = () => {
    if (trimmed.length < 2 || add.isPending) return
    add.mutate(trimmed)
  }

  const list = roles.data ?? []

  return (
    <div className="space-y-5">
      <div>
        <div className="flex gap-2">
          <Input
            className="flex-1"
            value={draft}
            placeholder="e.g. Software Engineer"
            aria-label="Job title you want"
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                e.stopPropagation()
                submit()
              }
            }}
          />
          <Button
            variant="secondary"
            icon="plus"
            onClick={submit}
            disabled={trimmed.length < 2}
            loading={add.isPending}
          >
            Add
          </Button>
        </div>

        {/* What adding it would accept, before they add it. */}
        {trimmed.length >= 3 ? (
          <div className="mt-2 min-h-[1.5rem] text-xs text-neutral-500 dark:text-neutral-400">
            {preview.isFetching ? (
              <span className="inline-flex items-center gap-1.5">
                <Spinner className="h-3 w-3" /> Working out the variations…
              </span>
            ) : preview.data ? (
              preview.data.variations.length > 0 ? (
                <span>
                  Also matches{' '}
                  <span className="text-neutral-700 dark:text-neutral-200">
                    {preview.data.variations.join(', ')}
                  </span>
                </span>
              ) : preview.data.recognised ? (
                <span>No close variations — this title will be matched as written.</span>
              ) : (
                <span>
                  A title JobPilot doesn’t recognise. It will match on the words themselves — add
                  variations yourself once it’s saved.
                </span>
              )
            ) : null}
          </div>
        ) : (
          <p className="mt-2 min-h-[1.5rem] text-xs text-neutral-400">
            Add as many as you like. Press Enter after each.
          </p>
        )}
      </div>

      {list.length === 0 ? (
        <div className="rounded-xl border border-dashed border-neutral-300 px-4 py-8 text-center dark:border-neutral-700">
          <Icon name="search" className="mx-auto h-6 w-6 text-neutral-300 dark:text-neutral-600" />
          <p className="mt-2 text-sm text-neutral-500 dark:text-neutral-400">
            No roles yet. JobPilot searches for the titles you add here — and the variations of
            them — every few hours.
          </p>
        </div>
      ) : (
        <ul className="space-y-2">
          {list.map((role) => (
            <li
              key={role.id}
              className="rounded-xl border border-neutral-200 px-4 py-3 dark:border-neutral-800"
            >
              <div className="flex items-start gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-neutral-900 dark:text-neutral-100">
                      {role.title}
                    </span>
                    {role.listings_found > 0 ? (
                      <Badge tone="success">{role.listings_found} found</Badge>
                    ) : role.last_run_at ? (
                      <Badge tone="neutral">searched, nothing yet</Badge>
                    ) : (
                      <Badge tone="neutral">queued</Badge>
                    )}
                  </div>
                  {editing === role.id ? (
                    <VariationEditor
                      role={role}
                      saving={saveVariations.isPending}
                      onCancel={() => setEditing(null)}
                      onSave={(variations) => saveVariations.mutate({ role, variations })}
                    />
                  ) : (
                    <button
                      onClick={() => setEditing(role.id)}
                      className="mt-1 block text-left text-xs text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-100"
                    >
                      {role.variations.length > 0 ? (
                        <>
                          also matches {role.variations.join(', ')}{' '}
                          <span className="text-accent-600 dark:text-accent-400">edit</span>
                        </>
                      ) : (
                        <span className="text-accent-600 dark:text-accent-400">
                          add variations
                        </span>
                      )}
                    </button>
                  )}
                </div>
                <button
                  onClick={() => remove.mutate(role.id)}
                  aria-label={`Remove ${role.title}`}
                  className="rounded-lg p-1.5 text-neutral-400 transition-colors hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-500/10"
                >
                  <Icon name="close" className="h-4 w-4" />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** Comma-separated because that is how people already write lists. */
function VariationEditor({
  role,
  saving,
  onSave,
  onCancel,
}: {
  role: RoleOut
  saving: boolean
  onSave: (variations: string[]) => void
  onCancel: () => void
}) {
  const [text, setText] = useState(role.variations.join(', '))
  return (
    <div className="mt-2">
      <Input
        value={text}
        onChange={(e) => setText(e.target.value)}
        aria-label={`Variations of ${role.title}`}
        placeholder="Software Developer, Backend Engineer"
        hint="Comma separated. These also count as this role."
      />
      <div className="mt-2 flex gap-2">
        <Button
          size="sm"
          variant="primary"
          loading={saving}
          onClick={() =>
            onSave(
              text
                .split(',')
                .map((v) => v.trim())
                .filter(Boolean),
            )
          }
        >
          Save
        </Button>
        <Button size="sm" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  )
}

/** Shown on the final screen, summarising what will happen next. */
export function RolesSummary({ roles }: { roles: RoleOut[] }) {
  if (roles.length === 0) return null
  return (
    <div className={cx('flex flex-wrap gap-1.5')}>
      {roles.map((r) => (
        <Badge key={r.id} tone="accent">
          {r.title}
        </Badge>
      ))}
    </div>
  )
}
