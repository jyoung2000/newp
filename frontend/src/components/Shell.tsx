import { Navigate, Outlet } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '../lib/auth'
import { RealtimeProvider } from '../lib/ws'
import { api } from '../lib/api'
import { qk } from '../lib/queryKeys'
import type { InterventionOut } from '../lib/types'
import { Sidebar } from './Sidebar'
import { MobileNav } from './MobileNav'
import { TopBar } from './TopBar'
import { Spinner } from './Spinner'

function Shell() {
  // Always-mounted query that drives the sidebar interventions badge. The
  // realtime layer invalidates ['interventions'] so this stays live.
  const { data: openInterventions } = useQuery({
    queryKey: qk.interventions('open'),
    queryFn: () => api.get<InterventionOut[]>('/api/interventions?status=open'),
    refetchInterval: 30000,
  })
  const badgeCount = openInterventions?.length ?? 0

  return (
    <div className="flex h-full">
      <Sidebar badgeCount={badgeCount} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="flex-1 overflow-y-auto pb-20 lg:pb-0">
          <div className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
            <Outlet />
          </div>
        </main>
      </div>
      <MobileNav badgeCount={badgeCount} />
    </div>
  )
}

/**
 * Signed-in, but without the app chrome. The onboarding flow is full-screen
 * and carries its own header — nesting it in the Shell would give it two.
 */
export function BareAuthedLayout() {
  const { status } = useAuth()
  if (status === 'loading') {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner className="h-6 w-6 text-accent-600" />
      </div>
    )
  }
  if (status === 'anon') return <Navigate to="/login" replace />
  return <Outlet />
}


export function ProtectedLayout() {
  const { status } = useAuth()

  if (status === 'loading') {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner className="h-6 w-6 text-accent-600" />
      </div>
    )
  }
  if (status === 'anon') {
    return <Navigate to="/login" replace />
  }
  return (
    <RealtimeProvider>
      <Shell />
    </RealtimeProvider>
  )
}
