import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api'
import { qk } from '../../lib/queryKeys'
import type { AISettingsOut, AISettingsUpdate, AITestResult } from '../../lib/types'
import { Card, CardHeader } from '../Card'
import { Input, Select } from '../Field'
import { Button } from '../Button'
import { Toggle } from '../Toggle'
import { Icon } from '../Icon'
import { Badge } from '../Badge'
import { SkeletonRows } from '../Skeleton'
import { useToast } from '../../lib/toast'

const KEY_CONSOLE = 'https://console.anthropic.com/settings/keys'

export function AISection() {
  const queryClient = useQueryClient()
  const toast = useToast()
  const [keyInput, setKeyInput] = useState('')
  const [revealInput, setRevealInput] = useState(false)
  const [test, setTest] = useState<AITestResult | null>(null)

  const settings = useQuery({
    queryKey: qk.aiSettings,
    queryFn: () => api.get<AISettingsOut>('/api/settings/ai'),
  })

  const save = useMutation({
    mutationFn: (patch: AISettingsUpdate) => api.put<AISettingsOut>('/api/settings/ai', patch),
    onSuccess: (data) => {
      queryClient.setQueryData(qk.aiSettings, data)
      setTest(null)
    },
  })

  const clearKey = useMutation({
    mutationFn: () => api.del<AISettingsOut>('/api/settings/ai/key'),
    onSuccess: (data) => {
      queryClient.setQueryData(qk.aiSettings, data)
      setKeyInput('')
      setTest(null)
      toast.push({ title: 'API key removed', message: 'JobPilot is back to offline mode.', tone: 'info' })
    },
  })

  const runTest = useMutation({
    mutationFn: () => api.post<AITestResult>('/api/settings/ai/test'),
    onSuccess: (data) => setTest(data),
  })

  if (settings.isLoading || !settings.data) return <SkeletonRows rows={4} />
  const s = settings.data
  const models = s.available_models ?? []

  const saveKey = async () => {
    const key = keyInput.trim()
    if (!key) return
    await save.mutateAsync({ api_key: key })
    setKeyInput('')
    setRevealInput(false)
    toast.push({ title: 'API key saved', message: 'Stored encrypted on this machine.', tone: 'success' })
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader
          title="AI provider"
          subtitle="Used for résumé parsing, listing summaries and match scores, unknown-field mapping, and drafted answers"
          icon={<Icon name="sparkles" />}
          action={
            s.effective_offline ? (
              <Badge tone="neutral">Offline</Badge>
            ) : (
              <Badge tone="success">Connected</Badge>
            )
          }
        />

        <div className="space-y-4">
          <div className="rounded-xl border border-neutral-200 p-4 dark:border-neutral-800">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="text-sm font-semibold">Anthropic API key</div>
                <div className="mt-0.5 text-xs text-neutral-500 dark:text-neutral-400">
                  {s.key_source === 'user' ? (
                    <>
                      Stored encrypted on this machine ·{' '}
                      <code className="rounded bg-neutral-100 px-1 py-0.5 dark:bg-neutral-800">
                        {s.key_hint}
                      </code>
                    </>
                  ) : s.key_source === 'env' ? (
                    <>
                      Provided by the <code>ANTHROPIC_API_KEY</code> environment variable ·{' '}
                      <code className="rounded bg-neutral-100 px-1 py-0.5 dark:bg-neutral-800">
                        {s.key_hint}
                      </code>
                    </>
                  ) : (
                    <>No key set — JobPilot uses offline heuristics.</>
                  )}
                </div>
              </div>
              {s.key_source === 'user' ? (
                <Button
                  variant="ghost"
                  onClick={() => clearKey.mutate()}
                  disabled={clearKey.isPending}
                >
                  <Icon name="trash" className="h-4 w-4" />
                  Remove key
                </Button>
              ) : null}
            </div>

            <div className="mt-3 flex flex-col gap-2 sm:flex-row">
              <div className="flex-1">
                <Input
                  type={revealInput ? 'text' : 'password'}
                  value={keyInput}
                  autoComplete="off"
                  spellCheck={false}
                  placeholder={s.key_source === 'none' ? 'sk-ant-…' : 'Enter a new key to replace the current one'}
                  onChange={(e) => setKeyInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') void saveKey()
                  }}
                />
              </div>
              <div className="flex gap-2">
                <Button
                  variant="ghost"
                  aria-label={revealInput ? 'Hide key' : 'Show key'}
                  onClick={() => setRevealInput((v) => !v)}
                >
                  <Icon name={revealInput ? 'eyeOff' : 'eye'} className="h-4 w-4" />
                </Button>
                <Button onClick={() => void saveKey()} disabled={!keyInput.trim() || save.isPending}>
                  {save.isPending ? 'Saving…' : 'Save key'}
                </Button>
              </div>
            </div>

            <p className="mt-2 text-xs text-neutral-400">
              Get a key from the{' '}
              <a href={KEY_CONSOLE} target="_blank" rel="noreferrer" className="text-accent-600 hover:underline dark:text-accent-400">
                Anthropic Console
              </a>
              . It is encrypted before it is stored and is never shown again — only the hint above.
            </p>
          </div>

          <Select
            label="Model"
            value={s.model}
            onChange={(e) => save.mutate({ model: e.target.value })}
            hint={
              models.find((m) => m.id === s.model)?.note ??
              'The model used for every JobPilot AI task.'
            }
          >
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
            {models.some((m) => m.id === s.model) ? null : (
              <option value={s.model}>{s.model}</option>
            )}
          </Select>

          <div className="rounded-xl border border-neutral-200 p-3 dark:border-neutral-800">
            <Toggle
              checked={s.offline}
              onChange={(v) => save.mutate({ offline: v })}
              label="Offline mode"
              description="Use deterministic local heuristics and send nothing to Anthropic. Parsing and matching are rougher, but no data leaves this machine."
            />
            {s.env_offline && !s.offline ? (
              <p className="mt-2 text-xs text-amber-600 dark:text-amber-500">
                <code>LLM_DRY_RUN</code> is set in the environment, which turns offline mode on by default.
              </p>
            ) : null}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Button variant="ghost" onClick={() => runTest.mutate()} disabled={runTest.isPending}>
              <Icon name="wifi" className="h-4 w-4" />
              {runTest.isPending ? 'Testing…' : 'Test connection'}
            </Button>
            {test ? (
              <span
                className={
                  test.ok
                    ? 'text-sm text-emerald-600 dark:text-emerald-400'
                    : 'text-sm text-red-600 dark:text-red-400'
                }
              >
                <Icon name={test.ok ? 'checkCircle' : 'alert'} className="mr-1 inline h-4 w-4" />
                {test.detail}
              </span>
            ) : null}
          </div>
        </div>
      </Card>

      <Card>
        <CardHeader
          title="What the model sees"
          subtitle="The one place your data leaves this machine"
          icon={<Icon name="shield" />}
        />
        <ul className="space-y-2 text-sm text-neutral-600 dark:text-neutral-400">
          <li className="flex gap-2">
            <Icon name="chevronRight" className="mt-0.5 h-4 w-4 shrink-0 text-neutral-400" />
            <span>Your résumé text, when you ask JobPilot to parse it (you review the parse before it is used).</span>
          </li>
          <li className="flex gap-2">
            <Icon name="chevronRight" className="mt-0.5 h-4 w-4 shrink-0 text-neutral-400" />
            <span>Job-listing text plus a compact summary of your profile, to score how well a listing matches you.</span>
          </li>
          <li className="flex gap-2">
            <Icon name="chevronRight" className="mt-0.5 h-4 w-4 shrink-0 text-neutral-400" />
            <span>A single form field&rsquo;s label, type and options, when mapping an unrecognized question to your stored answers.</span>
          </li>
          <li className="flex gap-2">
            <Icon name="chevronRight" className="mt-0.5 h-4 w-4 shrink-0 text-neutral-400" />
            <span>A question and your own facts, when drafting a free-text answer you then approve.</span>
          </li>
        </ul>
        <div className="mt-4 rounded-xl border border-accent-200 bg-accent-50 p-3 text-sm text-accent-900 dark:border-accent-900/40 dark:bg-accent-950/40 dark:text-accent-200">
          <b>Never sent:</b> your EEO self-identification answers and your current-compensation figure are
          deliberately excluded from everything the model sees, so they cannot leak into a generated answer.
          There is no telemetry and no third-party analytics anywhere in JobPilot.
        </div>
      </Card>
    </div>
  )
}
