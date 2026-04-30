// Dispatch task composable for dispatch orchestration layer (ADR-0004).
// Manages dispatch task lifecycle: create, monitor via WebSocket, cancel/resume.

import { ref, computed } from 'vue'
import { useWebSocket } from './useWebSocket.js'

const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:18000'

// Active dispatch task for the current chat session
const activeTaskId = ref(null)
const activeTask = ref(null)
const taskEvents = ref([])
const taskLoading = ref(false)
const taskError = ref('')

const { connect, subscribe, unsubscribe, on, off, connected } = useWebSocket()

// Dispatch task status display labels
const dispatchStatusLabelMap = {
  queued: '排队中',
  running: '运行中',
  awaiting_input: '等待输入',
  paused: '已暂停',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
}

const dispatchStatusClassMap = {
  queued: 'dispatch-queued',
  running: 'dispatch-running',
  awaiting_input: 'dispatch-awaiting',
  paused: 'dispatch-paused',
  completed: 'dispatch-completed',
  failed: 'dispatch-failed',
  cancelled: 'dispatch-cancelled',
}

const isTaskRunning = computed(() => {
  return activeTask.value && ['queued', 'running'].includes(activeTask.value.status)
})

const isTaskAwaitingInput = computed(() => {
  return activeTask.value?.status === 'awaiting_input'
})

const isTaskResumable = computed(() => {
  return activeTask.value && ['awaiting_input', 'paused'].includes(activeTask.value.status)
})

const isTaskCancellable = computed(() => {
  return activeTask.value && ['queued', 'running', 'awaiting_input'].includes(activeTask.value.status)
})

// WebSocket event handlers
function handleTaskEvent(data) {
  if (data.task_id !== activeTaskId.value) return

  // Append to local event log
  taskEvents.value.push({
    id: data.event_id || `evt_${Date.now()}`,
    event_type: data.event_type,
    payload: data.payload,
    created_at: data.created_at || new Date().toISOString(),
  })
}

function handleTaskStatus(data) {
  if (data.task_id !== activeTaskId.value) return
  if (activeTask.value) {
    activeTask.value = { ...activeTask.value, status: data.status, updated_at: data.updated_at || new Date().toISOString() }
  }
}

async function fetchJson(url) {
  const response = await fetch(url)
  if (!response.ok) throw new Error(`Request failed: ${response.status}`)
  return response.json()
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(`Request failed: ${response.status} ${detail}`)
  }
  return response.json()
}

// Create a dispatch task (replaces direct SSE call to Hermes)
async function createDispatchTask({ aiPlatform = 'hermes', initialPrompt, systemPrompt = '', model = '', skills = [], mcpServers = [], taskBoardItemId = null }) {
  taskLoading.value = true
  taskError.value = ''
  taskEvents.value = []

  try {
    // Ensure WebSocket is connected
    if (!connected.value) connect()

    const payload = {
      ai_platform: aiPlatform,
      initial_prompt: initialPrompt,
      task_board_item_id: taskBoardItemId,
      config: {
        system_prompt: systemPrompt,
        model,
        skills,
        mcp_servers: mcpServers,
      },
    }

    const task = await postJson(`${apiBase}/api/v1/dispatch`, payload)

    // Set active task and subscribe to events
    activeTaskId.value = task.id
    activeTask.value = task

    // Listen for task events
    on('status', handleTaskStatus)
    on('content_delta', handleTaskEvent)
    on('tool_call', handleTaskEvent)
    on('await_input', handleTaskEvent)
    on('completed', handleTaskEvent)
    on('error', handleTaskEvent)
    on('cancelled', handleTaskEvent)

    // Subscribe via WebSocket
    subscribe(task.id)

    return task
  } catch (error) {
    taskError.value = error instanceof Error ? error.message : 'Unknown error'
    throw error
  } finally {
    taskLoading.value = false
  }
}

// Resume an awaiting_input or paused task
async function resumeDispatchTask(userMessage) {
  if (!activeTaskId.value || !isTaskResumable.value) return

  taskLoading.value = true
  taskError.value = ''

  try {
    const task = await postJson(`${apiBase}/api/v1/dispatch/${activeTaskId.value}/resume`, {
      user_message: userMessage,
    })
    activeTask.value = task

    // Re-subscribe in case we lost subscription
    subscribe(task.id)

    return task
  } catch (error) {
    taskError.value = error instanceof Error ? error.message : 'Unknown error'
    throw error
  } finally {
    taskLoading.value = false
  }
}

// Cancel current task
async function cancelDispatchTask() {
  if (!activeTaskId.value || !isTaskCancellable.value) return

  try {
    const result = await postJson(`${apiBase}/api/v1/dispatch/${activeTaskId.value}/cancel`, {})
    activeTask.value = result
    unsubscribe(activeTaskId.value)
    return result
  } catch (error) {
    taskError.value = error instanceof Error ? error.message : 'Unknown error'
  }
}

// Abort current task (forceful)
async function abortDispatchTask() {
  if (!activeTaskId.value) return

  try {
    const result = await postJson(`${apiBase}/api/v1/dispatch/${activeTaskId.value}/abort`, {})
    activeTask.value = result
    unsubscribe(activeTaskId.value)
    return result
  } catch (error) {
    taskError.value = error instanceof Error ? error.message : 'Unknown error'
  }
}

// Clear active task and unsubscribe
function clearActiveTask() {
  if (activeTaskId.value) {
    unsubscribe(activeTaskId.value)
  }
  // Remove event listeners
  off('status', handleTaskStatus)
  off('content_delta', handleTaskEvent)
  off('tool_call', handleTaskEvent)
  off('await_input', handleTaskEvent)
  off('completed', handleTaskEvent)
  off('error', handleTaskEvent)
  off('cancelled', handleTaskEvent)

  activeTaskId.value = null
  activeTask.value = null
  taskEvents.value = []
  taskError.value = ''
}

// Build messages from dispatch events for timeline display
const dispatchMessages = computed(() => {
  const messages = []
  for (const evt of taskEvents.value) {
    if (evt.event_type === 'content_delta') {
      const payload = evt.payload || {}
      // Group consecutive content_deltas by role
      const lastMsg = messages[messages.length - 1]
      if (lastMsg && lastMsg.role === payload.role && lastMsg._groupKey === 'content') {
        lastMsg.content += payload.content || ''
      } else {
        messages.push({
          id: evt.id,
          role: payload.role || 'assistant',
          content: payload.content || '',
          content_type: 'text/markdown',
          created_at: evt.created_at,
          meta_json: {},
          _groupKey: 'content',
        })
      }
    } else if (evt.event_type === 'tool_call') {
      const payload = evt.payload || {}
      messages.push({
        id: evt.id,
        role: 'tool',
        content: `🔧 Calling: **${payload.function_name || payload.tool_name || 'tool'}**`,
        content_type: 'text/markdown',
        created_at: evt.created_at,
        meta_json: { tool_call: true },
        _groupKey: 'tool_call',
      })
    } else if (evt.event_type === 'error') {
      const payload = evt.payload || {}
      messages.push({
        id: evt.id,
        role: 'system',
        content: `❌ Error: ${payload.error || 'Unknown error'}`,
        created_at: evt.created_at,
        meta_json: { error: true },
        _groupKey: 'error',
      })
    }
  }
  return messages
})

export function useDispatchTask() {
  return {
    activeTaskId,
    activeTask,
    taskEvents,
    taskLoading,
    taskError,
    dispatchMessages,
    isTaskRunning,
    isTaskAwaitingInput,
    isTaskResumable,
    isTaskCancellable,
    dispatchStatusLabelMap,
    dispatchStatusClassMap,

    createDispatchTask,
    resumeDispatchTask,
    cancelDispatchTask,
    abortDispatchTask,
    clearActiveTask,
  }
}