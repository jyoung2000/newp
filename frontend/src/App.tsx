import { createBrowserRouter, Outlet } from 'react-router-dom'
import { BareAuthedLayout, ProtectedLayout } from './components/Shell'
import { Toaster } from './components/Toaster'
import { Login } from './routes/Login'
import { Register } from './routes/Register'
import { Dashboard } from './routes/Dashboard'
import { Onboarding } from './routes/Onboarding'
import { Search } from './routes/Search'
import { Listings } from './routes/Listings'
import { Queue } from './routes/Queue'
import { Interventions } from './routes/Interventions'
import { Applications } from './routes/Applications'
import { Profile } from './routes/Profile'
import { Settings } from './routes/Settings'
import { Users } from './routes/Users'
import { NotFound } from './routes/NotFound'

// Root layout so global chrome (toasts) lives inside the router context and
// can use <Link> safely.
function RootLayout() {
  return (
    <>
      <Outlet />
      <Toaster />
    </>
  )
}

export const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
      { path: '/login', element: <Login /> },
      { path: '/register', element: <Register /> },
      {
        // Full-screen, no sidebar: setup is its own room.
        element: <BareAuthedLayout />,
        children: [{ path: '/onboarding', element: <Onboarding /> }],
      },
      {
        element: <ProtectedLayout />,
        children: [
          { path: '/', element: <Dashboard /> },
          { path: '/search', element: <Search /> },
          { path: '/listings', element: <Listings /> },
          { path: '/queue', element: <Queue /> },
          { path: '/interventions', element: <Interventions /> },
          { path: '/applications', element: <Applications /> },
          { path: '/profile', element: <Profile /> },
          { path: '/settings', element: <Settings /> },
          { path: '/users', element: <Users /> },
          { path: '*', element: <NotFound /> },
        ],
      },
    ],
  },
])
