import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { MOBILE_PRIMARY, NAV_ITEMS } from './nav'
import { Icon } from './Icon'
import { cx, initials } from '../lib/format'
import { useAuth } from '../lib/auth'
import { Button } from './Button'

function Dot({ count }: { count: number }) {
  if (count <= 0) return null
  return (
    <span className="absolute -right-1 -top-1 inline-flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-accent-600 px-1 text-[10px] font-semibold text-white">
      {count > 9 ? '9+' : count}
    </span>
  )
}

export function MobileNav({ badgeCount }: { badgeCount: number }) {
  const [menuOpen, setMenuOpen] = useState(false)
  const { user, logout } = useAuth()
  const primary = NAV_ITEMS.filter((i) => MOBILE_PRIMARY.includes(i.to))

  return (
    <>
      <nav className="fixed inset-x-0 bottom-0 z-40 flex items-stretch border-t border-neutral-200/70 bg-white/85 backdrop-blur-xl lg:hidden dark:border-neutral-800/70 dark:bg-neutral-900/85">
        {primary.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              cx(
                'flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] font-medium',
                isActive ? 'text-accent-600 dark:text-accent-400' : 'text-neutral-500 dark:text-neutral-400',
              )
            }
          >
            <span className="relative">
              <Icon name={item.icon} className="h-5 w-5" />
              {item.badge ? <Dot count={badgeCount} /> : null}
            </span>
            {item.label}
          </NavLink>
        ))}
        <button
          onClick={() => setMenuOpen(true)}
          className="flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] font-medium text-neutral-500 dark:text-neutral-400"
        >
          <Icon name="menu" className="h-5 w-5" />
          More
        </button>
      </nav>

      {menuOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true">
          <div className="absolute inset-0 animate-fade-in bg-black/40 backdrop-blur-sm" onClick={() => setMenuOpen(false)} />
          <div className="absolute inset-x-0 bottom-0 animate-slide-up rounded-t-2xl bg-white p-4 pb-6 dark:bg-neutral-900">
            <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-neutral-300 dark:bg-neutral-700" />
            <div className="mb-3 flex items-center gap-3 px-1">
              <div className="flex h-9 w-9 items-center justify-center rounded-full bg-neutral-200 text-sm font-semibold text-neutral-700 dark:bg-neutral-700 dark:text-neutral-200">
                {initials(null, null, user?.email)}
              </div>
              <p className="truncate text-sm font-medium text-neutral-800 dark:text-neutral-200">{user?.email}</p>
            </div>
            <div className="grid grid-cols-3 gap-2">
              {NAV_ITEMS.filter((i) => !i.adminOnly || user?.is_admin).map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  onClick={() => setMenuOpen(false)}
                  className={({ isActive }) =>
                    cx(
                      'flex flex-col items-center gap-1.5 rounded-xl border p-3 text-xs font-medium',
                      isActive
                        ? 'border-accent-200 bg-accent-50 text-accent-700 dark:border-accent-500/30 dark:bg-accent-500/15 dark:text-accent-300'
                        : 'border-neutral-200 text-neutral-600 dark:border-neutral-800 dark:text-neutral-300',
                    )
                  }
                >
                  <span className="relative">
                    <Icon name={item.icon} className="h-5 w-5" />
                    {item.badge ? <Dot count={badgeCount} /> : null}
                  </span>
                  {item.label}
                </NavLink>
              ))}
            </div>
            <Button
              variant="ghost"
              icon="logout"
              block
              className="mt-3 justify-center"
              onClick={() => {
                setMenuOpen(false)
                void logout()
              }}
            >
              Sign out
            </Button>
          </div>
        </div>
      ) : null}
    </>
  )
}
