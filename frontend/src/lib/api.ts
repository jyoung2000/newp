// Small typed fetch wrapper. All requests are same-origin with the session
// cookie; mutations carry the CSRF header. Non-2xx responses throw ApiError
// with the backend's {detail} message parsed out.

export class ApiError extends Error {
  status: number
  detail: string
  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

// CSRF token is held in memory and injected on mutating requests. The auth
// layer sets it after login / csrf fetch.
let csrfToken: string | null = null
export function setCsrfToken(token: string | null): void {
  csrfToken = token
}
export function getCsrfToken(): string | null {
  return csrfToken
}

// A single subscriber (the auth provider) is notified on any 401 so it can
// bounce the user to the login screen.
type UnauthorizedHandler = () => void
let onUnauthorized: UnauthorizedHandler | null = null
export function setUnauthorizedHandler(fn: UnauthorizedHandler | null): void {
  onUnauthorized = fn
}

const MUTATING = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

interface RequestOptions {
  body?: unknown
  signal?: AbortSignal
  // When true, the body is sent as-is (FormData) and Content-Type is left to
  // the browser so the multipart boundary is set correctly.
  raw?: boolean
}

async function parseError(res: Response): Promise<never> {
  let detail = res.statusText || `Request failed (${res.status})`
  try {
    const data = (await res.json()) as unknown
    if (data && typeof data === 'object' && 'detail' in data) {
      const d = (data as { detail: unknown }).detail
      if (typeof d === 'string') detail = d
      else if (Array.isArray(d) && d.length > 0) {
        // FastAPI validation errors: array of {loc, msg}.
        const first = d[0] as { msg?: string }
        if (first?.msg) detail = first.msg
      }
    }
  } catch {
    // Non-JSON error body; keep the status text.
  }
  throw new ApiError(res.status, detail)
}

async function request<T>(method: Method, path: string, opts: RequestOptions = {}): Promise<T> {
  const headers = new Headers()
  let body: BodyInit | undefined

  if (opts.body !== undefined) {
    if (opts.raw) {
      body = opts.body as BodyInit
    } else {
      headers.set('Content-Type', 'application/json')
      body = JSON.stringify(opts.body)
    }
  }

  if (MUTATING.has(method) && csrfToken) {
    headers.set('x-csrf-token', csrfToken)
  }

  const res = await fetch(path, {
    method,
    credentials: 'include',
    headers,
    body,
    signal: opts.signal,
  })

  if (res.status === 401) {
    if (onUnauthorized) onUnauthorized()
    await parseError(res)
  }
  if (!res.ok) {
    await parseError(res)
  }

  if (res.status === 204) return undefined as T
  const contentType = res.headers.get('content-type') || ''
  if (!contentType.includes('application/json')) {
    // Some endpoints (blobs, empty bodies) — return undefined; callers that
    // need bytes use apiBlob instead.
    return undefined as T
  }
  return (await res.json()) as T
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => request<T>('GET', path, { signal }),
  post: <T>(path: string, body?: unknown, signal?: AbortSignal) =>
    request<T>('POST', path, { body, signal }),
  put: <T>(path: string, body?: unknown, signal?: AbortSignal) =>
    request<T>('PUT', path, { body, signal }),
  patch: <T>(path: string, body?: unknown, signal?: AbortSignal) =>
    request<T>('PATCH', path, { body, signal }),
  del: <T>(path: string, body?: unknown, signal?: AbortSignal) =>
    request<T>('DELETE', path, { body, signal }),
  // Multipart form upload (files, imports).
  upload: <T>(path: string, form: FormData, method: 'POST' | 'PUT' = 'POST') =>
    request<T>(method, path, { body: form, raw: true }),
}

// Fetch raw bytes (screenshots, exports) with cookie auth. Returns an object
// URL the caller is responsible for revoking.
export async function apiBlob(path: string, signal?: AbortSignal): Promise<Blob> {
  const res = await fetch(path, { credentials: 'include', signal })
  if (!res.ok) await parseError(res)
  return res.blob()
}

// Build a query string from a record, dropping null/undefined/empty values.
export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const usp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === '') continue
    usp.set(k, String(v))
  }
  const s = usp.toString()
  return s ? `?${s}` : ''
}
