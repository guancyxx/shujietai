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

function mapUpstreamErrorToFriendlyMessage(rawText) {
  const text = String(rawText || '').trim()
  if (!text) return ''

  if (/(invalid api key|unauthorized|authentication failed|invalid_api_key|\b401\b)/i.test(text)) {
    return '⚠️ AI 服务鉴权失败，请检查 Hermes API Key 配置后重试。'
  }
  if (/(insufficient credits|insufficient_quota|quota exceeded|余额不足|额度不足|billing|payment required)/i.test(text)) {
    return '⚠️ AI 服务额度不足，请充值或切换可用模型后重试。'
  }
  if (/(rate limit|too many requests|\b429\b)/i.test(text)) {
    return '⚠️ AI 服务请求过于频繁，请稍后重试。'
  }
  if (/(model not found|no endpoints found|does not support|unsupported model)/i.test(text)) {
    return '⚠️ 当前模型不可用，请切换模型后重试。'
  }
  return ''
}

function normalizeAssistantErrorLikeMessage(message) {
  if (!message || message.role !== 'assistant') return message
  const friendly = mapUpstreamErrorToFriendlyMessage(message.content)
  if (!friendly) return message

  return {
    ...message,
    role: 'system',
    content: friendly,
    meta_json: {
      ...(message.meta_json || {}),
      upstream_error: true,
      raw_error: message.content,
    },
  }
}

function formatTaskError(error) {
  const raw = error instanceof Error ? error.message : 'Unknown error'
  const friendly = mapUpstreamErrorToFriendlyMessage(raw)
  return friendly || raw
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

  const incomingEvent = {
    id: data.event_id || `evt_${Date.now()}`,
    event_type: data.event_type,
    event_name: data.event_name || data.event_type || '',
    status: data.status || null,
    seq: Number.isFinite(data.seq) ? data.seq : Number.MAX_SAFE_INTEGER,
    run_id: data.run_id || null,
    tool_call_id: data.tool_call_id || null,
    payload: data.payload,
    created_at: data.created_at || new Date().toISOString(),
  }

  taskEvents.value.push(incomingEvent)
  taskEvents.value.sort((a, b) => {
    const seqA = Number.isFinite(a.seq) ? a.seq : Number.MAX_SAFE_INTEGER
    const seqB = Number.isFinite(b.seq) ? b.seq : Number.MAX_SAFE_INTEGER
    if (seqA !== seqB) return seqA - seqB
    return new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  })
}

function handleTaskStatus(data) {
  if (data.task_id !== activeTaskId.value) return
  if (activeTask.value) {
    const payloadStatus = data.payload?.status
    const nextStatus = data.status || payloadStatus || activeTask.value.status
    activeTask.value = {
      ...activeTask.value,
      status: nextStatus,
      updated_at: data.created_at || data.updated_at || new Date().toISOString(),
    }
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
      system_prompt: systemPrompt,
      model,
      skills,
      mcp_servers: mcpServers,
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

    // Immediately fetch any events that were generated before WebSocket subscription
    // (race condition: worker may have already started streaming)
    taskEvents.value = []
    try {
      const eventsData = await fetchJson(`${apiBase}/api/v1/dispatch/${task.id}/events`)
      const items = eventsData.items || eventsData || []
      for (const evt of items) {
        taskEvents.value.push({
          id: evt.id,
          event_type: evt.event_type,
          event_name: evt.event_name || evt.event_type || '',
          status: evt.status || null,
          seq: Number.isFinite(evt.seq) ? evt.seq : Number.MAX_SAFE_INTEGER,
          run_id: evt.run_id || null,
          tool_call_id: evt.tool_call_id || null,
          payload: evt.payload,
          created_at: evt.created_at || new Date().toISOString(),
        })
      }
      taskEvents.value.sort((a, b) => {
        const seqA = Number.isFinite(a.seq) ? a.seq : Number.MAX_SAFE_INTEGER
        const seqB = Number.isFinite(b.seq) ? b.seq : Number.MAX_SAFE_INTEGER
        if (seqA !== seqB) return seqA - seqB
        return new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
      })
    } catch {
      // If fetch fails, rely on WebSocket streaming only
    }

    // Fetch current task status to get updated state
    try {
      const updatedTask = await fetchJson(`${apiBase}/api/v1/dispatch/${task.id}`)
      if (updatedTask) {
        activeTask.value = updatedTask
        // Check if task already completed/failed (terminal states)
        if (['completed', 'failed', 'cancelled', 'aborted'].includes(updatedTask.status)) {
          taskEvents.value.push({
            id: `evt_terminal_${task.id}`,
            event_type: updatedTask.status,
            payload: { summary: updatedTask.error_message || updatedTask.status },
            created_at: updatedTask.updated_at || new Date().toISOString(),
          })
        }
      }
    } catch {
      // Ignore status fetch errors
    }

    return task
  } catch (error) {
    taskError.value = formatTaskError(error)
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
    taskError.value = formatTaskError(error)
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
    taskError.value = formatTaskError(error)
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
    taskError.value = formatTaskError(error)
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
  const toolStates = new Map()

  for (const evt of taskEvents.value) {
    const payload = evt.payload || {}

    if (evt.event_type === 'content_delta') {
      const currentRole = payload.role || 'assistant'
      // Group consecutive content_deltas by role
      const lastMsg = messages[messages.length - 1]
      if (lastMsg && lastMsg.role === currentRole && lastMsg._groupKey === 'content') {
        lastMsg.content += payload.content || ''
      } else {
        const message = normalizeAssistantErrorLikeMessage({
          id: evt.id,
          role: currentRole,
          content: payload.content || '',
          content_type: 'text/markdown',
          created_at: evt.created_at,
          meta_json: {},
          _groupKey: 'content',
        })
        messages.push(message)
      }
    } else if (evt.event_type === 'tool_call') {
      const toolCallId = evt.tool_call_id || payload.tool_call_id || payload.id || `tool_${evt.seq || evt.id}`
      const functionName = payload.function_name || payload.tool_name || 'tool'
      const functionArgsDelta = payload.function_args_delta || ''
      const existingTool = toolStates.get(toolCallId)

      if (existingTool) {
        existingTool.args += functionArgsDelta
        existingTool.updatedAt = evt.created_at
        existingTool.completed = existingTool.completed || evt.event_name === 'tool.call.completed'
      } else {
        const toolMessage = {
          id: evt.id,
          role: 'tool',
          content: `🔧 Calling: **${functionName}**`,
          content_type: 'text/markdown',
          created_at: evt.created_at,
          meta_json: {
            tool_call: true,
            tool_call_id: toolCallId,
            function_name: functionName,
            function_args: functionArgsDelta,
            completed: evt.event_name === 'tool.call.completed',
          },
          _groupKey: 'tool_call',
        }
        messages.push(toolMessage)
        toolStates.set(toolCallId, {
          message: toolMessage,
          args: functionArgsDelta,
          updatedAt: evt.created_at,
          completed: evt.event_name === 'tool.call.completed',
        })
      }

      const toolState = toolStates.get(toolCallId)
      if (toolState) {
        if (evt.event_name === 'tool.call.completed') {
          toolState.completed = true
          toolState.updatedAt = evt.created_at
          const finalArgs = payload.function_args || toolState.args
          if (typeof finalArgs === 'string') {
            toolState.args = finalArgs
          }
        }

        toolState.message.meta_json = {
          ...(toolState.message.meta_json || {}),
          function_args: toolState.args,
          updated_at: toolState.updatedAt,
          completed: !!toolState.completed,
        }
        toolState.message.content = toolState.completed
          ? `✅ Tool completed: **${toolState.message.meta_json.function_name || functionName}**`
          : `🔧 Calling: **${toolState.message.meta_json.function_name || functionName}**`
      }
    } else if (evt.event_type === 'error') {
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