// WebSocket composable for dispatch orchestration layer (ADR-0004).
// Manages a single persistent WebSocket connection, subscriptions, and event dispatching.

import { ref, onUnmounted, readonly } from 'vue'

const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:18000'
const wsBase = apiBase.replace(/^http/, 'ws')

const socket = ref(null)
const connected = ref(false)
const connectionError = ref('')
const listeners = new Map() // event_type -> Set<callback>
const subscribedTaskIds = new Set()
const pendingMessages = []

let reconnectTimer = null
let reconnectAttempts = 0
const MAX_RECONNECT_ATTEMPTS = 10
const RECONNECT_BASE_MS = 1000

function sendRaw(data) {
  if (socket.value && socket.value.readyState === WebSocket.OPEN) {
    socket.value.send(JSON.stringify(data))
    return true
  }
  return false
}

function flushPendingMessages() {
  while (pendingMessages.length > 0) {
    const next = pendingMessages.shift()
    if (!sendRaw(next)) {
      pendingMessages.unshift(next)
      break
    }
  }
}

function replaySubscriptions() {
  for (const taskId of subscribedTaskIds) {
    sendRaw({ action: 'subscribe_task', task_id: taskId })
  }
}

function connect() {
  if (socket.value && (socket.value.readyState === WebSocket.OPEN || socket.value.readyState === WebSocket.CONNECTING)) {
    return
  }

  const url = `${wsBase}/api/v1/ws`
  const ws = new WebSocket(url)

  ws.onopen = () => {
    connected.value = true
    connectionError.value = ''
    reconnectAttempts = 0
    replaySubscriptions()
    flushPendingMessages()
  }

  ws.onclose = () => {
    connected.value = false
    socket.value = null
    scheduleReconnect()
  }

  ws.onerror = () => {
    connectionError.value = 'WebSocket connection failed'
  }

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      const eventType = data.event_type || data.type
      if (eventType && listeners.has(eventType)) {
        for (const cb of listeners.get(eventType)) {
          cb(data)
        }
      }
      // Also notify wildcard listeners
      if (listeners.has('*')) {
        for (const cb of listeners.get('*')) {
          cb(data)
        }
      }
    } catch {
      // Ignore malformed messages
    }
  }

  socket.value = ws
}

function scheduleReconnect() {
  if (reconnectTimer) return
  if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) return

  const delay = RECONNECT_BASE_MS * Math.pow(2, Math.min(reconnectAttempts, 5))
  reconnectAttempts++

  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    connect()
  }, delay)
}

function disconnect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  if (socket.value) {
    socket.value.close()
    socket.value = null
  }
  connected.value = false
}

function send(data) {
  if (sendRaw(data)) {
    return true
  }
  pendingMessages.push(data)
  return false
}

function subscribe(taskId) {
  if (!taskId) return false
  subscribedTaskIds.add(taskId)
  return sendRaw({ action: 'subscribe_task', task_id: taskId })
}

function unsubscribe(taskId) {
  if (!taskId) return false
  subscribedTaskIds.delete(taskId)
  return sendRaw({ action: 'unsubscribe_task', task_id: taskId })
}

function on(eventType, callback) {
  if (!listeners.has(eventType)) {
    listeners.set(eventType, new Set())
  }
  listeners.get(eventType).add(callback)
}

function off(eventType, callback) {
  if (listeners.has(eventType)) {
    listeners.get(eventType).delete(callback)
    if (listeners.get(eventType).size === 0) {
      listeners.delete(eventType)
    }
  }
}

export function useWebSocket() {
  // Auto-connect on first use, cleanup on last component unmount is optional
  // since we want the socket to persist across page navigations

  return {
    connected: readonly(connected),
    connectionError: readonly(connectionError),
    connect,
    disconnect,
    subscribe,
    unsubscribe,
    on,
    off,
    send,
  }
}