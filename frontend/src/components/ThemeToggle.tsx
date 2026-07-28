import { useTheme, type ThemePref } from '../lib/theme'
import { Icon, type IconName } from './Icon'

const NEXT: Record<ThemePref, ThemePref> = { system: 'light', light: 'dark', dark: 'system' }
const ICON: Record<ThemePref, IconName> = { system: 'monitor', light: 'sun', dark: 'moon' }
const LABEL: Record<ThemePref, string> = { system: 'System theme', light: 'Light theme', dark: 'Dark theme' }

export function ThemeToggle() {
  const { pref, setPref } = useTheme()
  return (
    <button
      type="button"
      onClick={() => setPref(NEXT[pref])}
      className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-neutral-200 text-neutral-600 transition-colors hover:bg-neutral-100 dark:border-neutral-800 dark:text-neutral-300 dark:hover:bg-neutral-800"
      title={`${LABEL[pref]} — click to change`}
      aria-label={`Theme: ${LABEL[pref]}. Click to change.`}
    >
      <Icon name={ICON[pref]} className="h-[18px] w-[18px]" />
    </button>
  )
}
