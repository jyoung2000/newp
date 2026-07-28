import { Link } from 'react-router-dom'
import { useToast, type ToastTone } from '../lib/toast'
import { Icon, type IconName } from './Icon'
import { cx } from '../lib/format'

const TONE_ICON: Record<ToastTone, IconName> = {
  info: 'info',
  success: 'checkCircle',
  warning: 'alert',
  error: 'alert',
}
const TONE_ACCENT: Record<ToastTone, string> = {
  info: 'text-accent-500',
  success: 'text-emerald-500',
  warning: 'text-amber-500',
  error: 'text-red-500',
}

export function Toaster() {
  const { toasts, dismiss } = useToast()
  if (toasts.length === 0) return null
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-[60] flex flex-col items-center gap-2 p-4 sm:right-4 sm:left-auto sm:items-end">
      {toasts.map((t) => (
        <div
          key={t.id}
          role="status"
          className="pointer-events-auto w-full max-w-sm animate-slide-up overflow-hidden rounded-xl border border-neutral-200 bg-white/95 shadow-lg backdrop-blur dark:border-neutral-800 dark:bg-neutral-900/95"
        >
          <div className="flex gap-3 p-3.5">
            <Icon name={TONE_ICON[t.tone]} className={cx('mt-0.5 h-5 w-5', TONE_ACCENT[t.tone])} />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">{t.title}</p>
              {t.message ? (
                <p className="mt-0.5 text-sm text-neutral-600 dark:text-neutral-400">{t.message}</p>
              ) : null}
              {t.href ? (
                <Link
                  to={t.href}
                  onClick={() => dismiss(t.id)}
                  className="mt-1.5 inline-block text-xs font-semibold text-accent-600 hover:underline dark:text-accent-400"
                >
                  {t.actionLabel || 'View'} →
                </Link>
              ) : null}
            </div>
            <button
              onClick={() => dismiss(t.id)}
              className="rounded-lg p-1 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-600 dark:hover:bg-neutral-800"
              aria-label="Dismiss notification"
            >
              <Icon name="close" className="h-4 w-4" />
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
