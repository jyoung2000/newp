// Central registry of TanStack Query keys so the WebSocket layer and the
// mutation callbacks invalidate exactly the same keys the queries use.

export const qk = {
  me: ['me'] as const,
  csrf: ['csrf'] as const,
  settings: ['settings'] as const,
  aiSettings: ['settings', 'ai'] as const,
  sessions: ['sessions'] as const,
  users: ['users'] as const,

  profile: ['profile'] as const,
  files: ['files'] as const,
  extensionInfo: ['extension', 'info'] as const,
  customFields: ['custom-fields'] as const,
  savedAnswers: (q?: string) => ['saved-answers', q ?? ''] as const,

  sources: ['search', 'sources'] as const,
  roles: ['roles'] as const,
  rolePreview: (title: string) => ['roles', 'preview', title] as const,
  searchTargets: ['search', 'targets'] as const,
  searchRun: (id: string) => ['search', 'run', id] as const,

  listings: (params: Record<string, unknown>) => ['listings', params] as const,
  listing: (id: number) => ['listing', id] as const,

  runs: ['runs'] as const,
  run: (id: number) => ['run', id] as const,

  applications: (params: Record<string, unknown>) => ['applications', params] as const,
  application: (id: number) => ['application', id] as const,

  interventions: (status: string) => ['interventions', status] as const,
  intervention: (id: number) => ['intervention', id] as const,

  devices: ['devices'] as const,
  analytics: (days: number) => ['analytics', days] as const,
}
