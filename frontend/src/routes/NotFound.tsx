import { Link } from 'react-router-dom'
import { Button } from '../components/Button'

export function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <p className="text-6xl font-semibold tracking-tightheading text-neutral-300 dark:text-neutral-700">404</p>
      <h1 className="mt-4 text-xl font-semibold text-neutral-900 dark:text-neutral-100">Page not found</h1>
      <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
        This part of JobPilot doesn’t exist.
      </p>
      <Link to="/" className="mt-6">
        <Button variant="primary" icon="dashboard">
          Back to dashboard
        </Button>
      </Link>
    </div>
  )
}
