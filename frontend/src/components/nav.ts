import type { IconName } from './Icon'

export interface NavItem {
  to: string
  label: string
  icon: IconName
  badge?: boolean
  end?: boolean
  // Rendered only for the head admin (see Sidebar / MobileNav).
  adminOnly?: boolean
}

export const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: 'dashboard', end: true },
  { to: '/search', label: 'Search', icon: 'search' },
  { to: '/listings', label: 'Listings', icon: 'listings' },
  { to: '/queue', label: 'Queue', icon: 'queue' },
  { to: '/interventions', label: 'Interventions', icon: 'inbox', badge: true },
  { to: '/applications', label: 'Applications', icon: 'applications' },
  { to: '/profile', label: 'Profile', icon: 'profile' },
  { to: '/settings', label: 'Settings', icon: 'settings' },
  { to: '/users', label: 'Users', icon: 'user', adminOnly: true },
]

// Primary items surfaced in the mobile bottom bar (the rest live in the menu).
export const MOBILE_PRIMARY: string[] = ['/', '/listings', '/interventions', '/applications']
