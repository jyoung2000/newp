import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api'
import { qk } from '../../lib/queryKeys'
import type { UserSettings } from '../../lib/types'
import { useAutosave } from '../../lib/useAutosave'
import { Card, CardHeader } from '../Card'
import { Select, Input } from '../Field'
import { Toggle } from '../Toggle'
import { Icon } from '../Icon'
import { SaveIndicator } from '../SaveIndicator'

export function PreferencesSection({ initial }: { initial: UserSettings }) {
  const queryClient = useQueryClient()
  const [s, setS] = useState<UserSettings>(initial)

  const save = useMutation({
    mutationFn: (next: UserSettings) => api.put<UserSettings>('/api/auth/settings', next),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.settings }),
  })
  const status = useAutosave(s, (next) => save.mutateAsync(next))

  const patch = (p: Partial<UserSettings>) => setS((prev) => ({ ...prev, ...p }))
  const patchNotif = (p: Partial<NonNullable<UserSettings['notifications']>>) =>
    setS((prev) => ({ ...prev, notifications: { ...(prev.notifications ?? { email_enabled: false, webhook_enabled: false }), ...p } }))

  const notif = s.notifications ?? { email_enabled: false, webhook_enabled: false }
  const threshold = s.resolver_confidence_threshold ?? 0.75

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader
          title="Application defaults"
          subtitle="Used when you start a run without changing them"
          icon={<Icon name="sparkles" />}
          action={<SaveIndicator status={status} />}
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <Select label="Default run mode" value={s.run_mode_default ?? 'review'} onChange={(e) => patch({ run_mode_default: e.target.value as UserSettings['run_mode_default'] })}>
            <option value="auto">Auto — fill & submit</option>
            <option value="review">Review — pause before submit</option>
            <option value="draft">Draft — prepare only</option>
          </Select>
          <Select label="Default executor" value={s.executor_default ?? 'auto'} onChange={(e) => patch({ executor_default: e.target.value as UserSettings['executor_default'] })}>
            <option value="auto">Auto</option>
            <option value="extension">Browser extension</option>
            <option value="playwright">Server (Playwright)</option>
          </Select>
        </div>
        <div className="mt-4 rounded-xl border border-neutral-200 p-3 dark:border-neutral-800">
          <Toggle checked={s.humanize_default ?? true} onChange={(v) => patch({ humanize_default: v })} label="Humanize typing by default" description="Natural pauses and typing rhythm while filling forms." />
        </div>
        <div className="mt-4">
          <label className="label">
            Auto-answer confidence threshold — <span className="font-semibold text-accent-600 dark:text-accent-400">{Math.round(threshold * 100)}%</span>
          </label>
          <input
            type="range"
            min={0.5}
            max={1}
            step={0.05}
            value={threshold}
            onChange={(e) => patch({ resolver_confidence_threshold: Number(e.target.value) })}
            className="w-full accent-accent-600"
          />
          <p className="mt-1 text-xs text-neutral-400">Below this confidence, JobPilot asks you instead of answering automatically.</p>
        </div>
      </Card>

      <Card>
        <CardHeader title="Notifications" subtitle="How you hear about interventions and results" icon={<Icon name="bell" />} />
        <div className="space-y-4">
          <div className="rounded-xl border border-neutral-200 p-3 dark:border-neutral-800">
            <Toggle checked={notif.email_enabled} onChange={(v) => patchNotif({ email_enabled: v })} label="Email notifications" />
            {notif.email_enabled ? (
              <div className="mt-3">
                <Input type="email" value={notif.email_address ?? ''} onChange={(e) => patchNotif({ email_address: e.target.value || null })} placeholder="you@example.com" />
              </div>
            ) : null}
          </div>
          <div className="rounded-xl border border-neutral-200 p-3 dark:border-neutral-800">
            <Toggle checked={notif.webhook_enabled} onChange={(v) => patchNotif({ webhook_enabled: v })} label="Webhook" description="POST a JSON payload on key events." />
            {notif.webhook_enabled ? (
              <div className="mt-3">
                <Input value={notif.webhook_url ?? ''} onChange={(e) => patchNotif({ webhook_url: e.target.value || null })} placeholder="https://…" />
              </div>
            ) : null}
          </div>
          <Input label="Timezone" value={s.timezone ?? 'UTC'} onChange={(e) => patch({ timezone: e.target.value })} hint="Used for schedules and timestamps." />
        </div>
      </Card>
    </div>
  )
}
