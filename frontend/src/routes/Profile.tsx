import { useSearchParams } from 'react-router-dom'
import { useProfile } from '../lib/hooks'
import { PageHeader } from '../components/PageHeader'
import { Card } from '../components/Card'
import { Badge } from '../components/Badge'
import { Icon, type IconName } from '../components/Icon'
import { SkeletonRows } from '../components/Skeleton'
import { PersonalTab } from '../components/profile/PersonalTab'
import { WorkTab } from '../components/profile/WorkTab'
import { EducationTab } from '../components/profile/EducationTab'
import { RecommendationsTab } from '../components/profile/RecommendationsTab'
import { FilesTab } from '../components/profile/FilesTab'
import { CustomFieldsTab } from '../components/profile/CustomFieldsTab'
import { SavedAnswersTab } from '../components/profile/SavedAnswersTab'
import { cx, titleCase } from '../lib/format'

const TABS: { key: string; label: string; icon: IconName }[] = [
  { key: 'personal', label: 'Personal', icon: 'user' },
  { key: 'work', label: 'Work', icon: 'applications' },
  { key: 'education', label: 'Education', icon: 'onboarding' },
  { key: 'recommendations', label: 'References', icon: 'star' },
  { key: 'files', label: 'Files', icon: 'upload' },
  { key: 'custom', label: 'Custom fields', icon: 'edit' },
  { key: 'answers', label: 'Saved answers', icon: 'inbox' },
]

function Completeness({ pct, missing }: { pct: number; missing: string[] }) {
  const tone = pct >= 80 ? 'bg-emerald-500' : pct >= 50 ? 'bg-accent-600' : 'bg-amber-500'
  return (
    <Card>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-neutral-700 dark:text-neutral-300">Profile completeness</p>
          <p className="text-xs text-neutral-400">A fuller profile means fewer questions during applications.</p>
        </div>
        <span className="text-2xl font-semibold tabular-nums text-neutral-900 dark:text-neutral-100">{pct}%</span>
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-800">
        <div className={cx('h-full rounded-full transition-[width] duration-700', tone)} style={{ width: `${pct}%` }} />
      </div>
      {missing.length > 0 ? (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-neutral-400">Still missing:</span>
          {missing.slice(0, 8).map((m) => (
            <Badge key={m} tone="neutral">
              {titleCase(m)}
            </Badge>
          ))}
        </div>
      ) : null}
    </Card>
  )
}

export function Profile() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || 'personal'
  const profile = useProfile()

  const setTab = (key: string) => {
    params.set('tab', key)
    setParams(params, { replace: true })
  }

  const data = profile.data

  return (
    <div>
      <PageHeader title="Profile" subtitle="Everything JobPilot uses to fill applications" />

      {data ? <Completeness pct={data.completeness} missing={data.completeness_missing} /> : null}

      <div className="mt-5 -mx-1 overflow-x-auto pb-1">
        <div className="flex min-w-max gap-1 rounded-xl border border-neutral-200 bg-white p-1 dark:border-neutral-800 dark:bg-neutral-900">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={cx(
                'inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                tab === t.key
                  ? 'bg-accent-600 text-white shadow-sm'
                  : 'text-neutral-600 hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-800',
              )}
            >
              <Icon name={t.icon} className="h-4 w-4" />
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-5">
        {tab === 'personal' ? (
          data ? <PersonalTab profile={data.profile} /> : <SkeletonRows rows={5} />
        ) : tab === 'work' ? (
          data ? <WorkTab items={data.work_experiences} /> : <SkeletonRows rows={4} />
        ) : tab === 'education' ? (
          data ? <EducationTab items={data.educations} /> : <SkeletonRows rows={3} />
        ) : tab === 'recommendations' ? (
          data ? <RecommendationsTab items={data.recommendations} /> : <SkeletonRows rows={3} />
        ) : tab === 'files' ? (
          <FilesTab />
        ) : tab === 'custom' ? (
          <CustomFieldsTab />
        ) : tab === 'answers' ? (
          <SavedAnswersTab />
        ) : null}
      </div>
    </div>
  )
}
