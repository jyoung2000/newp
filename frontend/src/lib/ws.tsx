import { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAuth } from './auth'
import { useToast } from './toast'
import { qk } from './queryKeys'

// Messages emitted by /ws/ui. Loosely typed by design — the backend sends a
// free-form dict; we key off `type` and read known fields defensively.
interface WsMessage {
  type: string
  [key: string]: unknown
}

interface RealtimeContextValue {
  connected: boolean
}

const RealtimeContext = createContext<RealtimeContextValue>({ connected: false })

function wsUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}/ws/ui`
}

function asNumber(v: unknown): number | undefined {
  return typeof v === 'number' ? v : undefined
}
function asString(v: unknown): string | undefined {
  return typeof v === 'string' ? v : undefined
}

export function RealtimeProvider({ children }: { children: React.ReactNode }) {
  const { status } = useAuth()
  const queryClient = useQueryClient()
  const { push } = useToast()
  const [connected, setConnected] = useState(false)

  const wsRef = useRef<WebSocket | null>(null)
  const pingRef = useRef<number | null>(null)
  const reconnectRef = useRef<number | null>(null)
  const attemptsRef = useRef(0)
  const closedRef = useRef(false)

  useEffect(() => {
    if (status !== 'authed') return
    closedRef.current = false

    const clearTimers = () => {
      if (pingRef.current) window.clearInterval(pingRef.current)
      if (reconnectRef.current) window.clearTimeout(reconnectRef.current)
      pingRef.current = null
      reconnectRef.current = null
    }

    const handle = (msg: WsMessage) => {
      switch (msg.type) {
        case 'badge': {
          // The open-interventions count changed; refresh the always-mounted
          // inbox query that feeds the sidebar badge.
          queryClient.invalidateQueries({ queryKey: ['interventions'] })
          break
        }
        case 'search.progress': {
          const runId = asString(msg.run_id)
          if (runId) queryClient.invalidateQueries({ queryKey: qk.searchRun(runId) })
          break
        }
        case 'application.status': {
          const appId = asNumber(msg.application_id)
          queryClient.invalidateQueries({ queryKey: ['applications'] })
          queryClient.invalidateQueries({ queryKey: qk.runs })
          if (appId) queryClient.invalidateQueries({ queryKey: qk.application(appId) })
          break
        }
        case 'intervention.answered': {
          queryClient.invalidateQueries({ queryKey: ['interventions'] })
          queryClient.invalidateQueries({ queryKey: ['applications'] })
          const id = asNumber(msg.intervention_id)
          if (id) queryClient.invalidateQueries({ queryKey: qk.intervention(id) })
          break
        }
        case 'notification': {
          const interventionId = asNumber(msg.intervention_id)
          push({
            title: asString(msg.title) || 'JobPilot',
            message: asString(msg.message),
            tone: 'info',
            href: interventionId ? `/interventions?focus=${interventionId}` : undefined,
            actionLabel: interventionId ? 'Open' : undefined,
          })
          // A notification usually means new interventions — refresh the inbox.
          queryClient.invalidateQueries({ queryKey: ['interventions'] })
          break
        }
        case 'run.created':
        case 'run.paused':
        case 'run.resumed':
        case 'run.stopped':
        case 'run.finished':
        case 'run.updated': {
          queryClient.invalidateQueries({ queryKey: qk.runs })
          queryClient.invalidateQueries({ queryKey: ['applications'] })
          break
        }
        default:
          break
      }
    }

    const connect = () => {
      if (closedRef.current) return
      let socket: WebSocket
      try {
        socket = new WebSocket(wsUrl())
      } catch {
        scheduleReconnect()
        return
      }
      wsRef.current = socket

      socket.onopen = () => {
        attemptsRef.current = 0
        setConnected(true)
        if (pingRef.current) window.clearInterval(pingRef.current)
        pingRef.current = window.setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: 'ping' }))
          }
        }, 30000)
      }

      socket.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data as string) as WsMessage
          if (data && typeof data.type === 'string') handle(data)
        } catch {
          /* ignore malformed frames */
        }
      }

      socket.onclose = () => {
        setConnected(false)
        if (pingRef.current) window.clearInterval(pingRef.current)
        pingRef.current = null
        scheduleReconnect()
      }

      socket.onerror = () => {
        // onclose will follow and schedule the reconnect.
        try {
          socket.close()
        } catch {
          /* ignore */
        }
      }
    }

    const scheduleReconnect = () => {
      if (closedRef.current) return
      attemptsRef.current += 1
      const delay = Math.min(30000, 1000 * 2 ** Math.min(attemptsRef.current, 5))
      reconnectRef.current = window.setTimeout(connect, delay)
    }

    connect()

    return () => {
      closedRef.current = true
      clearTimers()
      const s = wsRef.current
      wsRef.current = null
      if (s) {
        s.onclose = null
        s.onerror = null
        try {
          s.close()
        } catch {
          /* ignore */
        }
      }
      setConnected(false)
    }
  }, [status, queryClient, push])

  const value = useMemo<RealtimeContextValue>(() => ({ connected }), [connected])
  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>
}

export function useRealtime(): RealtimeContextValue {
  return useContext(RealtimeContext)
}
