import { NavLink } from 'react-router-dom'
import { NAV_ITEMS } from './nav'
import { Icon } from './Icon'
import { cx, initials } from '../lib/format'
import { useAuth } from '../lib/auth'
import { Button } from './Button'

function BadgeCount({ count }: { count: number }) {
  if (count <= 0) return null
  return (
    <span className="ml-auto inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-accent-600 px-1.5 text-[11px] font-semibold text-white">
      {count > 99 ? '99+' : count}
    </span>
  )
}

export function Sidebar({ badgeCount }: { badgeCount: number }) {
  const { user, logout } = useAuth()
  return (
    <aside className="hidden w-64 shrink-0 flex-col border-r border-neutral-200/70 bg-white/70 backdrop-blur-xl lg:flex dark:border-neutral-800/70 dark:bg-neutral-900/60">
      <div className="flex h-16 items-center gap-2.5 px-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent-600 text-white shadow-sm">
          <Icon name="onboarding" className="h-5 w-5" />
        </div>
        <span className="text-lg font-semibold tracking-tightheading text-neutral-900 dark:text-white">
          JobPilot
        </span>
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-2">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              cx(
                'group flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-accent-50 text-accent-700 dark:bg-accent-500/15 dark:text-accent-300'
                  : 'text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900 dark:text-neutral-400 dark:hover:bg-neutral-800 dark:hover:text-neutral-100',
              )
            }
          >
            <Icon name={item.icon} className="h-5 w-5" />
            <span>{item.label}</span>
            {item.badge ? <BadgeCount count={badgeCount} /> : null}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-neutral-200/70 p-3 dark:border-neutral-800/70">
        <div className="flex items-center gap-3 rounded-xl px-2 py-1.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-neutral-200 text-sm font-semibold text-neutral-700 dark:bg-neutral-700 dark:text-neutral-200">
            {initials(null, null, user?.email)}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-neutral-800 dark:text-neutral-200">
              {user?.email}
            </p>
            <p className="text-xs text-neutral-400">Self-hosted</p>
          </div>
        </div>
        <Button variant="ghost" size="sm" icon="logout" block className="mt-1 justify-start" onClick={() => void logout()}>
          Sign out
        </Button>
      </div>
    </aside>
  )
}
