import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../lib/api'
import { qk } from '../lib/queryKeys'
import { useFiles, useProfile, useUserSettings } from '../lib/hooks'
import type {
  ConfirmParseRequest,
  FileOut,
  ParsedResume,
  ProfileUpdate,
  RoleOut,
  UserSettings,
} from '../lib/types'
import { ChoiceCard, Fieldset, StepFrame } from '../components/onboarding/Scaffold'
import { RolesStep, RolesSummary } from '../components/onboarding/RolesStep'
import { WorkTab } from '../components/profile/WorkTab'
import { RecommendationsTab } from '../components/profile/RecommendationsTab'
import { Button } from '../components/Button'
import { Input, Select } from '../components/Field'
import { Icon } from '../components/Icon'
import { Spinner } from '../components/Spinner'
import { SpringCheck } from '../components/SpringCheck'
import { ChipInput } from '../components/ChipInput'
import { useToast } from '../lib/toast'

/**
 * Guided first-run setup.
 *
 * What it asks is not a guess: every field here is one the resolver can already
 * answer on a real form (services/field_library.py), which is the difference
 * between onboarding that pays for itself and a questionnaire. The knockout
 * questions — right to work, sponsorship, age, notice period — come before the
 * nice-to-haves, because those are the ones that stop an application dead when
 * they are missing.
 *
 * Three rules the flow keeps to:
 *  - Nothing is trapped. Every screen can be skipped except the one that needs
 *    a name, and everything lands in the ordinary Profile tabs, editable
 *    forever — the work-history and references screens *are* those editors.
 *  - Nothing is lost. Each step saves as you leave it, and the step reached is
 *    remembered, so closing the tab resumes instead of restarting.
 *  - Nothing is invented. Where an answer is voluntary (the EEO block) the
 *    default is to decline rather than to fill something in.
 */

type StepKey =
  | 'welcome'
  | 'resume'
  | 'you'
  | 'work'
  | 'eligibility'
  | 'voluntary'
  | 'references'
  | 'roles'
  | 'done'

const STEPS: StepKey[] = [
  'welcome',
  'resume',
  'you',
  'work',
  'eligibility',
  'voluntary',
  'references',
  'roles',
  'done',
]

type WorkModel = NonNullable<ProfileUpdate['work_model_preference']>
type PayPeriod = NonNullable<ProfileUpdate['salary_expectation_period']>

const WORK_MODELS: { value: WorkModel; label: string }[] = [
  { value: 'remote', label: 'Remote' },
  { value: 'hybrid', label: 'Hybrid' },
  { value: 'onsite', label: 'On-site' },
  { value: 'any', label: 'No preference' },
]
const PAY_PERIODS: { value: PayPeriod; label: string }[] = [
  { value: 'year', label: 'Year' },
  { value: 'month', label: 'Month' },
  { value: 'hour', label: 'Hour' },
]

export function Onboarding() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { push } = useToast()
  const [params, setParams] = useSearchParams()

  const profile = useProfile()
  const files = useFiles()
  const settings = useUserSettings()
  const roles = useQuery({ queryKey: qk.roles, queryFn: () => api.get<RoleOut[]>('/api/roles') })

  // The URL owns which step is showing, so Back/Forward and a refresh all
  // behave. The saved step is only consulted to pick up where the user left
  // off when they arrive without one.
  const urlStep = (params.get('step') as StepKey | null) ?? null
  const [resumed, setResumed] = useState(false)
  const stepKey: StepKey = urlStep && STEPS.includes(urlStep) ? urlStep : 'welcome'
  const stepIndex = STEPS.indexOf(stepKey)

  const saveSettings = useMutation({
    mutationFn: (patch: Partial<UserSettings>) =>
      api.put<UserSettings>('/api/auth/settings', { ...(settings.data ?? {}), ...patch }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.settings }),
  })

  useEffect(() => {
    if (resumed || urlStep || !settings.data) return
    setResumed(true)
    const saved = settings.data.onboarding_step as StepKey | null | undefined
    if (saved && STEPS.includes(saved) && saved !== 'welcome') {
      setParams({ step: saved }, { replace: true })
    }
  }, [resumed, urlStep, settings.data, setParams])

  const go = (key: StepKey) => {
    setParams({ step: key })
    saveSettings.mutate({ onboarding_step: key })
    window.scrollTo({ top: 0 })
  }
  const next = () => go(STEPS[Math.min(stepIndex + 1, STEPS.length - 1)])
  const back = stepIndex > 0 ? () => go(STEPS[stepIndex - 1]) : undefined

  const finish = () => {
    saveSettings.mutate({
      onboarding_step: 'done',
      onboarding_completed: true,
      onboarding_dismissed: true,
    })
    navigate('/')
  }

  // --- profile draft --------------------------------------------------------
  // Held locally and written when leaving a step, so a half-typed screen is
  // never pushed and nothing is lost on the way out.
  const [draft, setDraft] = useState<ProfileUpdate>({})
  const p = profile.data?.profile as ProfileUpdate | undefined
  const field = <K extends keyof ProfileUpdate>(key: K): ProfileUpdate[K] =>
    (draft[key] !== undefined ? draft[key] : p?.[key]) as ProfileUpdate[K]
  const set = <K extends keyof ProfileUpdate>(key: K, value: ProfileUpdate[K]) =>
    setDraft((d) => ({ ...d, [key]: value }))

  const saveProfile = useMutation({
    mutationFn: (body: ProfileUpdate) => api.put('/api/profile', body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.profile })
      setDraft({})
    },
    onError: (e) =>
      push({ title: 'Could not save', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })

  const saveAndNext = () => {
    if (Object.keys(draft).length === 0) {
      next()
      return
    }
    saveProfile.mutate(draft, { onSuccess: () => next() })
  }

  const common = { stepIndex, stepCount: STEPS.length, onBack: back }
  const busy = saveProfile.isPending

  // --- steps ---------------------------------------------------------------

  if (stepKey === 'welcome') {
    return (
      <StepFrame
        {...common}
        onBack={undefined}
        title="Let’s set you up"
        subtitle="A few minutes now, and JobPilot can fill an employer’s application form with your answers instead of asking you the same twenty questions every time."
        nextLabel="Get started"
        onNext={next}
        onSkip={finish}
        skipLabel="I’ll do this later"
      >
        <ul className="space-y-3">
          {[
            {
              icon: 'user' as const,
              title: 'Your answers, never invented',
              body: 'If a form asks something you haven’t told JobPilot, it stops and asks you.',
            },
            {
              icon: 'shield' as const,
              title: 'You solve every CAPTCHA',
              body: 'JobPilot detects challenges and hands them to you. It never answers one.',
            },
            {
              icon: 'edit' as const,
              title: 'Nothing here is final',
              body: 'Everything you enter stays editable in Profile.',
            },
          ].map((row) => (
            <li key={row.title} className="flex gap-3">
              <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-accent-50 text-accent-600 dark:bg-accent-500/15 dark:text-accent-400">
                <Icon name={row.icon} className="h-4 w-4" />
              </span>
              <span>
                <span className="block text-sm font-medium text-neutral-900 dark:text-neutral-100">
                  {row.title}
                </span>
                <span className="block text-sm text-neutral-500 dark:text-neutral-400">{row.body}</span>
              </span>
            </li>
          ))}
        </ul>
      </StepFrame>
    )
  }

  if (stepKey === 'resume') {
    return (
      <ResumeStep
        stepIndex={stepIndex}
        stepCount={STEPS.length}
        onBack={back}
        onNext={next}
        onSkip={next}
        hasResume={Boolean(files.data?.some((f) => f.is_default_resume || f.parse_confirmed))}
      />
    )
  }

  if (stepKey === 'you') {
    const ready = Boolean(field('first_name') && field('last_name') && field('email'))
    return (
      <StepFrame
        {...common}
        eyebrow="About you"
        title="The basics every form asks for"
        subtitle="Name, how to reach you, and where you are. If you uploaded a résumé, some of this is already filled in — worth a glance."
        onNext={saveAndNext}
        nextDisabled={!ready}
        nextLoading={busy}
      >
        <div className="space-y-6">
          <Fieldset>
            <div className="grid gap-4 sm:grid-cols-2">
              <Input label="First name" required value={field('first_name') ?? ''} onChange={(e) => set('first_name', e.target.value)} />
              <Input label="Last name" required value={field('last_name') ?? ''} onChange={(e) => set('last_name', e.target.value)} />
              <Input label="Email" type="email" required value={field('email') ?? ''} onChange={(e) => set('email', e.target.value)} />
              <Input label="Phone" value={field('phone') ?? ''} onChange={(e) => set('phone', e.target.value)} />
            </div>
          </Fieldset>
          <Fieldset legend="Where you are" hint="Forms ask for a city and country far more often than a street address.">
            <div className="grid gap-4 sm:grid-cols-3">
              <Input label="City" value={field('city') ?? ''} onChange={(e) => set('city', e.target.value)} />
              <Input label="State / region" value={field('state') ?? ''} onChange={(e) => set('state', e.target.value)} />
              <Input label="Country" value={field('country') ?? ''} onChange={(e) => set('country', e.target.value)} />
            </div>
          </Fieldset>
          <Fieldset legend="Links" hint="Optional, and commonly asked for.">
            <div className="grid gap-4 sm:grid-cols-2">
              <Input label="LinkedIn" value={field('linkedin_url') ?? ''} onChange={(e) => set('linkedin_url', e.target.value)} placeholder="https://linkedin.com/in/…" />
              <Input label="Portfolio or website" value={field('portfolio_url') ?? ''} onChange={(e) => set('portfolio_url', e.target.value)} />
            </div>
          </Fieldset>
        </div>
      </StepFrame>
    )
  }

  if (stepKey === 'work') {
    const items = profile.data?.work_experiences ?? []
    return (
      <StepFrame
        {...common}
        eyebrow="Work history"
        title={items.length > 0 ? 'Check your roles' : 'Where have you worked?'}
        subtitle="Application forms want a manager, dates and a reason for leaving per job — more than a résumé carries. Anything left blank becomes a question later."
        onNext={next}
        onSkip={next}
        nextLabel="Continue"
      >
        {/* Literally the Profile → Work editor, so what is learned here is not
            re-learned later and there is one place this is maintained. */}
        <WorkTab items={items} />
      </StepFrame>
    )
  }

  if (stepKey === 'eligibility') {
    return (
      <StepFrame
        {...common}
        eyebrow="Eligibility and pay"
        title="The questions that decide applications"
        subtitle="Forms treat these as pass/fail. JobPilot never guesses them, so whatever you leave blank stops an application and waits for you."
        onNext={saveAndNext}
        nextLoading={busy}
      >
        <div className="space-y-6">
          <Fieldset legend="Right to work" hint="Countries you can work in without sponsorship.">
            <ChipInput
              value={(field('authorized_countries') as string[] | null) ?? []}
              onChange={(v) => set('authorized_countries', v)}
              placeholder="United States, then Enter"
            />
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <ChoiceCard
                selected={field('requires_sponsorship') === false}
                title="I don’t need sponsorship"
                onSelect={() => set('requires_sponsorship', false)}
              />
              <ChoiceCard
                selected={field('requires_sponsorship') === true}
                title="I need sponsorship"
                onSelect={() => set('requires_sponsorship', true)}
              />
            </div>
          </Fieldset>

          <Fieldset legend="Logistics">
            <div className="grid gap-4 sm:grid-cols-2">
              <Select
                label="Preferred work model"
                value={(field('work_model_preference') as string) ?? ''}
                onChange={(e) => set('work_model_preference', (e.target.value || null) as WorkModel | null)}
              >
                <option value="">No answer</option>
                {WORK_MODELS.map((m) => (
                  <option key={m.value} value={m.value}>
                    {m.label}
                  </option>
                ))}
              </Select>
              <Select
                label="Willing to relocate?"
                value={field('willing_to_relocate') === true ? 'yes' : field('willing_to_relocate') === false ? 'no' : ''}
                onChange={(e) =>
                  set(
                    'willing_to_relocate',
                    e.target.value === 'yes' ? true : e.target.value === 'no' ? false : null,
                  )
                }
              >
                <option value="">No answer</option>
                <option value="yes">Yes</option>
                <option value="no">No</option>
              </Select>
              <Input
                label="Notice period (days)"
                type="number"
                min={0}
                value={(field('notice_period_days') as number | null) ?? ''}
                onChange={(e) => set('notice_period_days', e.target.value === '' ? null : Number(e.target.value))}
                hint="Answers “when can you start?”"
              />
              <Input
                label="Years of experience"
                type="number"
                min={0}
                value={(field('total_years_experience') as number | null) ?? ''}
                onChange={(e) =>
                  set('total_years_experience', e.target.value === '' ? null : Number(e.target.value))
                }
              />
              <Select
                label="Are you 18 or older?"
                value={field('over_18') === true ? 'yes' : field('over_18') === false ? 'no' : ''}
                onChange={(e) =>
                  set('over_18', e.target.value === 'yes' ? true : e.target.value === 'no' ? false : null)
                }
              >
                <option value="">No answer</option>
                <option value="yes">Yes</option>
                <option value="no">No</option>
              </Select>
            </div>
          </Fieldset>

          <Fieldset legend="Pay expectation" hint="Asked constantly. A number here saves a stop.">
            <div className="grid gap-4 sm:grid-cols-3">
              <Input
                label="Amount"
                type="number"
                min={0}
                value={(field('salary_expectation_amount') as number | null) ?? ''}
                onChange={(e) =>
                  set('salary_expectation_amount', e.target.value === '' ? null : Number(e.target.value))
                }
              />
              <Input
                label="Currency"
                value={(field('salary_expectation_currency') as string) ?? 'USD'}
                onChange={(e) => set('salary_expectation_currency', e.target.value)}
              />
              <Select
                label="Per"
                value={(field('salary_expectation_period') as string) ?? 'year'}
                onChange={(e) => set('salary_expectation_period', e.target.value as PayPeriod)}
              >
                {PAY_PERIODS.map((period) => (
                  <option key={period.value} value={period.value}>
                    {period.label}
                  </option>
                ))}
              </Select>
            </div>
          </Fieldset>
        </div>
      </StepFrame>
    )
  }

  if (stepKey === 'voluntary') {
    return (
      <StepFrame
        {...common}
        eyebrow="Voluntary"
        title="Self-identification"
        subtitle="Many employers ask these for equal-opportunity reporting. Answering is voluntary and it cannot be used to decide on your application. Leave them blank and JobPilot declines on your behalf."
        onNext={saveAndNext}
        onSkip={next}
        skipLabel="Decline all"
        nextLoading={busy}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          {(
            [
              ['gender', 'Gender'],
              ['race_ethnicity', 'Race / ethnicity'],
              ['veteran_status', 'Veteran status'],
              ['disability_status', 'Disability status'],
            ] as const
          ).map(([key, label]) => (
            <Input
              key={key}
              label={label}
              value={(field(key) as string) ?? ''}
              placeholder="Prefer not to say"
              onChange={(e) => set(key, e.target.value || null)}
            />
          ))}
        </div>
        <p className="mt-4 text-xs text-neutral-400">
          Free text, because every employer words their options differently — JobPilot matches what
          you write against whatever the form offers, and declines if it can’t.
        </p>
      </StepFrame>
    )
  }

  if (stepKey === 'references') {
    return (
      <StepFrame
        {...common}
        eyebrow="References"
        title="Anyone who can vouch for you?"
        subtitle="Optional. Most forms that ask want three, with a phone number and how you know them — adding them here means never typing them again."
        onNext={next}
        onSkip={next}
        nextLabel="Continue"
      >
        <RecommendationsTab items={profile.data?.recommendations ?? []} />
      </StepFrame>
    )
  }

  if (stepKey === 'roles') {
    const count = roles.data?.length ?? 0
    return (
      <StepFrame
        {...common}
        eyebrow="What you’re looking for"
        title="Which jobs do you want?"
        subtitle="Add the titles you’d take — as many as you like. JobPilot searches for each one every few hours, and for the variations of it, then puts the matches in your list to apply to when you’re ready."
        onNext={next}
        nextLabel={count > 0 ? 'Finish' : 'Finish without roles'}
        captureEnter
      >
        <RolesStep />
      </StepFrame>
    )
  }

  // --- done ----------------------------------------------------------------
  const roleList = roles.data ?? []
  return (
    <StepFrame
      {...common}
      title="You’re set up"
      subtitle={
        roleList.length > 0
          ? 'JobPilot is already looking. Matches land in your job list — nothing is applied to until you say so.'
          : 'Add the roles you want any time from the Search page and JobPilot will start looking.'
      }
      nextLabel="Go to my dashboard"
      onNext={finish}
    >
      <div className="flex flex-col items-start gap-5">
        <SpringCheck size="h-10 w-10" />
        {roleList.length > 0 ? (
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
              Searching for
            </p>
            <div className="mt-2">
              <RolesSummary roles={roleList} />
            </div>
          </div>
        ) : null}
        <ul className="space-y-2 text-sm text-neutral-600 dark:text-neutral-300">
          <li className="flex gap-2">
            <Icon name="edit" className="mt-0.5 h-4 w-4 shrink-0 text-neutral-400" />
            <span>
              Everything you entered is in <b>Profile</b>, editable any time.
            </span>
          </li>
          <li className="flex gap-2">
            <Icon name="search" className="mt-0.5 h-4 w-4 shrink-0 text-neutral-400" />
            <span>
              Your roles live under <b>Search</b> — add, edit or remove them there.
            </span>
          </li>
          <li className="flex gap-2">
            <Icon name="laptop" className="mt-0.5 h-4 w-4 shrink-0 text-neutral-400" />
            <span>
              To apply on real employer pages, pair the browser extension in{' '}
              <b>Settings → Extension</b>.
            </span>
          </li>
        </ul>
      </div>
    </StepFrame>
  )
}

/**
 * Résumé step. Upload, parse, then pre-fill — the one screen that removes the
 * most typing, which is why it comes before any form fields.
 */
function ResumeStep({
  stepIndex,
  stepCount,
  onBack,
  onNext,
  onSkip,
  hasResume,
}: {
  stepIndex: number
  stepCount: number
  onBack?: () => void
  onNext: () => void
  onSkip: () => void
  hasResume: boolean
}) {
  const queryClient = useQueryClient()
  const { push } = useToast()
  const [parsed, setParsed] = useState<{ fileId: number; data: ParsedResume } | null>(null)

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData()
      form.append('file', file)
      form.append('kind', 'resume')
      const stored = await api.upload<FileOut>('/api/files', form)
      const data = await api.post<ParsedResume>(`/api/files/${stored.id}/parse`)
      return { fileId: stored.id, data }
    },
    onSuccess: (result) => {
      setParsed(result)
      queryClient.invalidateQueries({ queryKey: qk.files })
    },
    onError: (e) =>
      push({
        title: 'Could not read that file',
        tone: 'error',
        message: e instanceof ApiError ? e.detail : '',
      }),
  })

  const confirm = useMutation({
    mutationFn: () => {
      const body: ConfirmParseRequest = {
        parsed: parsed!.data,
        replace_work_history: true,
        replace_education: true,
      }
      return api.post<FileOut>(`/api/files/${parsed!.fileId}/confirm-parse`, body)
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: qk.profile })
      await queryClient.invalidateQueries({ queryKey: qk.files })
      push({ title: 'Résumé applied', tone: 'success' })
      onNext()
    },
    onError: (e) =>
      push({ title: 'Could not apply it', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })

  const found = useMemo(() => {
    if (!parsed) return [] as [string, number][]
    const d = parsed.data
    return [
      ['Contact details', d.contact ? 1 : 0],
      ['Roles', (d.work_experiences ?? []).length],
      ['Education', (d.educations ?? []).length],
      ['Skills', (d.skills ?? []).length],
    ] as [string, number][]
  }, [parsed])

  return (
    <StepFrame
      stepIndex={stepIndex}
      stepCount={stepCount}
      onBack={onBack}
      eyebrow="Résumé"
      title="Start from your résumé"
      subtitle="Upload it and JobPilot reads it into your profile, so the next screens are you checking details rather than typing them. The file stays on your own server."
      onNext={parsed ? () => confirm.mutate() : onNext}
      nextLabel={parsed ? 'Use these details' : 'Continue'}
      nextLoading={confirm.isPending}
      onSkip={onSkip}
      skipLabel="I’ll type it instead"
    >
      {parsed ? (
        <div className="rounded-2xl border border-neutral-200 p-5 dark:border-neutral-800">
          <div className="flex items-center gap-2">
            <SpringCheck size="h-6 w-6" />
            <p className="text-sm font-medium text-neutral-900 dark:text-neutral-100">
              Read your résumé
            </p>
          </div>
          <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {found.map(([label, n]) => (
              <div key={label} className="rounded-xl bg-neutral-50 px-3 py-2 dark:bg-neutral-800/60">
                <dd className="text-lg font-semibold tabular-nums text-neutral-900 dark:text-neutral-100">
                  {n}
                </dd>
                <dt className="text-[11px] text-neutral-500 dark:text-neutral-400">{label}</dt>
              </div>
            ))}
          </dl>
          <p className="mt-3 text-xs text-neutral-400">
            You’ll check every field on the next screens before any of it is used on a form.
          </p>
          <Button variant="ghost" size="sm" className="mt-3" onClick={() => setParsed(null)}>
            Choose a different file
          </Button>
        </div>
      ) : (
        <>
          <label className="flex cursor-pointer flex-col items-center justify-center rounded-2xl border border-dashed border-neutral-300 px-6 py-12 text-center transition-colors hover:border-accent-400 hover:bg-accent-50/40 dark:border-neutral-700 dark:hover:border-accent-500/50 dark:hover:bg-accent-500/5">
            <input
              type="file"
              accept=".pdf,.docx,.txt"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) upload.mutate(file)
                e.target.value = ''
              }}
            />
            {upload.isPending ? (
              <>
                <Spinner className="h-6 w-6 text-accent-600" />
                <span className="mt-3 text-sm text-neutral-500 dark:text-neutral-400">Reading it…</span>
              </>
            ) : (
              <>
                <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-accent-50 text-accent-600 dark:bg-accent-500/15 dark:text-accent-400">
                  <Icon name="upload" className="h-5 w-5" />
                </span>
                <span className="mt-3 text-sm font-medium text-neutral-900 dark:text-neutral-100">
                  Choose a résumé
                </span>
                <span className="mt-1 text-xs text-neutral-400">PDF, Word or plain text</span>
              </>
            )}
          </label>
          {hasResume ? (
            <p className="mt-3 text-xs text-neutral-500 dark:text-neutral-400">
              You already have a résumé on file — upload a new one to replace what it filled in, or
              just continue.
            </p>
          ) : null}
        </>
      )}
    </StepFrame>
  )
}
