import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { useWebSocket } from '../composables/useWebSocket.js'
import { useDispatchTask } from '../composables/useDispatchTask.js'
import { useMarkdownRenderer } from '../composables/useMarkdownRenderer.js'
import { useTimelineScroll } from '../composables/useTimelineScroll.js'
import { fetchJson, postJson } from '../services/apiClient.js'
import { DISPATCH_EVENT_LABEL_MAP, ROLE_LABEL_MAP } from '../constants/appConstants.js'

const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:18000'

export const useSessionStore = defineStore('session', () => {
  // --- State ---
  const sessions = ref([])
  const selectedSessionId = ref('')
  const selectedExternalSessionId = ref('')
  const timeline = ref({ messages: [], events: [] })
  const cockpit = ref(null)
  const loading = ref(false)
  const errorMessage = ref('')
  const sending = ref(false)
  const deletingSessionId = ref('')
  const clearingSessions = ref(false)
  const composerText = ref('')
  const isBlankChatMode = ref(false)
  const blankChatProvider = ref('')
  const streamingContent = ref('')
  const isStreaming = ref(false)
  const streamAbortController = ref(null)

  // Modals in App scope
  const isCreateConversationModalOpen = ref(false)
  const createConversationPlatform = ref('hermes')
  const createConversationInitialMessage = ref('')
  const creatingConversation = ref(false)

  const roleLabelMap = ROLE_LABEL_MAP
  const dispatchEventLabelMap = DISPATCH_EVENT_LABEL_MAP

  // Dispatch orchestration
  const {
    activeTaskId: dispatchTaskId,
    activeTask: dispatchActiveTask,
    taskEvents: dispatchTaskEvents,
    taskLoading: dispatchLoading,
    taskError: dispatchError,
    dispatchMessages,
    isTaskRunning: dispatchIsRunning,
    isTaskAwaitingInput: dispatchAwaitingInput,
    isTaskResumable: dispatchIsResumable,
    isTaskCancellable: dispatchIsCancellable,
    dispatchStatusLabelMap,
    dispatchStatusClassMap,
    createDispatchTask,
    resumeDispatchTask,
    cancelDispatchTask,
    abortDispatchTask,
    interruptDispatchTask,
    clearActiveTask,
    handleTaskEvent,
    handleTaskStatus,
  } = useDispatchTask()

  const { connected: wsConnected, connect: wsConnect, subscribe, on } = useWebSocket()
  const { renderMarkdown } = useMarkdownRenderer()
  const { timelineScrollRef, scrollToBottom, onTimelineScroll, resetTimelineScroll } = useTimelineScroll()

  // --- Getters ---
  const selectedSession = computed(() => sessions.value.find(s => s.id === selectedSessionId.value) || null)

  const blankChatProviders = computed(() => {
    const values = new Set(['hermes'])
    const runtime = cockpit.value?.runtime
    for (const platform of (runtime?.available_platforms ?? [])) {
      if (platform) values.add(platform)
    }
    return Array.from(values).sort()
  })

  const platformOptions = computed(() => {
    const values = new Set(['hermes'])
    for (const item of sessions.value) {
      if (item?.platform) values.add(item.platform)
    }
    return Array.from(values)
  })

  const displayMessages = computed(() => {
    if (dispatchTaskId.value) return dispatchMessages.value
    const msgs = [...(timeline.value.messages || [])]
    if (isStreaming.value && streamingContent.value) {
      msgs.push({
        id: 'streaming', role: 'assistant', content: streamingContent.value,
        content_type: 'text/markdown', created_at: new Date().toISOString(),
        meta_json: { streaming: true },
      })
    }
    return msgs
  })

  const latestDispatchEvent = computed(() => {
    if (!dispatchTaskEvents.value.length) return null
    return dispatchTaskEvents.value[dispatchTaskEvents.value.length - 1]
  })

  const conversationLatestStatus = computed(() => {
    const evt = latestDispatchEvent.value
    if (evt) {
      return {
        text: dispatchEventLabelMap[evt.event_type] || evt.event_type,
        time: evt.created_at ? formatSessionTime(evt.created_at) : '-',
        tone: evt.event_type === 'error' ? 'error' : (evt.event_type === 'completed' ? 'done' : 'active'),
      }
    }
    if (dispatchTaskId.value && dispatchActiveTask.value) {
      return {
        text: `当前任务：${dispatchStatusLabelMap[dispatchActiveTask.value.status] || dispatchActiveTask.value.status}`,
        time: dispatchActiveTask.value.updated_at ? formatSessionTime(dispatchActiveTask.value.updated_at) : '-',
        tone: ['failed', 'cancelled', 'aborted'].includes(dispatchActiveTask.value.status) ? 'error'
          : (dispatchActiveTask.value.status === 'completed' ? 'done' : 'active'),
      }
    }
    if (sending.value || creatingConversation.value || dispatchLoading.value) {
      return { text: '消息已发送，正在发起请求...', time: formatSessionTime(new Date().toISOString()), tone: 'active' }
    }
    return { text: '暂无进行中的请求', time: '-', tone: 'idle' }
  })

  // --- Helpers ---
  function formatSessionTime(value) {
    if (!value) return '-'
    const parsed = new Date(value)
    if (Number.isNaN(parsed.getTime())) return '-'
    return parsed.toLocaleString()
  }

  function formatTime(value) {
    if (!value) return '-'
    const parsed = new Date(value)
    if (Number.isNaN(parsed.getTime())) return '-'
    return parsed.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  }

  function roleClass(role) { return `role-${role || 'assistant'}` }
  function messageSideClass(role) { return role === 'user' ? 'msg-user' : 'msg-assistant' }

  function safePlatform(value) {
    const v = (value || '').trim().toLowerCase()
    return (v === 'none' || v === '') ? 'hermes' : (v || 'hermes')
  }

  // --- Actions ---
  async function loadSessions() {
    const data = await fetchJson(`${apiBase}/api/v1/sessions`)
    const orderedSessions = [...data].sort((a, b) => {
      const ta = a.updated_at || a.created_at || ''
      const tb = b.updated_at || b.created_at || ''
      return tb.localeCompare(ta)
    })
    sessions.value = orderedSessions
    if (!selectedSessionId.value && orderedSessions.length > 0) {
      selectedSessionId.value = orderedSessions[0].id
      selectedExternalSessionId.value = orderedSessions[0].external_session_id
      return
    }
    if (selectedSessionId.value) {
      const m = orderedSessions.find(s => s.id === selectedSessionId.value)
      if (m) { selectedExternalSessionId.value = m.external_session_id; return }
    }
    if (selectedExternalSessionId.value) {
      const m = orderedSessions.find(s => s.external_session_id === selectedExternalSessionId.value)
      if (m) { selectedSessionId.value = m.id; return }
    }
    if (orderedSessions.length > 0) {
      selectedSessionId.value = orderedSessions[0].id
      selectedExternalSessionId.value = orderedSessions[0].external_session_id
    } else {
      selectedSessionId.value = ''
      selectedExternalSessionId.value = ''
    }
  }

  async function fetchCockpitData(sessionId) {
    try {
      return await fetchJson(`${apiBase}/api/v1/board/cockpit?session_id=${sessionId}`)
    } catch (error) {
      const msg = (error instanceof Error ? error.message : String(error || '')).toLowerCase()
      if (msg.includes('session_not_found') || msg.includes('request failed: 404')) return null
      throw error
    }
  }

  async function loadSessionData() {
    if (!selectedSessionId.value) return
    const timelineData = await fetchJson(`${apiBase}/api/v1/sessions/${selectedSessionId.value}/timeline`)
    const cockpitData = await fetchCockpitData(selectedSessionId.value)
    timeline.value = timelineData
    cockpit.value = cockpitData
  }

  function selectConversation(sessionId, externalSessionId) {
    selectedSessionId.value = sessionId
    selectedExternalSessionId.value = externalSessionId
    isBlankChatMode.value = false
  }

  function activateBlankChat() {
    selectedSessionId.value = ''
    selectedExternalSessionId.value = ''
    isBlankChatMode.value = true
    clearActiveTask()
    timeline.value = { messages: [], events: [] }
    if (!blankChatProvider.value || !blankChatProviders.value.includes(blankChatProvider.value)) {
      blankChatProvider.value = blankChatProviders.value.includes('hermes') ? 'hermes' : blankChatProviders.value[0]
    }
  }

  function resetCreateConversationForm() {
    createConversationPlatform.value = selectedSession.value?.platform || 'hermes'
    createConversationInitialMessage.value = ''
  }

  function openCreateConversationModal() {
    resetCreateConversationForm()
    isCreateConversationModalOpen.value = true
  }

  function closeCreateConversationModal() {
    if (creatingConversation.value) return
    isCreateConversationModalOpen.value = false
  }

  function createNewConversation() { openCreateConversationModal() }

  async function submitCreateConversation() {
    const trimmed = createConversationInitialMessage.value.trim()
    if (!trimmed || creatingConversation.value) return
    creatingConversation.value = true
    errorMessage.value = ''
    try {
      const externalSessionId = `web_${Date.now()}`
      await postJson(`${apiBase}/api/v1/connectors/hermes/chat`, {
        external_session_id: externalSessionId,
        platform: createConversationPlatform.value || 'hermes',
        user_message: trimmed,
      })
      isCreateConversationModalOpen.value = false
      composerText.value = ''
      await loadSessions()
      const matched = sessions.value.find(s => s.external_session_id === externalSessionId)
      if (matched) {
        selectedSessionId.value = matched.id
        selectedExternalSessionId.value = matched.external_session_id
      }
      await loadSessionData()
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
    } finally {
      creatingConversation.value = false
    }
  }

  async function deleteSession(sessionId) {
    if (!sessionId || deletingSessionId.value || clearingSessions.value) return
    const target = sessions.value.find(s => s.id === sessionId)
    const title = target?.title || target?.external_session_id || sessionId
    if (!window.confirm(`确认删除对话「${title}」？`)) return
    deletingSessionId.value = sessionId
    errorMessage.value = ''
    try {
      const res = await fetch(`${apiBase}/api/v1/sessions/${sessionId}`, { method: 'DELETE' })
      if (!res.ok) throw new Error(`Request failed: ${res.status}`)
      if (selectedSessionId.value === sessionId) {
        selectedSessionId.value = ''
        selectedExternalSessionId.value = ''
        clearActiveTask()
        isStreaming.value = false
        streamingContent.value = ''
        timeline.value = { messages: [], events: [] }
        cockpit.value = null
      }
      await loadSessions()
      if (selectedSessionId.value) await loadSessionData()
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
    } finally {
      deletingSessionId.value = ''
    }
  }

  async function clearAllSessions() {
    if (clearingSessions.value || deletingSessionId.value || sessions.value.length === 0) return
    if (!window.confirm('确认清空全部对话？此操作不可恢复。')) return
    clearingSessions.value = true
    errorMessage.value = ''
    try {
      const res = await fetch(`${apiBase}/api/v1/sessions`, { method: 'DELETE' })
      if (!res.ok) throw new Error(`Request failed: ${res.status}`)
      selectedSessionId.value = ''
      selectedExternalSessionId.value = ''
      clearActiveTask()
      isStreaming.value = false
      streamingContent.value = ''
      timeline.value = { messages: [], events: [] }
      cockpit.value = null
      await loadSessions()
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
    } finally {
      clearingSessions.value = false
    }
  }

  function handleComposerKeydown(event) {
    if (event.key !== 'Enter' || event.shiftKey || event.ctrlKey || event.altKey || event.metaKey || event.isComposing) return
    event.preventDefault()
    sendMessageToHermes()
  }

  function handleCreateInitialMessageKeydown(event) {
    if (event.key !== 'Enter' || event.shiftKey || event.ctrlKey || event.altKey || event.metaKey || event.isComposing) return
    event.preventDefault()
    submitCreateConversation()
  }

  async function sendMessageToHermes() {
    const trimmed = composerText.value.trim()
    if (!trimmed || sending.value) return
    sending.value = true
    errorMessage.value = ''
    try {
      if (dispatchIsRunning.value && dispatchIsCancellable.value) {
        composerText.value = ''
        await interruptDispatchTask(trimmed)
      } else if (dispatchTaskId.value && dispatchIsResumable.value) {
        composerText.value = ''
        await resumeDispatchTask(trimmed)
      } else {
        if (dispatchActiveTask.value && isTerminalDispatchStatus(dispatchActiveTask.value.status)) clearActiveTask()
        if (!dispatchTaskId.value) {
          composerText.value = ''
          if (!wsConnected.value) wsConnect()
          await createDispatchTask({
            aiPlatform: blankChatProvider.value || 'hermes',
            initialPrompt: trimmed,
            model: '', skills: [], mcpServers: [],
            externalSessionId: selectedExternalSessionId.value || null,
          })
          isBlankChatMode.value = false
        }
      }
    } catch (error) {
      if (error.name !== 'AbortError') errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
    } finally {
      sending.value = false
    }
  }

  function isTerminalDispatchStatus(status) {
    return ['completed', 'failed', 'cancelled', 'aborted'].includes(status)
  }

  // Dispatch task restore logic
  function getDispatchTaskIdFromExternalSessionId(externalSessionId) {
    const n = String(externalSessionId || '').trim()
    if (n.startsWith('dispatch_')) return n.slice('dispatch_'.length)
    return ''
  }

  async function resolveDispatchTaskFromExternalSessionId(externalSessionId) {
    const n = String(externalSessionId || '').trim()
    if (n.startsWith('dispatch_') && n.slice('dispatch_'.length)) {
      return await fetchJson(`${apiBase}/api/v1/dispatch/${n.slice('dispatch_'.length)}`)
    }
    if (n.startsWith('task_board_')) {
      const tid = n.slice('task_board_'.length)
      if (!tid) return null
      try {
        const r = await fetchJson(`${apiBase}/api/v1/dispatch/task-board/${encodeURIComponent(tid)}/work-session`)
        return r.active_dispatch_task || r.latest_dispatch_task || null
      } catch { return null }
    }
    return null
  }

  async function restoreActiveDispatchTask() {
    const n = String(selectedExternalSessionId.value || '').trim()
    if (!n) { clearActiveTask(); return }
    clearActiveTask()
    try {
      const legacyId = getDispatchTaskIdFromExternalSessionId(n)
      let task = null
      if (legacyId) {
        task = await fetchJson(`${apiBase}/api/v1/dispatch/${legacyId}`)
      } else {
        task = await resolveDispatchTaskFromExternalSessionId(n)
      }
      if (!task) return
      dispatchTaskId.value = task.id
      dispatchActiveTask.value = task
      const nonTerminal = ['queued', 'running', 'awaiting_input', 'paused']
      if (nonTerminal.includes(task.status)) {
        on('status', handleTaskStatus)
        on('content_delta', handleTaskEvent)
        on('tool_call', handleTaskEvent)
        on('await_input', handleTaskEvent)
        on('completed', handleTaskEvent)
        on('error', handleTaskEvent)
        on('cancelled', handleTaskEvent)
        if (!wsConnected.value) wsConnect()
        subscribe(task.id)
      }
      const eventsData = await fetchJson(`${apiBase}/api/v1/dispatch/${task.id}/events?limit=2000`)
      const items = eventsData.items || eventsData || []
      dispatchTaskEvents.value = items.map(evt => ({
        id: evt.id, event_type: evt.event_type, event_name: evt.event_name || evt.event_type || '',
        status: evt.status || null, seq: Number.isFinite(evt.seq) ? evt.seq : Number.MAX_SAFE_INTEGER,
        run_id: evt.run_id || null, tool_call_id: evt.tool_call_id || null,
        payload: evt.payload, created_at: evt.created_at || new Date().toISOString(),
      }))
      dispatchTaskEvents.value.sort((a, b) => {
        const sa = Number.isFinite(a.seq) ? a.seq : Number.MAX_SAFE_INTEGER
        const sb = Number.isFinite(b.seq) ? b.seq : Number.MAX_SAFE_INTEGER
        if (sa !== sb) return sa - sb
        return new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
      })
    } catch (error) {
      console.warn('Failed to restore dispatch task', error)
      clearActiveTask()
    }
  }

  async function refreshData() {
    loading.value = true
    errorMessage.value = ''
    try {
      await loadSessions()
      await loadSessionData()
      await restoreActiveDispatchTask()
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
    } finally {
      loading.value = false
    }
  }

  // Watchers
  watch(blankChatProviders, (providers) => {
    if (!providers.includes(blankChatProvider.value)) {
      blankChatProvider.value = providers.includes('hermes') ? 'hermes' : providers[0]
    }
  })

  watch(selectedSessionId, async () => {
    if (!selectedSessionId.value) {
      timeline.value = { messages: [], events: [] }
      clearActiveTask()
      if (!isBlankChatMode.value) cockpit.value = null
      return
    }
    try {
      errorMessage.value = ''
      await loadSessionData()
      await restoreActiveDispatchTask()
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
    }
  })

  return {
    sessions, selectedSessionId, selectedExternalSessionId, timeline, cockpit,
    loading, errorMessage, sending, deletingSessionId, clearingSessions,
    composerText, isBlankChatMode, blankChatProvider, blankChatProviders,
    streamingContent, isStreaming, streamAbortController,
    isCreateConversationModalOpen, createConversationPlatform,
    createConversationInitialMessage, creatingConversation,
    roleLabelMap, dispatchEventLabelMap,
    dispatchTaskId, dispatchActiveTask, dispatchTaskEvents,
    dispatchLoading, dispatchError, dispatchMessages,
    dispatchIsRunning, dispatchAwaitingInput, dispatchIsResumable, dispatchIsCancellable,
    dispatchStatusLabelMap, dispatchStatusClassMap,
    wsConnected, wsConnect, createDispatchTask, resumeDispatchTask,
    cancelDispatchTask, abortDispatchTask, interruptDispatchTask, clearActiveTask,
    selectedSession, displayMessages, latestDispatchEvent, conversationLatestStatus,
    platformOptions, renderMarkdown,
    timelineScrollRef, scrollToBottom, onTimelineScroll, resetTimelineScroll,
    loadSessions, loadSessionData, refreshData, restoreActiveDispatchTask,
    selectConversation, activateBlankChat, createNewConversation,
    openCreateConversationModal, closeCreateConversationModal, submitCreateConversation,
    deleteSession, clearAllSessions,
    handleComposerKeydown, handleCreateInitialMessageKeydown, sendMessageToHermes,
    formatSessionTime, formatTime, roleClass, messageSideClass, safePlatform,
    isTerminalDispatchStatus,
  }
})
