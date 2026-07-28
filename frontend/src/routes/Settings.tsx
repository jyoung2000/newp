import { useSearchParams } from 'react-router-dom'
import { useUserSettings } from '../lib/hooks'
import { PageHeader } from '../components/PageHeader'
import { Icon, type IconName } from '../components/Icon'
import { SkeletonRows } from '../components/Skeleton'
import { SecuritySection } from '../components/settings/SecuritySection'
import { AISection } from '../components/settings/AISection'
import { ExtensionSection } from '../components/settings/ExtensionSection'
import { PreferencesSection } from '../components/settings/PreferencesSection'
import { DataSection } from '../components/settings/DataSection'
import { DangerSection } from '../components/settings/DangerSection'
import { cx } from '../lib/format'

const SECTIONS: { key: string; label: string; icon: IconName }[] = [
  { key: 'security', label: 'Security', icon: 'lock' },
  { key: 'ai', label: 'AI', icon: 'sparkles' },
  { key: 'extension', label: 'Extension', icon: 'laptop' },
  { key: 'preferences', label: 'Preferences', icon: 'settings' },
  { key: 'data', label: 'Data', icon: 'download' },
  { key: 'danger', label: 'Danger zone', icon: 'alert' },
]

export function Settings() {
  const [params, setParams] = useSearchParams()
  const section = params.get('section') || 'security'
  const settings = useUserSettings()

  const setSection = (key: string) => {
    params.set('section', key)
    setParams(params, { replace: true })
  }

  return (
    <div>
      <PageHeader title="Settings" subtitle="Security, AI, extension, preferences and your data" />

      <div className="-mx-1 overflow-x-auto pb-1">
        <div className="flex min-w-max gap-1 rounded-xl border border-neutral-200 bg-white p-1 dark:border-neutral-800 dark:bg-neutral-900">
          {SECTIONS.map((sct) => (
            <button
              key={sct.key}
              onClick={() => setSection(sct.key)}
              className={cx(
                'inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                section === sct.key
                  ? 'bg-accent-600 text-white shadow-sm'
                  : 'text-neutral-600 hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-800',
              )}
            >
              <Icon name={sct.icon} className="h-4 w-4" />
              {sct.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-5">
        {section === 'security' ? (
          <SecuritySection />
        ) : section === 'ai' ? (
          <AISection />
        ) : section === 'extension' ? (
          <ExtensionSection />
        ) : section === 'preferences' ? (
          settings.data ? <PreferencesSection initial={settings.data} /> : <SkeletonRows rows={4} />
        ) : section === 'data' ? (
          <DataSection />
        ) : section === 'danger' ? (
          <DangerSection />
        ) : null}
      </div>
    </div>
  )
}
