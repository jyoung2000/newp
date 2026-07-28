import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { qk } from '../lib/queryKeys'
import { useProfile, useFiles, useDevices, useUserSettings } from '../lib/hooks'
import type { ApplicationOut, ListingOut, UserSettings } from '../lib/types'
import { PageHeader } from '../components/PageHeader'
import { Card } from '../components/Card'
import { Button } from '../components/Button'
import { Icon, type IconName } from '../components/Icon'
import { SpringCheck } from '../components/SpringCheck'
import { cx } from '../lib/format'

interface Step {
  key: string
  title: string
  description: string
  icon: IconName
  to: string
  cta: string
  done: boolean
}

export function Onboarding() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const profile = useProfile()
  const files = useFiles()
  const devices = useDevices()
  const settings = useUserSettings()

  const listings = useQuery({
    queryKey: qk.listings({ probe: 1 }),
    queryFn: () => api.get<ListingOut[]>('/api/listings?limit=1'),
  })
  const applications = useQuery({
    queryKey: qk.applications({ probe: 1 }),
    queryFn: () => api.get<ApplicationOut[]>('/api/applications?limit=1'),
  })

  const dismiss = useMutation({
    mutationFn: () =>
      api.put<UserSettings>('/api/auth/settings', {
        ...(settings.data ?? {}),
        onboarding_dismissed: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.settings })
      navigate('/')
    },
  })

  const p = profile.data?.profile
  const profileDone = Boolean(p?.first_name && p?.last_name && p?.email)
  const resumeDone = Boolean(files.data?.some((f) => f.is_default_resume || f.parse_confirmed))
  const extensionDone = Boolean(devices.data && devices.data.length > 0)
  const searchDone = Boolean(listings.data && listings.data.length > 0)
  const appliedDone = Boolean(applications.data && applications.data.length > 0)

  const steps: Step[] = [
    {
      key: 'profile',
      title: 'Complete your profile',
      description: 'Add your name, contact details and work history — the answers JobPilot fills forms with.',
      icon: 'profile',
      to: '/profile',
      cta: 'Edit profile',
      done: profileDone,
    },
    {
      key: 'resume',
      title: 'Upload & confirm your resume',
      description: 'Upload a resume, then review the parsed structure before it becomes your default.',
      icon: 'upload',
      to: '/profile?tab=files',
      cta: 'Upload resume',
      done: resumeDone,
    },
    {
      key: 'extension',
      title: 'Install & pair the browser extension',
      description: 'The extension applies on real employer pages from your own browser. Pair it with a code.',
      icon: 'laptop',
      to: '/settings?section=extension',
      cta: 'Set up extension',
      done: extensionDone,
    },
    {
      key: 'search',
      title: 'Run your first search',
      description: 'Search real openings across the sources you have permission to use.',
      icon: 'search',
      to: '/search',
      cta: 'Search jobs',
      done: searchDone,
    },
    {
      key: 'apply',
      title: 'Apply to your first job',
      description: 'Pick a listing and let JobPilot fill the application — you stay in control of every step.',
      icon: 'sparkles',
      to: '/listings',
      cta: 'Browse listings',
      done: appliedDone,
    },
  ]

  const doneCount = steps.filter((s) => s.done).length
  const pct = Math.round((doneCount / steps.length) * 100)
  const allDone = doneCount === steps.length

  return (
    <div>
      <PageHeader
        title="Get started"
        subtitle="Five steps to your first automated application"
        actions={
          <Button variant="ghost" onClick={() => dismiss.mutate()} loading={dismiss.isPending}>
            Skip for now
          </Button>
        }
      />

      <Card className="mb-6">
        <div className="flex items-center gap-4">
          <div className="relative flex h-14 w-14 shrink-0 items-center justify-center">
            <svg viewBox="0 0 36 36" className="h-14 w-14 -rotate-90">
              <circle cx="18" cy="18" r="15.5" fill="none" strokeWidth="3" className="stroke-neutral-200 dark:stroke-neutral-800" />
              <circle
                cx="18"
                cy="18"
                r="15.5"
                fill="none"
                strokeWidth="3"
                strokeLinecap="round"
                className="stroke-accent-600 transition-[stroke-dashoffset] duration-700"
                strokeDasharray={2 * Math.PI * 15.5}
                strokeDashoffset={2 * Math.PI * 15.5 * (1 - pct / 100)}
              />
            </svg>
            <span className="absolute text-sm font-semibold tabular-nums text-neutral-800 dark:text-neutral-100">
              {pct}%
            </span>
          </div>
          <div>
            <p className="text-base font-semibold text-neutral-900 dark:text-neutral-100">
              {allDone ? 'You’re all set!' : `${doneCount} of ${steps.length} steps done`}
            </p>
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              {allDone
                ? 'Your workspace is ready. Head to the dashboard any time.'
                : 'Finish setup to unlock the full workflow.'}
            </p>
          </div>
          {allDone ? (
            <Link to="/" className="ml-auto">
              <Button variant="primary" iconRight="arrowRight">
                Go to dashboard
              </Button>
            </Link>
          ) : null}
        </div>
      </Card>

      <ol className="space-y-3">
        {steps.map((step, i) => (
          <li key={step.key}>
            <Card padded={false} className={cx('p-4 sm:p-5', step.done && 'opacity-80')}>
              <div className="flex items-center gap-4">
                <div className="shrink-0">
                  {step.done ? (
                    <SpringCheck size="h-10 w-10" />
                  ) : (
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-neutral-100 text-sm font-semibold text-neutral-500 ring-1 ring-neutral-200 dark:bg-neutral-800 dark:text-neutral-400 dark:ring-neutral-700">
                      {i + 1}
                    </div>
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <Icon name={step.icon} className="h-4 w-4 text-accent-600 dark:text-accent-400" />
                    <h3 className={cx('font-semibold text-neutral-900 dark:text-neutral-100', step.done && 'line-through decoration-neutral-300')}>
                      {step.title}
                    </h3>
                  </div>
                  <p className="mt-0.5 text-sm text-neutral-500 dark:text-neutral-400">{step.description}</p>
                </div>
                <div className="shrink-0">
                  <Link to={step.to}>
                    <Button variant={step.done ? 'ghost' : 'secondary'} size="sm" iconRight={step.done ? undefined : 'chevronRight'}>
                      {step.done ? 'Review' : step.cta}
                    </Button>
                  </Link>
                </div>
              </div>
            </Card>
          </li>
        ))}
      </ol>
    </div>
  )
}
