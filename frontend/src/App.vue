<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useWebSocket } from './composables/useWebSocket.js'
import { useDispatchTask } from './composables/useDispatchTask.js'
import { useDispatchHistory } from './composables/useDispatchHistory.js'
import SkillGraph from './SkillGraph.vue'
import { useMarkdownRenderer } from './composables/useMarkdownRenderer.js'
import { useTimelineScroll } from './composables/useTimelineScroll.js'
import { deleteJson, fetchJson, patchJson, postJson, postJsonTimeout, putJson } from './services/apiClient.js'
import { buildTaskTree, countTaskTreeNodes, getTaskPriority, makeTaskNodeKey } from './services/taskBoardTree.js'
import {
  COLLAPSIBLE_KANBAN_STATUSES,
  DISPATCH_EVENT_LABEL_MAP,
  KANBAN_PRIORITY_LABELS,
  KANBAN_PRIORITY_ORDER,
  KANBAN_STATUSES,
  LANE_TITLE_MAP,
  PAGE_WHITELIST,
  ROLE_LABEL_MAP,
  TASK_BOARD_PRIORITY_LABEL_MAP,
  TASK_BOARD_PRIORITY_OPTIONS,
  TASK_BOARD_STATUS_LABEL_MAP,
  TASK_BOARD_STATUS_OPTIONS,
} from './constants/appConstants.js'

const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:18000'

const sessions = ref([])
const selectedSessionId = ref('')
const selectedExternalSessionId = ref('')
const timeline = ref({ messages: [], events: [] })
const cockpit = ref(null)
const loading = ref(false)
const errorMessage = ref('')
const selectedModel = ref('')
const selectedSkills = ref([])
const selectedMcpServers = ref([])
const isModelModalOpen = ref(false)
const isSkillModalOpen = ref(false)
const isMcpModalOpen = ref(false)
const isCreateConversationModalOpen = ref(false)
const blankChatProvider = ref('')
const isBlankChatMode = ref(false)
const modelSearchDraft = ref('')
const modelProviderDraft = ref('')
const tempSelectedModel = ref('')
const skillSearch = ref('')
const mcpSearch = ref('')
const skillSearchDraft = ref('')
const mcpSearchDraft = ref('')
const tempSelectedSkills = ref([])
const tempSelectedMcpServers = ref([])
const createConversationPlatform = ref('hermes')
const createConversationInitialMessage = ref('')
const creatingConversation = ref(false)
const sending = ref(false)
const deletingSessionId = ref('')
const clearingSessions = ref(false)
const composerText = ref('')
// Load persisted active page from localStorage on init — avoids flashing to chat first
function getInitialPage() {
  try {
    const saved = localStorage.getItem('shujietai_activePage')
    if (PAGE_WHITELIST.includes(saved)) return saved
  } catch {
    // localStorage unavailable (private browsing), ignore
  }
  return 'chat'
}

const activePage = ref(getInitialPage())

// Persist active page on every switch so refresh restores the last page
watch(activePage, (page) => {
  try {
    localStorage.setItem('shujietai_activePage', page)
  } catch {
    // localStorage write blocked, ignore
  }
})
const projects = ref([])
const githubRepos = ref([])
const projectSearch = ref('')
const creatingProject = ref(false)
const updatingProject = ref(false)
const deletingProjectId = ref('')
const creatingGithubRepo = ref(false)
const githubTokenDraft = ref('')
const githubTokenSaving = ref(false)
const githubTokenConfigured = ref(false)
const taskBoardItems = ref([])
const taskBoardProjectFilter = ref('')
const taskBoardKeyword = ref('')
const taskBoardStatusFilter = ref('')
const isTaskBoardCreateModalOpen = ref(false)
const isTaskBoardEditModalOpen = ref(false)
const creatingTaskBoardItem = ref(false)
const updatingTaskBoardItem = ref(false)
const deletingTaskBoardItemId = ref('')
const quickUpdatingTaskBoardItemId = ref('')
const draggingTaskBoardItemId = ref('')
const taskBoardDetailItem = ref(null)
const highlightedTaskBoardItemId = ref('')
const startingConversationFromTask = ref(false)
const streamingContent = ref('')        // Current streaming assistant message content
const isStreaming = ref(false)           // Whether a stream is in progress
const streamAbortController = ref(null) // AbortController for cancelling streams
const {
  timelineScrollRef,
  scrollToBottom,
  onTimelineScroll,
  resetTimelineScroll,
} = useTimelineScroll()

// Dispatch orchestration layer (ADR-0004) — replaces direct SSE with async dispatch + WebSocket
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

const {
  allTasks: allDispatchTasks,
  filteredTasks: filteredDispatchTasks,
  taskStats: dispatchStats,
  historyLoading: dispatchHistoryLoading,
  historyError: dispatchHistoryError,
  statusFilter: dispatchHistoryStatusFilter,
  fetchTaskHistory,
  fetchTaskEvents,
} = useDispatchHistory()

const dispatchDetailTask = ref(null)
const dispatchDetailEvents = ref([])

async function switchToDispatchHistory() {
  activePage.value = 'dispatch-history'
  await refreshDispatchHistory()
}

// Skills catalog state
const skillsCatalog = ref(null)
const skillsCatalogLoading = ref(false)
const skillsCatalogError = ref('')
const skillsCatalogSearch = ref('')
const skillsCatalogCategoryFilter = ref('全部')
const skillsCatalogProviderFilter = ref('hermes')
const skillsCatalogTypeFilter = ref('全部')
const skillDetailTarget = ref(null)
const skillDetailContent = ref('')
const skillDetailContentLoading = ref(false)
const skillDetailError = ref('')
const skillsCatalogPage = ref(1)
const skillsCatalogPageSize = 30
const skillsCatalogView = ref('list')  // 'list' | 'graph'

const skillsCatalogProviders = computed(() => {
  if (!skillsCatalog.value) return [{ id: 'hermes', label: 'Hermes Agent' }]
  return skillsCatalog.value.providers.map((p) => ({ id: p.id, label: p.label }))
})

const skillsCatalogCategories = computed(() => {
  if (!skillsCatalog.value) return []
  const provider = skillsCatalog.value.providers.find((p) => p.id === skillsCatalogProviderFilter.value)
  if (!provider) return []
  const cats = new Set(provider.skills.map((s) => s.category))
  return Array.from(cats).sort()
})

const filteredCatalogSkills = computed(() => {
  if (!skillsCatalog.value) return []
  const provider = skillsCatalog.value.providers.find((p) => p.id === skillsCatalogProviderFilter.value)
  if (!provider) return []
  const keyword = skillsCatalogSearch.value.trim().toLowerCase()
  const catFilter = skillsCatalogCategoryFilter.value
  const typeFilter = skillsCatalogTypeFilter.value
  return provider.skills
    .filter((s) => {
      const catOk = catFilter === '全部' || s.category === catFilter
      const typeOk = typeFilter === '全部' || (s.skill_type || 'builtin') === typeFilter
      if (!catOk || !typeOk) return false
      if (!keyword) return true
      return s.name.toLowerCase().includes(keyword) || (s.description || '').toLowerCase().includes(keyword)
    })
    .map((s) => ({ ...s, provider_id: provider.id, provider_label: provider.label }))
})

const skillsCatalogTotalPages = computed(() => Math.max(1, Math.ceil(filteredCatalogSkills.value.length / skillsCatalogPageSize)))
const pagedCatalogSkills = computed(() => {
  const start = (skillsCatalogPage.value - 1) * skillsCatalogPageSize
  return filteredCatalogSkills.value.slice(start, start + skillsCatalogPageSize)
})

// Reset to page 1 when filters change
watch([skillsCatalogSearch, skillsCatalogCategoryFilter, skillsCatalogTypeFilter, skillsCatalogProviderFilter], () => {
  skillsCatalogPage.value = 1
})

async function openSkillDetail(skill) {
  skillDetailTarget.value = skill
  skillDetailContent.value = ''
  skillDetailError.value = ''
  skillDetailContentLoading.value = true
  try {
    const res = await fetch(`${apiBase}/api/v1/skills/${encodeURIComponent(skill.name)}/content`)
    if (res.ok) {
      const data = await res.json()
      skillDetailContent.value = data.content || ''
      if (data.path) {
        skillDetailTarget.value = { ...skillDetailTarget.value, _api_path: data.path }
      }
    } else if (res.status === 404) {
      skillDetailError.value = '技能内容文件未找到。该技能可能已被移除或技能名称有误。'
    } else if (res.status === 403 || res.status === 401) {
      skillDetailError.value = '无权访问该技能内容，请检查文件权限。'
    } else {
      skillDetailError.value = '加载技能内容失败 (HTTP ' + res.status + ')，请稍后重试。'
    }
  } catch (_) {
    skillDetailError.value = '网络请求失败，无法加载技能内容。请检查后端服务是否正常运行。'
  }
  skillDetailContentLoading.value = false
}
function closeSkillDetail() {
  skillDetailTarget.value = null
  skillDetailContent.value = ''
  skillDetailError.value = ''
}

async function loadSkillsCatalog() {
  skillsCatalogLoading.value = true
  skillsCatalogError.value = ''
  try {
    const data = await fetchJson(`${apiBase}/api/v1/skills`)
    skillsCatalog.value = data
    // reset category filter when provider changes
    skillsCatalogCategoryFilter.value = '全部'
  } catch (e) {
    skillsCatalogError.value = e?.message || 'Failed to load skills'
  } finally {
    skillsCatalogLoading.value = false
  }
}

async function switchToSkillsCatalog() {
  activePage.value = 'skills-catalog'
  if (!skillsCatalog.value) {
    await loadSkillsCatalog()
  }
}

async function refreshDispatchHistory() {
  await fetchTaskHistory(dispatchHistoryStatusFilter.value)
}

async function viewDispatchTaskDetail(task) {
  dispatchDetailTask.value = task
  dispatchDetailEvents.value = []
  try {
    const data = await fetchTaskEvents(task.id)
    dispatchDetailEvents.value = data.events || data || []
  } catch { /* ignore */ }
}

async function resumeFromHistory(task) {
  dispatchDetailTask.value = null
  activePage.value = 'chat'

  const externalSessionId = task?.external_session_id || `dispatch_${task?.id || ''}`
  const matchedSession = sessions.value.find((item) => item.external_session_id === externalSessionId)
  if (matchedSession) {
    selectedSessionId.value = matchedSession.id
    selectedExternalSessionId.value = matchedSession.external_session_id
  } else {
    selectedExternalSessionId.value = externalSessionId
  }

  await restoreActiveDispatchTask()
}

async function cancelFromHistory(task) {
  try {
    await fetch(`${apiBase}/api/v1/dispatch/${task.id}/cancel`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
    await refreshDispatchHistory()
    dispatchDetailTask.value = null
  } catch { /* ignore */ }
}

const { connected: wsConnected, connect: wsConnect, subscribe, on } = useWebSocket()
const editingTaskBoardItemId = ref('')
const taskBoardCreateForm = ref({
  name: '',
  description: '',
  ai_platform: 'hermes',
  project_id: '',
  upstream_task_id: '',
  parent_task_id: '',
  status: 'draft',
  status_reason: '',
  priority: 3,
})
const taskBoardEditForm = ref({
  name: '',
  description: '',
  ai_platform: 'hermes',
  project_id: '',
  upstream_task_id: '',
  parent_task_id: '',
  status: 'draft',
  status_reason: '',
  priority: 3,
})
const isProjectCreateModalOpen = ref(false)
const isProjectEditModalOpen = ref(false)
const createRepoEnabled = ref(false)
const createProjectForm = ref({
  repository_url: '',
  name: '',
  description: '',
  private: false,
})
const editProjectId = ref('')
const editProjectForm = ref({
  name: '',
  description: '',
})

const selectedSession = computed(() => sessions.value.find((s) => s.id === selectedSessionId.value) || null)

const filteredProjects = computed(() => {
  const keyword = projectSearch.value.trim().toLowerCase()
  if (!keyword) {
    return projects.value
  }
  return projects.value.filter((item) => {
    const text = `${item.code} ${item.name} ${item.description} ${item.repository_name} ${item.repository_url}`.toLowerCase()
    return text.includes(keyword)
  })
})

const taskBoardStatusOptions = TASK_BOARD_STATUS_OPTIONS
const taskBoardStatusLabelMap = TASK_BOARD_STATUS_LABEL_MAP
const taskBoardPriorityOptions = TASK_BOARD_PRIORITY_OPTIONS
const taskBoardPriorityLabelMap = TASK_BOARD_PRIORITY_LABEL_MAP

const taskBoardProjectOptions = computed(() => [
  { value: '', label: '全部项目' },
  ...projects.value.map((item) => ({ value: item.id, label: `${item.name}（${item.code}）` })),
])

const taskBoardDependencyOptions = computed(() => taskBoardItems.value.map((item) => ({ value: item.id, label: item.name })))

const taskBoardStatusFilterOptions = computed(() => [
  { value: '', label: '全部状态' },
  ...taskBoardStatusOptions,
])

const filteredTaskBoardItems = computed(() => {
  const keyword = taskBoardKeyword.value.trim().toLowerCase()
  const projectId = taskBoardProjectFilter.value.trim()
  const statusFilter = taskBoardStatusFilter.value.trim()
  return taskBoardItems.value.filter((item) => {
    const projectMatched = !projectId || item.project_id === projectId
    if (!projectMatched) {
      return false
    }
    const statusMatched = !statusFilter || item.status === statusFilter
    if (!statusMatched) {
      return false
    }
    if (!keyword) {
      return true
    }
    const text = `${item.name} ${item.description} ${item.ai_platform} ${item.project_name || ''}`.toLowerCase()
    return text.includes(keyword)
  })
})

function findTaskBoardItemById(taskId) {
  if (!taskId) return null
  return taskBoardItems.value.find((item) => item.id === taskId) || null
}

const currentLinkedTaskId = computed(() => {
  return dispatchActiveTask.value?.task_board_item_id
    || selectedSession.value?.payload_json?.task_board_item_id
    || dispatchTaskEvents.value.find((evt) => evt.payload?.task_board_item_id)?.payload?.task_board_item_id
    || null
})

const currentLinkedTask = computed(() => findTaskBoardItemById(currentLinkedTaskId.value))

const currentLoadedSkills = computed(() => {
  const seen = new Set()
  const items = []
  for (const evt of dispatchTaskEvents.value) {
    const payload = evt.payload || {}
    const functionName = payload.function_name || payload.tool_name || ''
    const skillName = payload.skill_name || (functionName === 'skill_view' ? extractSkillNameFromToolPayload(payload) : '')
    if (!skillName || seen.has(skillName)) continue
    seen.add(skillName)
    items.push({
      name: skillName,
      file_path: payload.skill_file_path || '',
      skill_type: 'builtin',
      category: 'loaded',
      description: payload.skill_file_path ? `已读取 ${payload.skill_file_path}` : '本轮会话已加载',
    })
  }
  return items
})

function extractSkillNameFromToolPayload(payload) {
  const args = payload.arguments || payload.function_args || payload.preview || ''
  if (args && typeof args === 'object' && args.name) return String(args.name)
  const text = typeof args === 'string' ? args : JSON.stringify(args || {})
  const match = text.match(/name\s*=\s*['"]([^'"]+)['"]/) || text.match(/["']name["']\s*:\s*["']([^"']+)["']/)
  return match?.[1] || ''
}

async function openLinkedTaskFromStatus() {
  const taskId = currentLinkedTaskId.value
  if (!taskId) return
  if (!taskBoardItems.value.length) {
    try { await loadTaskBoardItems() } catch (_) { /* ignore */ }
  }
  const item = findTaskBoardItemById(taskId)
  if (item?.project_id) taskBoardProjectFilter.value = item.project_id
  taskBoardKeyword.value = ''
  taskBoardStatusFilter.value = ''
  highlightedTaskBoardItemId.value = taskId
  activePage.value = 'task-board'
}

const taskBoardMatrix = computed(() => {
  const projectMap = new Map()
  for (const item of filteredTaskBoardItems.value) {
    const projectKey = item.project_id || '__none__'
    const projectName = item.project_name || '未关联项目'
    if (!projectMap.has(projectKey)) {
      projectMap.set(projectKey, {
        id: projectKey,
        name: projectName,
        columns: Object.fromEntries(KANBAN_STATUSES.map((s) => [s, []])),
      })
    }
    const project = projectMap.get(projectKey)
    const status = KANBAN_STATUSES.includes(item.status) ? item.status : 'draft'
    project.columns[status].push(item)
  }

  return [...projectMap.values()]
    .map((project) => {
      const columns = Object.fromEntries(
        KANBAN_STATUSES.map((status) => [status, buildTaskTree(project.columns[status])]),
      )
      return {
        ...project,
        columns,
        taskCount: KANBAN_STATUSES.reduce((sum, status) => sum + countTaskTreeNodes(columns[status]), 0),
      }
    })
    .sort((a, b) => {
      if (a.id === '__none__') return 1
      if (b.id === '__none__') return -1
      return a.name.localeCompare(b.name)
    })
})

const collapsedProjectRows = ref(new Set())
const collapsedTaskNodes = ref(new Set())
const collapsedKanbanStatuses = ref(new Set(['completed']))

const KANBAN_LABEL_TRACK = 'minmax(clamp(8rem, 13vw, 11rem), 0.52fr)'
const KANBAN_EXPANDED_TRACK = 'minmax(clamp(10rem, 12vw, 14rem), 1fr)'
const KANBAN_COLLAPSED_TRACK = 'minmax(4.4rem, 0.22fr)'
const KANBAN_LABEL_MIN_REM = 8
const KANBAN_EXPANDED_MIN_REM = 10
const KANBAN_COLLAPSED_MIN_REM = 4.4

const kanbanGridTemplate = computed(() => (
  [
    KANBAN_LABEL_TRACK,
    ...KANBAN_STATUSES.map((status) => (
      collapsedKanbanStatuses.value.has(status) ? KANBAN_COLLAPSED_TRACK : KANBAN_EXPANDED_TRACK
    )),
  ].join(' ')
))

const kanbanMatrixMinWidth = computed(() => {
  const statusTrackMinWidth = KANBAN_STATUSES.reduce((sum, status) => (
    sum + (collapsedKanbanStatuses.value.has(status) ? KANBAN_COLLAPSED_MIN_REM : KANBAN_EXPANDED_MIN_REM)
  ), 0)
  return `${KANBAN_LABEL_MIN_REM + statusTrackMinWidth}rem`
})

const kanbanMatrixStyle = computed(() => ({
  '--kanban-grid-template': kanbanGridTemplate.value,
  '--kanban-matrix-min-width': kanbanMatrixMinWidth.value,
}))

function isKanbanStatusCollapsible(status) {
  return COLLAPSIBLE_KANBAN_STATUSES.includes(status)
}

function isKanbanStatusCollapsed(status) {
  return collapsedKanbanStatuses.value.has(status)
}

function toggleKanbanStatusColumn(status) {
  if (!isKanbanStatusCollapsible(status)) return
  const next = new Set(collapsedKanbanStatuses.value)
  if (next.has(status)) { next.delete(status) } else { next.add(status) }
  collapsedKanbanStatuses.value = next
}

function toggleProjectRow(projectId) {
  const s = new Set(collapsedProjectRows.value)
  if (s.has(projectId)) { s.delete(projectId) } else { s.add(projectId) }
  collapsedProjectRows.value = s
}

function toggleTaskNode(item) {
  const key = makeTaskNodeKey(item)
  if (!key) return
  const s = new Set(collapsedTaskNodes.value)
  if (s.has(key)) { s.delete(key) } else { s.add(key) }
  collapsedTaskNodes.value = s
}

const selectedCreateRepo = computed(() => {
  if (!createProjectForm.value.repository_url) {
    return null
  }
  return githubRepos.value.find((repo) => repo.url === createProjectForm.value.repository_url) || null
})

const laneTitleMap = LANE_TITLE_MAP
const roleLabelMap = ROLE_LABEL_MAP
const dispatchEventLabelMap = DISPATCH_EVENT_LABEL_MAP

const latestDispatchEvent = computed(() => {
  if (!dispatchTaskEvents.value.length) {
    return null
  }
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
      tone: ['failed', 'cancelled', 'aborted'].includes(dispatchActiveTask.value.status) ? 'error' : (dispatchActiveTask.value.status === 'completed' ? 'done' : 'active'),
    }
  }

  if (sending.value || creatingConversation.value || dispatchLoading.value) {
    return {
      text: '消息已发送，正在发起请求...',
      time: formatSessionTime(new Date().toISOString()),
      tone: 'active',
    }
  }

  return {
    text: '暂无进行中的请求',
    time: '-',
    tone: 'idle',
  }
})

const { renderMarkdown } = useMarkdownRenderer()

// Merged timeline: historical messages + dispatch messages (via WebSocket) + streaming assistant message
const displayMessages = computed(() => {
  // If there is an active dispatch task, always show dispatch messages view
  // (even while loading — avoids showing stale timeline "已提交..." placeholder)
  if (dispatchTaskId.value) {
    return dispatchMessages.value
  }
  const msgs = [...(timeline.value.messages || [])]
  if (isStreaming.value && streamingContent.value) {
    msgs.push({
      id: 'streaming',
      role: 'assistant',
      content: streamingContent.value,
      content_type: 'text/markdown',
      created_at: new Date().toISOString(),
      meta_json: { streaming: true },
    })
  }
  return msgs
})

// Auto-scroll to bottom when displayMessages change (respects user scroll state)
watch(displayMessages, () => scrollToBottom(), { deep: true })

const taskLanes = computed(() => {
  const laneMap = { todo: [], doing: [], done: [] }
  if (!cockpit.value) {
    return laneMap
  }
  for (const task of cockpit.value.tasks || []) {
    laneMap[task.lane]?.push(task)
  }
  return laneMap
})

const runtimeSummary = computed(() => {
  const runtime = cockpit.value?.runtime
  const skillItems = runtime?.available_skill_items ?? []
  const modelItems = runtime?.available_model_items ?? []
  const modelProviderMap = Object.fromEntries(modelItems.map((item) => [item.name, item.provider || '-']))
  const selectedProvider = runtime?.selected_model_provider || modelProviderMap[selectedModel.value] || '-'
  return {
    availableModels: runtime?.available_models ?? [],
    availableModelItems: modelItems,
    selectedModelProvider: selectedProvider,
    currentModelProvider: runtime?.current_model_provider || '-',
    availableSkills: runtime?.available_skills ?? [],
    availableSkillItems: skillItems,
    availableMcpServers: runtime?.available_mcp_servers ?? [],
    availablePlatforms: runtime?.available_platforms ?? ['hermes'],
    selectedModelText: selectedModel.value || '-',
    selectedSkillsText: selectedSkills.value.length > 0 ? selectedSkills.value.join(' · ') : '-',
    selectedMcpText: selectedMcpServers.value.length > 0 ? selectedMcpServers.value.join(' · ') : '-',
  }
})

function getCatalog() {
  return runtimeSummary.value
}

const modelRuntimeCatalog = computed(() => getCatalog())
const skillRuntimeCatalog = computed(() => getCatalog())
const mcpRuntimeCatalog = computed(() => getCatalog())

const selectedSkillsCountText = computed(() => {
  const count = selectedSkills.value.length
  return count > 0 ? `已选择 ${count} 项` : '未选择'
})

const selectedMcpCountText = computed(() => {
  const count = selectedMcpServers.value.length
  return count > 0 ? `已选择 ${count} 项` : '未选择'
})

const platformOptions = computed(() => {
  const values = new Set(['hermes'])
  for (const item of sessions.value) {
    if (item?.platform) {
      values.add(item.platform)
    }
  }
  return Array.from(values)
})

const modelProviderOptions = computed(() => {
  const values = new Set(modelRuntimeCatalog.value.availableModelItems.map((item) => item.provider || '-'))
  return ['全部', ...Array.from(values).filter((value) => value && value !== '-').sort()]
})

const blankChatProviders = computed(() => {
  const values = new Set(['hermes'])
  for (const platform of runtimeSummary.value.availablePlatforms) {
    if (platform) values.add(platform)
  }
  return Array.from(values).sort()
})

const filteredModelItems = computed(() => {
  const providerFilter = modelProviderDraft.value
  const keyword = modelSearchDraft.value.trim().toLowerCase()
  return modelRuntimeCatalog.value.availableModelItems.filter((item) => {
    const provider = item.provider || '-'
    const providerMatched = providerFilter === '全部' || !providerFilter ? true : provider === providerFilter
    if (!providerMatched) {
      return false
    }
    if (!keyword) {
      return true
    }
    const text = `${item.name} ${provider}`.toLowerCase()
    return text.includes(keyword)
  })
})

const filteredSkillItems = computed(() => {
  const keyword = skillSearchDraft.value.trim().toLowerCase()
  if (!keyword) {
    return skillRuntimeCatalog.value.availableSkillItems
  }
  return skillRuntimeCatalog.value.availableSkillItems.filter((item) => {
    const name = item.name?.toLowerCase() ?? ''
    const description = item.description?.toLowerCase() ?? ''
    return name.includes(keyword) || description.includes(keyword)
  })
})

const filteredMcpItems = computed(() => {
  const keyword = mcpSearchDraft.value.trim().toLowerCase()
  if (!keyword) {
    return mcpRuntimeCatalog.value.availableMcpServers
  }
  return mcpRuntimeCatalog.value.availableMcpServers.filter((item) => item.toLowerCase().includes(keyword))
})

function syncRuntimeSelectionsFromCockpit() {
  const runtime = cockpit.value?.runtime
  if (!runtime) {
    selectedModel.value = ''
    selectedSkills.value = []
    selectedMcpServers.value = []
    return
  }

  const modelCandidates = runtime.available_models ?? []
  const selectedModelFromServer = runtime.selected_model ?? ''
  selectedModel.value = modelCandidates.includes(selectedModelFromServer)
    ? selectedModelFromServer
    : (modelCandidates[0] || selectedModelFromServer)

  const skillCandidates = new Set(runtime.available_skills ?? [])
  selectedSkills.value = (runtime.selected_skills ?? []).filter((item) => skillCandidates.has(item))

  const mcpCandidates = new Set(runtime.available_mcp_servers ?? [])
  selectedMcpServers.value = (runtime.selected_mcp_servers ?? []).filter((item) => mcpCandidates.has(item))
}

function openModelModal() {
  tempSelectedModel.value = selectedModel.value
  const currentProvider = runtimeSummary.value.availableModelItems.find((item) => item.name === selectedModel.value)?.provider || ''
  modelProviderDraft.value = currentProvider || '全部'
  modelSearchDraft.value = ''
  isModelModalOpen.value = true
}

function closeModelModal() {
  isModelModalOpen.value = false
}

async function applyModelModalSelection() {
  if (tempSelectedModel.value) {
    selectedModel.value = tempSelectedModel.value
  }
  await persistRuntimePreferences()
  isModelModalOpen.value = false
}

function selectTempModel(name) {
  tempSelectedModel.value = name
}

function openSkillModal() {
  tempSelectedSkills.value = [...selectedSkills.value]
  skillSearchDraft.value = skillSearch.value
  isSkillModalOpen.value = true
}

function closeSkillModal() {
  isSkillModalOpen.value = false
}

async function applySkillModalSelection() {
  selectedSkills.value = [...tempSelectedSkills.value]
  skillSearch.value = skillSearchDraft.value
  await persistRuntimePreferences()
  isSkillModalOpen.value = false
}

function toggleTempSkill(name) {
  const next = new Set(tempSelectedSkills.value)
  if (next.has(name)) {
    next.delete(name)
  } else {
    next.add(name)
  }
  tempSelectedSkills.value = [...next]
}

function isTempSkillChecked(name) {
  return tempSelectedSkills.value.includes(name)
}

function openMcpModal() {
  tempSelectedMcpServers.value = [...selectedMcpServers.value]
  mcpSearchDraft.value = mcpSearch.value
  isMcpModalOpen.value = true
}

function closeMcpModal() {
  isMcpModalOpen.value = false
}

async function applyMcpModalSelection() {
  selectedMcpServers.value = [...tempSelectedMcpServers.value]
  mcpSearch.value = mcpSearchDraft.value
  await persistRuntimePreferences()
  isMcpModalOpen.value = false
}

function toggleTempMcp(name) {
  const next = new Set(tempSelectedMcpServers.value)
  if (next.has(name)) {
    next.delete(name)
  } else {
    next.add(name)
  }
  tempSelectedMcpServers.value = [...next]
}

function isTempMcpChecked(name) {
  return tempSelectedMcpServers.value.includes(name)
}

function laneClass(lane) {
  return `lane-${lane}`
}

function taskBoardStatusClass(status) {
  return `task-status-${status || 'draft'}`
}

function isTerminalDispatchStatus(status) {
  return ['completed', 'failed', 'cancelled', 'aborted'].includes(status)
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
  if (creatingConversation.value) {
    return
  }
  isCreateConversationModalOpen.value = false
}

async function submitCreateConversation() {
  const trimmed = createConversationInitialMessage.value.trim()
  if (!trimmed || creatingConversation.value) {
    return
  }

  creatingConversation.value = true
  errorMessage.value = ''
  try {
    const externalSessionId = `web_${Date.now()}`
    const payload = {
      external_session_id: externalSessionId,
      title: 'Web Chat Session',
      platform: createConversationPlatform.value || 'hermes',
      user_message: trimmed,
    }
    await postJson(`${apiBase}/api/v1/connectors/hermes/chat`, payload)
    isCreateConversationModalOpen.value = false
    composerText.value = ''
    await loadSessions()
    const matched = sessions.value.find((item) => item.external_session_id === externalSessionId)
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

function createNewConversation() {
  openCreateConversationModal()
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

function roleClass(role) {
  return `role-${role || 'assistant'}`
}

function messageSideClass(role) {
  return role === 'user' ? 'msg-user' : 'msg-assistant'
}

function formatSessionTime(value) {
  if (!value) {
    return '-'
  }
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return '-'
  }
  return parsed.toLocaleString()
}

function formatTime(value) {
  if (!value) return '-'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return '-'
  return parsed.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

async function persistRuntimePreferences() {
  const payload = {
    selected_model: selectedModel.value || null,
    selected_skills: selectedSkills.value,
    selected_mcp_servers: selectedMcpServers.value,
  }
  const runtime = await putJson(`${apiBase}/api/v1/runtime/preferences`, payload)
  const modelCandidates = runtime.available_models ?? []
  const selectedModelFromServer = runtime.selected_model ?? ''
  selectedModel.value = modelCandidates.includes(selectedModelFromServer)
    ? selectedModelFromServer
    : (modelCandidates[0] || selectedModelFromServer)

  const skillCandidates = new Set(runtime.available_skills ?? [])
  selectedSkills.value = (runtime.selected_skills ?? []).filter((item) => skillCandidates.has(item))

  const mcpCandidates = new Set(runtime.available_mcp_servers ?? [])
  selectedMcpServers.value = (runtime.selected_mcp_servers ?? []).filter((item) => mcpCandidates.has(item))
}

async function loadSessions() {
  const data = await fetchJson(`${apiBase}/api/v1/sessions`)
  // Sort by updated_at descending (most recently active first)
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
    const matchedById = orderedSessions.find((item) => item.id === selectedSessionId.value)
    if (matchedById) {
      selectedExternalSessionId.value = matchedById.external_session_id
      return
    }
  }

  if (selectedExternalSessionId.value) {
    const matchedByExternal = orderedSessions.find((item) => item.external_session_id === selectedExternalSessionId.value)
    if (matchedByExternal) {
      selectedSessionId.value = matchedByExternal.id
      return
    }
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
    const message = error instanceof Error ? error.message : String(error || '')
    const normalized = message.toLowerCase()
    if (normalized.includes('session_not_found') || normalized.includes('request failed: 404')) {
      return null
    }
    throw error
  }
}

async function loadSessionData() {
  if (!selectedSessionId.value) {
    return
  }
  const timelineData = await fetchJson(`${apiBase}/api/v1/sessions/${selectedSessionId.value}/timeline`)
  const cockpitData = await fetchCockpitData(selectedSessionId.value)
  timeline.value = timelineData
  cockpit.value = cockpitData
  if (cockpitData) {
    syncRuntimeSelectionsFromCockpit()
  }
}

async function refreshData() {
  loading.value = true
  errorMessage.value = ''
  try {
    await Promise.all([loadSessions(), loadProjects(), loadTaskBoardItems(), loadGithubRepos(), loadSystemConfig()])
    await loadSessionData()
    await restoreActiveDispatchTask()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    loading.value = false
  }
}

function getDispatchTaskIdFromExternalSessionId(externalSessionId) {
  const normalized = String(externalSessionId || '').trim()
  const dispatchPrefix = 'dispatch_'
  if (!normalized.startsWith(dispatchPrefix)) {
    return ''
  }
  return normalized.slice(dispatchPrefix.length)
}

// Re-attach to the dispatch task associated with the selected session.
// This runs on initial page refresh and on later session switches.
async function restoreActiveDispatchTask() {
  const taskId = getDispatchTaskIdFromExternalSessionId(selectedExternalSessionId.value)
  if (!taskId) {
    clearActiveTask()
    return
  }

  clearActiveTask()

  try {
    const task = await fetchJson(`${apiBase}/api/v1/dispatch/${taskId}`)
    if (!task) {
      return
    }

    // Keep the dispatch view active even for terminal tasks so historical execution is visible.
    dispatchTaskId.value = task.id
    dispatchActiveTask.value = task

    const nonTerminalStatuses = ['queued', 'running', 'awaiting_input', 'paused']
    const isLive = nonTerminalStatuses.includes(task.status)

    if (isLive) {
      on('status', handleTaskStatus)
      on('content_delta', handleTaskEvent)
      on('tool_call', handleTaskEvent)
      on('await_input', handleTaskEvent)
      on('completed', handleTaskEvent)
      on('error', handleTaskEvent)
      on('cancelled', handleTaskEvent)

      if (!wsConnected.value) {
        wsConnect()
      }
      subscribe(task.id)
    }

    const eventsData = await fetchJson(`${apiBase}/api/v1/dispatch/${task.id}/events?limit=2000`)
    const items = eventsData.items || eventsData || []
    dispatchTaskEvents.value = items.map((evt) => ({
      id: evt.id,
      event_type: evt.event_type,
      event_name: evt.event_name || evt.event_type || '',
      status: evt.status || null,
      seq: Number.isFinite(evt.seq) ? evt.seq : Number.MAX_SAFE_INTEGER,
      run_id: evt.run_id || null,
      tool_call_id: evt.tool_call_id || null,
      payload: evt.payload,
      created_at: evt.created_at || new Date().toISOString(),
    }))
    dispatchTaskEvents.value.sort((a, b) => {
      const seqA = Number.isFinite(a.seq) ? a.seq : Number.MAX_SAFE_INTEGER
      const seqB = Number.isFinite(b.seq) ? b.seq : Number.MAX_SAFE_INTEGER
      if (seqA !== seqB) return seqA - seqB
      return new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
    })
  } catch (error) {
    console.warn('Failed to restore dispatch task after session reload', error)
    clearActiveTask()
  }
}

function resetCreateProjectForm() {
  createRepoEnabled.value = false
  createProjectForm.value = {
    repository_url: githubRepos.value[0]?.url || '',
    name: '',
    description: '',
    private: false,
  }
}

function openProjectCreateModal() {
  resetCreateProjectForm()
  isProjectCreateModalOpen.value = true
}

function closeProjectCreateModal() {
  if (creatingProject.value) {
    return
  }
  isProjectCreateModalOpen.value = false
}

function closeProjectEditModal() {
  if (updatingProject.value) {
    return
  }
  isProjectEditModalOpen.value = false
  editProjectId.value = ''
}

function openProjectEditModal(item) {
  editProjectId.value = item.id
  editProjectForm.value = {
    name: item.name,
    description: item.description || '',
  }
  isProjectEditModalOpen.value = true
}

function getRepoChoices() {
  return githubRepos.value
}

function handleRepositoryChange() {
  const repo = selectedCreateRepo.value
  if (!repo) {
    return
  }

  if (!createProjectForm.value.name.trim()) {
    createProjectForm.value.name = repo.name
  }

  if (!createProjectForm.value.description.trim() && repo.description?.trim()) {
    createProjectForm.value.description = repo.description.trim()
  }
}

async function loadProjects() {
  const data = await fetchJson(`${apiBase}/api/v1/projects`)
  projects.value = data.items || []
}

async function loadTaskBoardItems() {
  const params = new URLSearchParams()
  if (taskBoardProjectFilter.value.trim()) {
    params.set('project_id', taskBoardProjectFilter.value.trim())
  }
  if (taskBoardKeyword.value.trim()) {
    params.set('keyword', taskBoardKeyword.value.trim())
  }
  const query = params.toString()
  const endpoint = query ? `${apiBase}/api/v1/task-board?${query}` : `${apiBase}/api/v1/task-board`
  const data = await fetchJson(endpoint)
  taskBoardItems.value = data.items || []
  // Default-collapse all parent nodes so kanban starts compact
  collapseAllTaskNodes()
}

function collapseAllTaskNodes() {
  const tree = buildTaskTree(taskBoardItems.value)
  const parentIds = new Set()
  const walk = (nodes) => {
    for (const node of nodes) {
      if (node.children.length) parentIds.add(node.id)
      walk(node.children)
    }
  }
  walk(tree)
  collapsedTaskNodes.value = parentIds
}

function resetTaskBoardCreateForm() {
  taskBoardCreateForm.value = {
    name: '',
    description: '',
    ai_platform: 'hermes',
    project_id: '',
    upstream_task_id: '',
    parent_task_id: '',
    status: 'draft',
    status_reason: '',
    priority: 3,
  }
}

function openTaskBoardByProject(project) {
  taskBoardProjectFilter.value = project.id
  taskBoardKeyword.value = ''
  taskBoardStatusFilter.value = ''
  activePage.value = 'task-board'
}

async function startConversationFromTask(task) {
  if (startingConversationFromTask.value) return
  startingConversationFromTask.value = true
  errorMessage.value = ''
  try {
    const projectContext = resolveTaskProjectContext(task)
    const systemPrompt = buildTaskSystemPrompt(task, projectContext)
    const platform = task.ai_platform || 'hermes'
    const promptMessage = buildTaskStartMessage(task, projectContext)

    // Use dispatch orchestration layer instead of direct SSE (ADR-0004)
    const dispatchTask = await createDispatchTask({
      aiPlatform: platform,
      initialPrompt: promptMessage,
      systemPrompt,
      model: selectedModel.value || '',
      skills: [...selectedSkills.value],
      mcpServers: [...selectedMcpServers.value],
      taskBoardItemId: task.id,
    })

    // Create a session entry so the conversation appears in the list
    const externalSessionId = dispatchTask.external_session_id || dispatchTask.id
    await postJson(`${apiBase}/api/v1/events/ingest`, {
      platform,
      event_id: `evt_init_${dispatchTask.id}`,
      event_type: 'session_started',
      external_session_id: externalSessionId,
      title: task.name,
      payload_json: {
        source: 'task-board',
        task_board_item_id: task.id,
        dispatch_task_id: dispatchTask.id,
      },
      message: {
        role: 'user',
        content: promptMessage,
      },
    })

    // Inject progress system message
    await postJson(`${apiBase}/api/v1/events/ingest`, {
      platform,
      event_id: `evt_progress_${dispatchTask.id}`,
      event_type: 'dispatch_created',
      external_session_id: externalSessionId,
      title: task.name,
      payload_json: { source: 'task-board', status: 'running', dispatch_task_id: dispatchTask.id },
      message: { role: 'system', content: '🔄 已提交 Dispatch 任务，等待 AI Agent 处理中...' },
    })

    // Refresh sessions list and select the new session
    await loadSessions()
    selectedSessionId.value = sessions.value.find(
      (s) => s.platform === platform && s.external_session_id === externalSessionId,
    )?.id || selectedSessionId.value

    // Switch to chat page to show the dispatch task progress
    activePage.value = 'chat'

    // Auto-scroll to bottom and reset user scroll state
    resetTimelineScroll()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    startingConversationFromTask.value = false
  }
}

function buildTaskSystemPrompt(task, projectContext = null) {
  const lines = [`[Task Context]`]
  lines.push(`Task: ${task.name}`)
  if (task.description) lines.push(`Description: ${task.description}`)
  lines.push(`Status: ${taskBoardStatusLabelMap[task.status] || task.status}`)
  lines.push(`AI Platform: ${task.ai_platform || 'hermes'}`)

  const context = projectContext || resolveTaskProjectContext(task)
  if (context?.name || context?.repositoryName || context?.repositoryUrl) {
    lines.push(`\n[Project]`)
    if (context.name) lines.push(`Project: ${context.name}`)
    if (context.repositoryName) lines.push(`Repository: ${context.repositoryName}`)
    if (context.repositoryUrl) lines.push(`Repository URL: ${context.repositoryUrl}`)
  }

  if (task.upstream_task_name) lines.push(`\n[Upstream Dependency] ${task.upstream_task_name}`)
  if (task.parent_task_name) lines.push(`[Parent Task] ${task.parent_task_name}`)
  return lines.join('\n')
}

function buildTaskStartMessage(task, projectContext = null) {
  const context = projectContext || resolveTaskProjectContext(task)
  const lines = ['请根据任务上下文开始工作。']
  if (context?.name) {
    lines.push(`关联项目: ${context.name}`)
  }
  if (context?.repositoryName) {
    lines.push(`仓库: ${context.repositoryName}`)
  }
  if (context?.repositoryUrl) {
    lines.push(`仓库地址: ${context.repositoryUrl}`)
  }
  lines.push(`任务: ${task.name}`)
  return lines.join('\n')
}

function resolveTaskProjectContext(task) {
  const projectById = task.project_id
    ? projects.value.find((item) => item.id === task.project_id)
    : null
  const repositoryUrl = task.project_repository_url || projectById?.repository_url || ''
  const repositoryName = task.project_repository_name
    || projectById?.repository_name
    || inferRepositoryNameFromUrl(repositoryUrl)
    || ''

  return {
    name: task.project_name || projectById?.name || '',
    repositoryName,
    repositoryUrl,
  }
}

function inferRepositoryNameFromUrl(url) {
  if (!url) return ''
  const trimmed = String(url).trim().replace(/\/+$/, '')
  const parts = trimmed.split('/')
  return parts.length > 0 ? (parts[parts.length - 1] || '') : ''
}

function openTaskBoardCreateModal() {
  resetTaskBoardCreateForm()
  isTaskBoardCreateModalOpen.value = true
}

function closeTaskBoardCreateModal() {
  if (creatingTaskBoardItem.value) {
    return
  }
  isTaskBoardCreateModalOpen.value = false
}

function openTaskBoardEditModal(item) {
  editingTaskBoardItemId.value = item.id
  taskBoardEditForm.value = {
    name: item.name,
    description: item.description || '',
    ai_platform: item.ai_platform || 'hermes',
    project_id: item.project_id || '',
    upstream_task_id: item.upstream_task_id || '',
    parent_task_id: item.parent_task_id || '',
    status: item.status || 'draft',
    status_reason: item.status_reason || '',
    priority: item.priority ?? 3,
  }
  isTaskBoardEditModalOpen.value = true
}

function closeTaskBoardEditModal() {
  if (updatingTaskBoardItem.value) {
    return
  }
  isTaskBoardEditModalOpen.value = false
  editingTaskBoardItemId.value = ''
}

function openTaskBoardDetailModal(item) {
  taskBoardDetailItem.value = item
}

function closeTaskBoardDetailModal() {
  taskBoardDetailItem.value = null
}

function taskBoardDetailField(value) {
  const normalized = String(value || '').trim()
  return normalized || '-'
}

function requiresTaskStatusReason(status) {
  return status === 'blocked' || status === 'cancelled'
}

function normalizeTaskStatusReason(status, reason) {
  if (!requiresTaskStatusReason(status)) {
    return ''
  }
  return String(reason || '').trim()
}

function getTaskStatusReasonPreview(item, maxLength = 96) {
  const reason = String(item?.status_reason || '').trim()
  if (!reason) {
    return ''
  }
  if (reason.length <= maxLength) {
    return reason
  }
  return `${reason.slice(0, maxLength).trimEnd()}...`
}

function ensureTaskStatusReasonBeforeSave(formState) {
  const normalizedReason = normalizeTaskStatusReason(formState.status, formState.status_reason)
  if (requiresTaskStatusReason(formState.status) && !normalizedReason) {
    throw new Error('阻塞或取消任务时必须填写原因')
  }
  return normalizedReason
}

function buildTaskBoardUpdatePayload(item, patch) {
  const nextStatus = patch.status ?? item.status ?? 'draft'
  const nextReasonSource = Object.prototype.hasOwnProperty.call(patch, 'status_reason')
    ? patch.status_reason
    : (item.status_reason || '')
  return {
    name: item.name,
    description: item.description || '',
    ai_platform: item.ai_platform || 'hermes',
    status: nextStatus,
    status_reason: normalizeTaskStatusReason(nextStatus, nextReasonSource),
    priority: item.priority ?? 3,
    project_id: item.project_id || null,
    upstream_task_id: item.upstream_task_id || null,
    parent_task_id: item.parent_task_id || null,
    ...patch,
  }
}

async function updateTaskBoardItemQuick(item, patch) {
  if (!item?.id || quickUpdatingTaskBoardItemId.value === item.id) {
    return
  }
  const targetStatus = patch.status ?? item.status ?? 'draft'
  if (
    requiresTaskStatusReason(targetStatus)
    && targetStatus !== (item.status ?? 'draft')
    && !Object.prototype.hasOwnProperty.call(patch, 'status_reason')
  ) {
    openTaskBoardEditModal({ ...item, status: targetStatus, status_reason: '' })
    errorMessage.value = `请先填写${taskBoardStatusLabelMap[targetStatus] || targetStatus}原因`
    return
  }
  quickUpdatingTaskBoardItemId.value = item.id
  errorMessage.value = ''
  try {
    const updated = await patchJson(`${apiBase}/api/v1/task-board/${item.id}`, buildTaskBoardUpdatePayload(item, patch))
    taskBoardItems.value = taskBoardItems.value.map((entry) => (entry.id === item.id ? updated : entry))
    if (taskBoardDetailItem.value?.id === item.id) {
      taskBoardDetailItem.value = updated
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    quickUpdatingTaskBoardItemId.value = ''
  }
}

function handleTaskBoardDragStart(item, event) {
  if (!item?.id) return
  draggingTaskBoardItemId.value = item.id
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', item.id)
}

function handleTaskBoardDragEnd() {
  draggingTaskBoardItemId.value = ''
}

async function handleTaskBoardDrop(status, event) {
  const taskId = event.dataTransfer.getData('text/plain') || draggingTaskBoardItemId.value
  draggingTaskBoardItemId.value = ''
  const item = taskBoardItems.value.find((entry) => entry.id === taskId)
  if (!item || item.status === status) {
    return
  }
  await updateTaskBoardItemQuick(item, { status })
}

async function updateTaskBoardPriority(item, event) {
  const priority = Number(event.target.value)
  if (!item || !Number.isInteger(priority) || item.priority === priority) {
    return
  }
  await updateTaskBoardItemQuick(item, { priority })
}

function buildTaskBoardPayload(formState) {
  const normalizedReason = ensureTaskStatusReasonBeforeSave(formState)
  return {
    name: formState.name.trim(),
    description: formState.description.trim(),
    ai_platform: formState.ai_platform.trim() || 'hermes',
    status: formState.status,
    status_reason: normalizedReason,
    priority: formState.priority,
    project_id: formState.project_id || null,
    upstream_task_id: formState.upstream_task_id || null,
    parent_task_id: formState.parent_task_id || null,
  }
}

async function submitCreateTaskBoardItem() {
  if (creatingTaskBoardItem.value || !taskBoardCreateForm.value.name.trim()) {
    return
  }
  creatingTaskBoardItem.value = true
  errorMessage.value = ''
  try {
    await postJson(`${apiBase}/api/v1/task-board`, buildTaskBoardPayload(taskBoardCreateForm.value))
    isTaskBoardCreateModalOpen.value = false
    await loadTaskBoardItems()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    creatingTaskBoardItem.value = false
  }
}

async function submitEditTaskBoardItem() {
  if (updatingTaskBoardItem.value || !editingTaskBoardItemId.value || !taskBoardEditForm.value.name.trim()) {
    return
  }
  updatingTaskBoardItem.value = true
  errorMessage.value = ''
  try {
    await patchJson(`${apiBase}/api/v1/task-board/${editingTaskBoardItemId.value}`, buildTaskBoardPayload(taskBoardEditForm.value))
    isTaskBoardEditModalOpen.value = false
    editingTaskBoardItemId.value = ''
    await loadTaskBoardItems()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    updatingTaskBoardItem.value = false
  }
}

async function deleteTaskBoardItem(item) {
  if (!item?.id || deletingTaskBoardItemId.value) {
    return
  }
  const confirmed = window.confirm(`确认删除任务「${item.name}」？`)
  if (!confirmed) {
    return
  }
  deletingTaskBoardItemId.value = item.id
  errorMessage.value = ''
  try {
    await deleteJson(`${apiBase}/api/v1/task-board/${item.id}`)
    await loadTaskBoardItems()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    deletingTaskBoardItemId.value = ''
  }
}

async function loadGithubRepos() {
  try {
    const data = await fetchJson(`${apiBase}/api/v1/projects/github/repos`)
    githubRepos.value = data || []
    if (!createProjectForm.value.repository_url && githubRepos.value.length > 0) {
      createProjectForm.value.repository_url = githubRepos.value[0].url
    }
  } catch {
    githubRepos.value = []
  }
}

async function loadSystemConfig() {
  try {
    const data = await fetchJson(`${apiBase}/api/v1/system/config`)
    githubTokenConfigured.value = Boolean(data?.github_token_configured)
  } catch {
    githubTokenConfigured.value = false
  }
}

async function saveGithubToken() {
  if (githubTokenSaving.value) {
    return
  }
  githubTokenSaving.value = true
  errorMessage.value = ''
  try {
    const payload = { github_token: githubTokenDraft.value.trim() }
    const data = await putJson(`${apiBase}/api/v1/system/config/github-token`, payload)
    githubTokenConfigured.value = Boolean(data?.github_token_configured)
    githubTokenDraft.value = ''
    await loadGithubRepos()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    githubTokenSaving.value = false
  }
}

async function createGithubRepo() {
  if (creatingGithubRepo.value || !createProjectForm.value.name.trim()) {
    return
  }
  creatingGithubRepo.value = true
  errorMessage.value = ''
  try {
    const payload = {
      name: createProjectForm.value.name.trim(),
      description: createProjectForm.value.description.trim(),
      private: Boolean(createProjectForm.value.private),
    }
    const created = await postJson(`${apiBase}/api/v1/projects/github/repos`, payload)
    createProjectForm.value.repository_url = created.url
    await loadGithubRepos()
    await submitCreateProject()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    creatingGithubRepo.value = false
  }
}

async function submitCreateProject() {
  const projectName = createProjectForm.value.name.trim()
  if (creatingProject.value || !projectName) {
    return
  }
  if (!createRepoEnabled.value && !createProjectForm.value.repository_url.trim()) {
    return
  }
  creatingProject.value = true
  errorMessage.value = ''
  try {
    const payload = {
      repository_url: createProjectForm.value.repository_url.trim(),
      name: projectName,
      description: createProjectForm.value.description.trim(),
    }
    await postJson(`${apiBase}/api/v1/projects`, payload)
    isProjectCreateModalOpen.value = false
    await loadProjects()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    creatingProject.value = false
  }
}

async function submitEditProject() {
  if (updatingProject.value || !editProjectId.value || !editProjectForm.value.name.trim()) {
    return
  }
  updatingProject.value = true
  errorMessage.value = ''
  try {
    const payload = {
      name: editProjectForm.value.name.trim(),
      description: editProjectForm.value.description.trim(),
    }
    await patchJson(`${apiBase}/api/v1/projects/${editProjectId.value}`, payload)
    isProjectEditModalOpen.value = false
    editProjectId.value = ''
    await loadProjects()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    updatingProject.value = false
  }
}

async function deleteProject(item) {
  if (!item?.id || deletingProjectId.value) {
    return
  }
  const confirmed = window.confirm(`确认删除项目「${item.name}」？`)
  if (!confirmed) {
    return
  }
  deletingProjectId.value = item.id
  errorMessage.value = ''
  try {
    await deleteJson(`${apiBase}/api/v1/projects/${item.id}`)
    await loadProjects()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    deletingProjectId.value = ''
  }
}

async function deleteSession(sessionId) {
  if (!sessionId || deletingSessionId.value || clearingSessions.value) {
    return
  }

  const target = sessions.value.find((item) => item.id === sessionId)
  const title = target?.title || target?.external_session_id || sessionId
  const confirmed = window.confirm(`确认删除对话「${title}」？`)
  if (!confirmed) {
    return
  }

  deletingSessionId.value = sessionId
  errorMessage.value = ''
  try {
    const response = await fetch(`${apiBase}/api/v1/sessions/${sessionId}`, { method: 'DELETE' })
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status}`)
    }
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
    if (selectedSessionId.value) {
      await loadSessionData()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    deletingSessionId.value = ''
  }
}

async function clearAllSessions() {
  if (clearingSessions.value || deletingSessionId.value || sessions.value.length === 0) {
    return
  }

  const confirmed = window.confirm('确认清空全部对话？此操作不可恢复。')
  if (!confirmed) {
    return
  }

  clearingSessions.value = true
  errorMessage.value = ''
  try {
    const response = await fetch(`${apiBase}/api/v1/sessions`, { method: 'DELETE' })
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status}`)
    }
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
  if (
    event.key !== 'Enter'
    || event.shiftKey
    || event.ctrlKey
    || event.altKey
    || event.metaKey
    || event.isComposing
  ) {
    return
  }
  event.preventDefault()
  sendMessageToHermes()
}

function handleCreateInitialMessageKeydown(event) {
  if (
    event.key !== 'Enter'
    || event.shiftKey
    || event.ctrlKey
    || event.altKey
    || event.metaKey
    || event.isComposing
  ) {
    return
  }
  event.preventDefault()
  submitCreateConversation()
}

async function sendMessageToHermes() {
  const trimmed = composerText.value.trim()
  if (!trimmed || sending.value) {
    return
  }

  sending.value = true
  errorMessage.value = ''

  try {
    // A second user message while the AI is still running is an intentional correction.
    // Interrupt the current run (non-terminal), append the correction, and restart.
    if (dispatchIsRunning.value && dispatchIsCancellable.value) {
      composerText.value = ''
      await interruptDispatchTask(trimmed)
    } else if (dispatchTaskId.value && dispatchIsResumable.value) {
      composerText.value = ''
      await resumeDispatchTask(trimmed)
    } else {
      if (dispatchActiveTask.value && isTerminalDispatchStatus(dispatchActiveTask.value.status)) {
        clearActiveTask()
      }

      if (!dispatchTaskId.value) {
        composerText.value = ''
        if (!wsConnected.value) wsConnect()
        await createDispatchTask({
          aiPlatform: blankChatProvider.value || 'hermes',
          initialPrompt: trimmed,
          model: selectedModel.value || '',
          skills: [...selectedSkills.value],
          mcpServers: [...selectedMcpServers.value],
          externalSessionId: selectedExternalSessionId.value || null,
        })
        // Exit blank chat mode after dispatch creation (now has a real session)
        isBlankChatMode.value = false
      }
    }

    // Auto-scroll to bottom and reset user scroll state (new message sent)
    resetTimelineScroll()
  } catch (error) {
    if (error.name !== 'AbortError') {
      errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
    }
  } finally {
    sending.value = false
  }
}

watch(blankChatProviders, (providers) => {
  if (!providers.includes(blankChatProvider.value)) {
    blankChatProvider.value = providers.includes('hermes') ? 'hermes' : providers[0]
  }
})

watch(selectedSessionId, async () => {
  resetTimelineScroll()
  if (!selectedSessionId.value) {
    timeline.value = { messages: [], events: [] }
    clearActiveTask()
    // Keep cockpit for blank chat provider list
    if (!isBlankChatMode.value) {
      cockpit.value = null
    }
    return
  }
  try {
    errorMessage.value = ''
    await loadSessionData()
    await restoreActiveDispatchTask()
    scrollToBottom(true)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  }
})

watch([taskBoardProjectFilter, taskBoardKeyword], async () => {
  if (activePage.value !== 'task-board') {
    return
  }
  try {
    errorMessage.value = ''
    await loadTaskBoardItems()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  }
})

watch(activePage, async (page) => {
  if (page !== 'task-board') {
    return
  }
  try {
    errorMessage.value = ''
    await Promise.all([loadProjects(), loadTaskBoardItems()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  }
})

onMounted(async () => {
  // Initialize WebSocket connection for dispatch orchestration (ADR-0004)
  wsConnect()
  await refreshData()
})

// Cleanup active dispatch task on unmount
onUnmounted(() => {
  clearActiveTask()
})
</script>

<template>
  <main class="app-shell">
    <div class="bg-layer"></div>

    <section class="cockpit-wrap">
      <header class="topbar panel">
        <div class="brand-block">
          <div class="brand-title-row">
            <img class="brand-logo" src="/src/assets/logo-sjt-a3-icon.svg" alt="枢界台 Logo" />
            <h1 class="title">枢界台 · 会话驾驶舱</h1>
          </div>
          <p class="subtitle">全屏自适应 · 多平台对话任务看板</p>
        </div>

        <nav class="top-nav" aria-label="页面切换">
          <button type="button" class="top-nav-btn" :class="{ 'top-nav-btn-active': activePage === 'chat' }" @click="activePage = 'chat'">
            <span class="top-nav-btn-icon" aria-hidden="true">💬</span>
            <span class="top-nav-btn-label">会话中心</span>
          </button>
          <button type="button" class="top-nav-btn" :class="{ 'top-nav-btn-active': activePage === 'projects' }" @click="activePage = 'projects'">
            <span class="top-nav-btn-icon" aria-hidden="true">📁</span>
            <span class="top-nav-btn-label">项目管理</span>
          </button>
          <button type="button" class="top-nav-btn" :class="{ 'top-nav-btn-active': activePage === 'task-board' }" @click="activePage = 'task-board'">
            <span class="top-nav-btn-icon" aria-hidden="true">🗂️</span>
            <span class="top-nav-btn-label">任务看板</span>
          </button>
          <button type="button" class="top-nav-btn" :class="{ 'top-nav-btn-active': activePage === 'model-config' }" @click="activePage = 'model-config'">
            <span class="top-nav-btn-icon" aria-hidden="true">🤖</span>
            <span class="top-nav-btn-label">模型配置</span>
          </button>
          <button type="button" class="top-nav-btn" :class="{ 'top-nav-btn-active': activePage === 'skills-catalog' }" @click="switchToSkillsCatalog">
            <span class="top-nav-btn-icon" aria-hidden="true">🧩</span>
            <span class="top-nav-btn-label">Skills 库</span>
          </button>
          <button type="button" class="top-nav-btn" :class="{ 'top-nav-btn-active': activePage === 'system-config' }" @click="activePage = 'system-config'">
            <span class="top-nav-btn-icon" aria-hidden="true">⚙️</span>
            <span class="top-nav-btn-label">系统配置</span>
          </button>
          <button type="button" class="top-nav-btn" :class="{ 'top-nav-btn-active': activePage === 'dispatch-history' }" @click="switchToDispatchHistory">
            <span class="top-nav-btn-icon" aria-hidden="true">📋</span>
            <span class="top-nav-btn-label">调度历史</span>
          </button>
        </nav>
      </header>

      <div v-if="errorMessage" class="error panel">{{ errorMessage }}</div>

      <section v-if="activePage === 'chat'" class="main-grid chat-grid">
        <article class="panel tasks-panel">
          <div class="tasks-panel-header">
            <h2>对话列表</h2>
            <div class="tasks-panel-actions">
              <button type="button" class="session-new-btn" @click="createNewConversation">新建对话</button>
              <button
                type="button"
                class="session-clear-btn"
                :disabled="clearingSessions || deletingSessionId || sessions.length === 0"
                @click="clearAllSessions"
              >
                {{ clearingSessions ? '清空中...' : '清空对话' }}
              </button>
            </div>
          </div>

          <div
            class="pinned-ai-entry"
            :class="{ 'pinned-ai-entry-active': isBlankChatMode }"
            @click="activateBlankChat"
          >
            <div class="pinned-ai-icon">🤖</div>
            <div class="pinned-ai-body">
              <div class="pinned-ai-title">AI Assistant</div>
              <div class="pinned-ai-subtitle">AI provider: {{ blankChatProvider || 'hermes' }}</div>
            </div>
            <select
              v-if="blankChatProviders.length > 1"
              v-model="blankChatProvider"
              class="pinned-ai-provider-select"
              @click.stop
            >
              <option v-for="provider in blankChatProviders" :key="provider" :value="provider">{{ provider }}</option>
            </select>
          </div>

          <div class="conversation-only-list scrollbar-themed-auto-hide">
            <div
              v-for="item in sessions"
              :key="item.id"
              class="task conversation-task"
              :class="{ 'conversation-task-active': item.id === selectedSessionId }"
            >
              <button
                type="button"
                class="conversation-task-main"
                @click="selectConversation(item.id, item.external_session_id)"
              >
                <div class="conversation-task-header">
                  <div class="task-title conversation-task-title">{{ item.title }}</div>
                  <span class="conversation-platform-pill">{{ item.platform }}</span>
                </div>
                <div class="conversation-task-subtitle">{{ item.external_session_id }}</div>
                <div class="conversation-task-meta-row">
                  <span class="conversation-meta-label">开始时间</span>
                  <span class="conversation-meta-value">{{ formatSessionTime(item.started_at) }}</span>
                </div>
              </button>
              <button
                type="button"
                class="card-delete-btn conversation-delete-btn"
                :aria-label="`删除对话 ${item.title}`"
                :disabled="clearingSessions || deletingSessionId === item.id"
                @click="deleteSession(item.id)"
              >
                <span aria-hidden="true">×</span>
              </button>
            </div>
            <div v-if="sessions.length === 0" class="muted">暂无会话</div>
          </div>
        </article>

        <article class="panel timeline-panel">
          <div class="timeline-panel-header">
            <h2>对话时间线</h2>
            <!-- Dispatch task status indicator (ADR-0004) -->
            <div v-if="dispatchActiveTask" class="dispatch-status-bar" :class="dispatchStatusClassMap[dispatchActiveTask.status] || ''">
              <span class="dispatch-status-label">{{ dispatchStatusLabelMap[dispatchActiveTask.status] || dispatchActiveTask.status }}</span>
              <span class="dispatch-task-id">{{ dispatchActiveTask.id }}</span>
              <div class="dispatch-actions">
                <button v-if="dispatchIsCancellable" type="button" class="dispatch-action-btn dispatch-cancel-btn" @click="cancelDispatchTask">取消任务</button>
                <button v-if="dispatchIsResumable" type="button" class="dispatch-action-btn dispatch-resume-btn" @click="clearActiveTask">关闭任务</button>
                <button v-if="dispatchActiveTask.status === 'completed' || dispatchActiveTask.status === 'failed' || dispatchActiveTask.status === 'cancelled'" type="button" class="dispatch-action-btn dispatch-close-btn" @click="clearActiveTask">清除</button>
              </div>
            </div>
            <div v-if="dispatchError" class="dispatch-friendly-error">{{ dispatchError }}</div>
          </div>

          <div class="timeline-scroll scrollbar-themed" ref="timelineScrollRef" @scroll="onTimelineScroll">
            <div v-if="displayMessages.length === 0 && dispatchTaskId && dispatchActiveTask && ['queued','running','awaiting_input','paused'].includes(dispatchActiveTask.status)" class="muted">⏳ 正在恢复任务进度，接入实时数据流中...</div>
            <div v-else-if="displayMessages.length === 0 && dispatchTaskId" class="muted">📭 暂无执行记录</div>
            <div v-else-if="displayMessages.length === 0" class="muted">暂无消息</div>
            <div
              v-for="message in displayMessages"
              :key="message.id"
              class="timeline-item"
              :class="[
                messageSideClass(message.role),
                message.meta_json?.thinking ? 'msg-thinking' : '',
                message.meta_json?.tool_call ? 'msg-tool' : '',
                message.meta_json?.streaming ? 'streaming' : '',
              ]"
            >
              <!-- Thinking bubble (collapsible) -->
              <template v-if="message.meta_json?.thinking">
                <details class="thinking-bubble">
                  <summary class="thinking-summary">
                    <span class="thinking-icon">🧠</span> 思考过程
                    <span class="thinking-chars">{{ message.content.length }} 字符</span>
                  </summary>
                  <pre class="thinking-content">{{ message.content }}</pre>
                </details>
              </template>

              <!-- Tool call bubble -->
              <template v-else-if="message.meta_json?.tool_call">
                <div class="tool-bubble" :class="message.meta_json?.completed ? 'tool-done' : 'tool-running'">
                  <div class="tool-header">
                    <span class="tool-status-icon">{{ message.meta_json?.tool_error ? '❌' : message.meta_json?.completed ? '✅' : '⚙️' }}</span>
                    <span class="tool-name">{{ message.content }}</span>
                    <span v-if="message.meta_json?.completed && message.meta_json?.duration_ms != null" class="tool-duration">{{ message.meta_json.duration_ms }}ms</span>
                    <span v-else-if="!message.meta_json?.completed" class="tool-spinning">…</span>
                  </div>
                  <div v-if="message.meta_json?.tool_error" class="tool-error-text">{{ message.meta_json.tool_error }}</div>
                  <details v-if="message.meta_json?.function_args" class="tool-args-details">
                    <summary>参数</summary>
                    <pre class="tool-args-pre">{{ message.meta_json.function_args }}</pre>
                  </details>
                </div>
              </template>

              <!-- Normal message -->
              <template v-else>
                <div class="role-chip" :class="roleClass(message.role)">{{ roleLabelMap[message.role] || message.role }}</div>
                <div class="timeline-meta">
                  {{ new Date(message.created_at).toLocaleString() }}
                  <span v-if="message.meta_json?.streaming" class="streaming-indicator">生成中…</span>
                </div>
                <div class="timeline-content" v-html="message.role === 'assistant' ? renderMarkdown(message.content) : message.content"></div>
              </template>
            </div>
          </div>

          <form class="chat-composer" @submit.prevent="sendMessageToHermes">
            <div class="conversation-latest-status" :class="`status-${conversationLatestStatus.tone}`">
              <span class="latest-status-label">会话状态</span>
              <span class="latest-status-text">{{ conversationLatestStatus.text }}</span>
              <button v-if="currentLinkedTask" type="button" class="status-task-chip" @click="openLinkedTaskFromStatus">
                {{ currentLinkedTask.project_name || '未关联项目' }} · {{ currentLinkedTask.name }} · {{ taskBoardStatusLabelMap[currentLinkedTask.status] || currentLinkedTask.status }} · {{ KANBAN_PRIORITY_LABELS[getTaskPriority(currentLinkedTask)] }}
              </button>
              <span v-if="requiresTaskStatusReason(currentLinkedTask?.status) && currentLinkedTask?.status_reason" class="status-task-reason-chip">
                原因：{{ getTaskStatusReasonPreview(currentLinkedTask, 120) }}
              </span>
              <span v-if="currentLoadedSkills.length" class="status-skill-group">
                <button v-for="skill in currentLoadedSkills" :key="skill.name + skill.file_path" type="button" class="status-skill-chip" @click="openSkillDetail(skill)">{{ skill.name }}</button>
              </span>
              <span class="latest-status-time">{{ conversationLatestStatus.time }}</span>
            </div>
            <textarea
              v-model="composerText"
              class="composer-input"
              :disabled="sending"
              :placeholder="dispatchIsRunning ? '输入修正内容，将打断当前 AI 回复并重新发送' : (dispatchAwaitingInput ? 'AI 正在等待你的回复...' : '输入消息，直接与 AI 对话')"
              @keydown="handleComposerKeydown"
            ></textarea>
            <button v-if="dispatchIsCancellable" class="composer-send composer-cancel" type="button" @click="cancelDispatchTask">
              取消任务
            </button>
            <button v-else class="composer-send" type="submit" :disabled="sending || !composerText.trim()">
              {{ sending ? '处理中...' : (dispatchIsRunning ? '打断并发送' : '发送') }}
            </button>
          </form>
        </article>

        <article class="panel state-panel placeholder-state-panel">
          <h2>会话状态</h2>
          <div class="muted">状态已移动到输入框上方，仅显示最新状态。</div>
        </article>
      </section>

      <section v-else-if="activePage === 'projects'" class="main-grid project-grid">
        <article class="panel project-panel">
          <div class="project-panel-header">
            <h2>项目管理</h2>
            <div class="project-actions">
              <input v-model="projectSearch" class="project-search" placeholder="搜索项目名称/编号/仓库" />
              <button type="button" class="session-new-btn" @click="openProjectCreateModal">新建项目</button>
            </div>
          </div>

          <div class="project-list scrollbar-themed" v-if="filteredProjects.length > 0">
            <div v-for="item in filteredProjects" :key="item.id" class="project-card project-card-clickable" @click="openTaskBoardByProject(item)">
              <div class="project-card-top">
                <div class="project-title-wrap">
                  <div class="project-name">{{ item.name }}</div>
                  <div class="project-code">{{ item.code }}</div>
                </div>
                <div class="project-card-actions">
                  <button type="button" class="project-btn" @click="openProjectEditModal(item)">编辑</button>
                  <button type="button" class="card-delete-btn" :disabled="deletingProjectId === item.id" :aria-label="`删除项目 ${item.name}`" @click="deleteProject(item)">
                    <span aria-hidden="true">×</span>
                  </button>
                </div>
              </div>
              <div class="project-desc">{{ item.description || '暂无简介' }}</div>
              <div class="project-meta">
                <span class="project-meta-label">仓库</span>
                <span class="project-meta-value">{{ item.repository_name }}</span>
              </div>
              <div class="project-meta">
                <span class="project-meta-label">更新时间</span>
                <span class="project-meta-value">{{ formatSessionTime(item.updated_at) }}</span>
              </div>
            </div>
          </div>
          <div v-else class="project-empty">暂无项目，点击“新建项目”开始。</div>
        </article>
      </section>

<section v-else-if="activePage === 'task-board'" class="main-grid task-board-grid">
        <article class="panel task-board-panel">
          <div class="task-board-panel-header">
            <h2>任务看板</h2>
            <div class="task-board-actions">
              <select v-model="taskBoardProjectFilter" class="task-board-filter-select">
                <option v-for="opt in taskBoardProjectOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
              </select>
              <input v-model="taskBoardKeyword" class="project-search task-board-search" placeholder="搜索任务名称/描述" />
              <button type="button" class="session-new-btn" @click="openTaskBoardCreateModal">新建任务</button>
            </div>
          </div>

          <!-- Matrix Kanban: columns=statuses, rows=projects; cards render parent/child task trees -->
          <div class="kanban-matrix-wrap scrollbar-themed">
            <div class="kanban-matrix-header" :style="kanbanMatrixStyle">
              <div class="kanban-row-label-head">项目</div>
              <div v-for="s in KANBAN_STATUSES" :key="s" class="kanban-col-header" :class="['kanban-col-' + s, { 'kanban-col-collapsed': isKanbanStatusCollapsed(s) }]">
                <span class="kanban-status-dot" :class="'task-status-' + s"></span>
                <span class="kanban-col-title">{{ taskBoardStatusLabelMap[s] }}</span>
                <button
                  v-if="isKanbanStatusCollapsible(s)"
                  type="button"
                  class="kanban-col-toggle"
                  :aria-label="isKanbanStatusCollapsed(s) ? '展开已完成列' : '折叠已完成列'"
                  :title="isKanbanStatusCollapsed(s) ? '展开已完成列' : '折叠已完成列'"
                  @click.stop="toggleKanbanStatusColumn(s)"
                >
                  {{ isKanbanStatusCollapsed(s) ? '◀' : '▶' }}
                </button>
              </div>
            </div>
            <template v-if="taskBoardMatrix.length > 0">
              <template v-for="project in taskBoardMatrix" :key="project.id">
                <div class="kanban-project-row kanban-project-l1">
                  <button type="button" class="kanban-row-header" @click="toggleProjectRow(project.id)">
                    <span class="kanban-collapse-icon">{{ collapsedProjectRows.has(project.id) ? '▶' : '▼' }}</span>
                    <span class="kanban-project-name">{{ project.name }}</span>
                    <span class="kanban-project-count muted">{{ project.taskCount }} 项</span>
                  </button>
                </div>
                <div v-if="!collapsedProjectRows.has(project.id)" class="kanban-row-columns" :style="kanbanMatrixStyle">
                  <div class="kanban-row-spacer"></div>
                  <div
                    v-for="s in KANBAN_STATUSES"
                    :key="s"
                    class="kanban-cell"
                    :class="{ 'kanban-cell-drop-active': draggingTaskBoardItemId && !isKanbanStatusCollapsed(s), 'kanban-cell-collapsed': isKanbanStatusCollapsed(s) }"
                    @dragover.prevent="!isKanbanStatusCollapsed(s)"
                    @drop.prevent="!isKanbanStatusCollapsed(s) && handleTaskBoardDrop(s, $event)"
                  >
                    <button
                      v-if="isKanbanStatusCollapsed(s)"
                      type="button"
                      class="kanban-collapsed-summary"
                      :aria-label="`展开${taskBoardStatusLabelMap[s]}列，当前有${countTaskTreeNodes(project.columns[s])}项`"
                      :title="`展开${taskBoardStatusLabelMap[s]}列`"
                      @click="toggleKanbanStatusColumn(s)"
                    >
                      <span class="kanban-collapsed-count">{{ countTaskTreeNodes(project.columns[s]) }}</span>
                      <span class="kanban-collapsed-label">项</span>
                    </button>
                    <template v-else>
                      <div v-if="project.columns[s].length === 0" class="kanban-cell-empty">拖到这里</div>
                      <template v-for="item in project.columns[s]" :key="item.id">
                      <div
                        class="task-board-card"
                        :class="{ 'task-board-card-dragging': draggingTaskBoardItemId === item.id, 'task-board-card-highlighted': highlightedTaskBoardItemId === item.id }"
                        draggable="true"
                        @dragstart="handleTaskBoardDragStart(item, $event)"
                        @dragend="handleTaskBoardDragEnd"
                      >
                        <div class="task-board-card-top">
                          <div class="task-board-title-wrap">
                            <div class="task-board-name-row">
                              <button v-if="item.children.length" type="button" class="task-tree-toggle" @click.stop="toggleTaskNode(item)">{{ collapsedTaskNodes.has(item.id) ? '▶' : '▼' }}</button>
                              <span v-else class="task-tree-spacer"></span>
                              <span class="task-board-name">{{ item.name }}</span>
                            </div>
                            <div class="task-board-badges">
                              <span class="priority-badge" :class="`priority-P${getTaskPriority(item) - 1}`">{{ KANBAN_PRIORITY_LABELS[getTaskPriority(item)] }}</span>
                              <span v-if="item.children.length" class="task-child-count">{{ item.children.length }} 子任务</span>
                            </div>
                          </div>
                          <div class="task-board-card-actions">
                            <select class="priority-badge priority-select" :class="`priority-P${getTaskPriority(item) - 1}`" :value="getTaskPriority(item)" :disabled="quickUpdatingTaskBoardItemId === item.id" aria-label="调整任务优先级" @change.stop="updateTaskBoardPriority(item, $event)" @click.stop>
                              <option v-for="opt in taskBoardPriorityOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                            </select>
                            <button type="button" class="project-btn" @click.stop="openTaskBoardDetailModal(item)">详情</button>
                            <button type="button" class="project-btn project-btn-primary" :disabled="startingConversationFromTask" @click.stop="startConversationFromTask(item)">{{ startingConversationFromTask ? '...' : '会话' }}</button>
                            <button type="button" class="project-btn" @click.stop="openTaskBoardEditModal(item)">编辑</button>
                            <button type="button" class="card-delete-btn" :disabled="deletingTaskBoardItemId === item.id" :aria-label="`删除任务 ${item.name}`" @click.stop="deleteTaskBoardItem(item)"><span aria-hidden="true">×</span></button>
                          </div>
                        </div>
                        <div class="task-board-desc task-board-desc-compact">{{ item.description || '暂无描述' }}</div>
                        <div v-if="requiresTaskStatusReason(item.status) && item.status_reason" class="task-board-status-reason">
                          原因：{{ getTaskStatusReasonPreview(item) }}
                        </div>
                        <div class="task-board-meta task-board-meta-inline">
                          <span class="task-board-meta-label">{{ item.ai_platform }}</span>
                          <span class="task-board-meta-label muted">{{ formatSessionTime(item.updated_at) }}</span>
                        </div>
                        <div v-if="item.children.length && !collapsedTaskNodes.has(item.id)" class="task-tree-children">
                          <template v-for="child in item.children" :key="child.id">
                            <div class="task-board-card task-board-card-child" :class="{ 'task-board-card-highlighted': highlightedTaskBoardItemId === child.id }" draggable="true" @dragstart="handleTaskBoardDragStart(child, $event)" @dragend="handleTaskBoardDragEnd">
                              <div class="task-board-card-top">
                                <div class="task-board-title-wrap">
                                  <div class="task-board-name-row">
                                    <button v-if="child.children.length" type="button" class="task-tree-toggle" @click.stop="toggleTaskNode(child)">{{ collapsedTaskNodes.has(child.id) ? '▶' : '▼' }}</button>
                                    <span v-else class="task-tree-spacer"></span>
                                    <span class="task-board-name">{{ child.name }}</span>
                                  </div>
                                  <div class="task-board-badges">
                                    <span class="priority-badge" :class="`priority-P${getTaskPriority(child) - 1}`">{{ KANBAN_PRIORITY_LABELS[getTaskPriority(child)] }}</span>
                                    <span v-if="child.children.length" class="task-child-count">{{ child.children.length }} 子任务</span>
                                  </div>
                                </div>
                                <div class="task-board-card-actions"><button type="button" class="project-btn" @click.stop="openTaskBoardDetailModal(child)">详情</button><button type="button" class="project-btn" @click.stop="openTaskBoardEditModal(child)">编辑</button></div>
                              </div>
                              <div class="task-board-desc task-board-desc-compact">{{ child.description || '暂无描述' }}</div>
                              <div v-if="requiresTaskStatusReason(child.status) && child.status_reason" class="task-board-status-reason">
                                原因：{{ getTaskStatusReasonPreview(child) }}
                              </div>
                              <div v-if="child.children.length && !collapsedTaskNodes.has(child.id)" class="task-tree-children">
                                <div v-for="grandchild in child.children" :key="grandchild.id" class="task-board-card task-board-card-child task-board-card-grandchild" :class="{ 'task-board-card-highlighted': highlightedTaskBoardItemId === grandchild.id }">
                                  <div class="task-board-card-top"><div class="task-board-title-wrap"><div class="task-board-name-row"><span class="task-tree-spacer"></span><span class="task-board-name">{{ grandchild.name }}</span></div><div class="task-board-badges"><span class="priority-badge" :class="`priority-P${getTaskPriority(grandchild) - 1}`">{{ KANBAN_PRIORITY_LABELS[getTaskPriority(grandchild)] }}</span></div></div><div class="task-board-card-actions"><button type="button" class="project-btn" @click.stop="openTaskBoardDetailModal(grandchild)">详情</button><button type="button" class="project-btn" @click.stop="openTaskBoardEditModal(grandchild)">编辑</button></div></div>
                                  <div class="task-board-desc task-board-desc-compact">{{ grandchild.description || '暂无描述' }}</div>
                                  <div v-if="requiresTaskStatusReason(grandchild.status) && grandchild.status_reason" class="task-board-status-reason">
                                    原因：{{ getTaskStatusReasonPreview(grandchild) }}
                                  </div>
                                </div>
                              </div>
                            </div>
                          </template>
                        </div>
                      </div>
                      </template>
                    </template>
                  </div>
                </div>
              </template>
            </template>
            <div v-else class="project-empty">暂无任务，点击"新建任务"开始。</div>
          </div>
        </article>
      </section>

      <section v-else-if="activePage === 'model-config'" class="main-grid config-grid">
        <article class="panel state-panel config-panel">
          <h2>模型与 AI 配置</h2>

          <div class="state-group">
            <div class="state-group-title">模型</div>
            <div class="kv">
              <span class="muted">selected_model</span>
              <button type="button" class="state-picker-btn" @click="openModelModal">
                {{ selectedModel || '-' }}
              </button>
            </div>
            <div class="kv">
              <span class="muted">provider</span>
              <span class="state-value">{{ runtimeSummary.selectedModelProvider }}</span>
            </div>
          </div>

          <div class="state-group">
            <div class="state-group-title">技能</div>
            <div class="kv">
              <span class="muted">selected_skills</span>
              <button type="button" class="state-picker-btn" @click="openSkillModal">{{ selectedSkillsCountText }}</button>
            </div>
          </div>

          <div class="state-group">
            <div class="state-group-title">MCP</div>
            <div class="kv">
              <span class="muted">selected_mcp_servers</span>
              <button type="button" class="state-picker-btn" @click="openMcpModal">{{ selectedMcpCountText }}</button>
            </div>
          </div>
        </article>
      </section>

      <section v-else-if="activePage === 'system-config'" class="main-grid config-grid">
        <article class="panel state-panel config-panel config-panel-system">
          <div class="config-panel-head">
            <h2>系统配置</h2>
            <p class="config-panel-subtitle">集中管理平台级连接能力，所有配置即时生效并用于项目仓库操作。</p>
          </div>

          <div class="state-group config-card system-config-card">
            <div class="state-group-title">GitHub 集成</div>
            <div class="system-config-layout">
              <div class="system-config-main">
                <label class="create-field system-config-field">
                  <span class="create-field-label">GitHub Token</span>
                  <input
                    v-model="githubTokenDraft"
                    type="password"
                    class="picker-search-input system-token-input"
                    :disabled="githubTokenSaving"
                    placeholder="输入 GITHUB_TOKEN"
                  />
                </label>

                <p class="system-config-hint">建议使用具备 repo 权限的 Personal Access Token，用于仓库读取与创建。</p>
              </div>

              <aside class="system-config-side">
                <div class="system-status-card" :class="{ 'system-status-card-ready': githubTokenConfigured }">
                  <span class="system-status-label">当前状态</span>
                  <span class="system-status-value">{{ githubTokenConfigured ? '已配置' : '未配置' }}</span>
                </div>

                <div class="picker-actions system-config-actions">
                  <button
                    type="button"
                    class="picker-btn system-save-btn"
                    :disabled="githubTokenSaving || !githubTokenDraft.trim()"
                    @click="saveGithubToken"
                  >
                    {{ githubTokenSaving ? '保存中...' : '保存 Token' }}
                  </button>
                </div>
              </aside>
            </div>
          </div>
        </article>
      </section>

      <section v-else-if="activePage === 'dispatch-history'" class="main-grid dispatch-history-grid">
        <article class="panel dispatch-history-panel">
          <div class="dispatch-history-header">
            <h2>调度任务历史</h2>
            <div class="dispatch-history-controls">
              <select v-model="dispatchHistoryStatusFilter" class="dispatch-filter-select" @change="refreshDispatchHistory">
                <option value="">全部状态</option>
                <option value="completed">已完成</option>
                <option value="failed">失败</option>
                <option value="cancelled">已取消</option>
                <option value="running">运行中</option>
                <option value="awaiting_input">等待输入</option>
                <option value="paused">已暂停</option>
              </select>
              <button type="button" class="dispatch-refresh-btn" @click="refreshDispatchHistory" :disabled="dispatchHistoryLoading">刷新</button>
            </div>
          </div>

          <!-- Stats -->
          <div class="dispatch-stats-bar">
            <span class="dispatch-stat">总计: {{ dispatchStats.total }}</span>
            <span class="dispatch-stat dispatch-stat-success">完成: {{ dispatchStats.completed }}</span>
            <span class="dispatch-stat dispatch-stat-error">失败: {{ dispatchStats.failed }}</span>
            <span class="dispatch-stat dispatch-stat-warn">运行: {{ dispatchStats.running + dispatchStats.queued }}</span>
          </div>

          <!-- Task list -->
          <div v-if="dispatchHistoryLoading" class="dispatch-loading">加载中...</div>
          <div v-else-if="dispatchHistoryError" class="dispatch-error">{{ dispatchHistoryError }}</div>
          <div v-else-if="filteredDispatchTasks.length === 0" class="dispatch-empty">暂无调度任务</div>
          <ul v-else class="dispatch-task-list">
            <li v-for="task in filteredDispatchTasks" :key="task.id" class="dispatch-task-item" @click="viewDispatchTaskDetail(task)">
              <div class="dispatch-task-row">
                <span class="dispatch-task-platform">{{ task.ai_platform }}</span>
                <span class="dispatch-task-status" :class="'dispatch-status-' + task.status">{{ dispatchStatusLabelMap[task.status] || task.status }}</span>
              </div>
              <div class="dispatch-task-prompt">{{ (task.initial_prompt || '').slice(0, 80) }}{{ (task.initial_prompt || '').length > 80 ? '...' : '' }}</div>
              <div class="dispatch-task-meta">
                <span>{{ formatTime(task.created_at) }}</span>
                <span v-if="task.error_message" class="dispatch-task-error-hint">错误</span>
              </div>
            </li>
          </ul>

          <!-- Task detail modal -->
          <div v-if="dispatchDetailTask" class="dispatch-detail-overlay" @click.self="dispatchDetailTask = null">
            <div class="dispatch-detail-panel panel scrollbar-themed">
              <div class="dispatch-detail-header">
                <h3>调度任务详情</h3>
                <button type="button" class="picker-close-btn" @click="dispatchDetailTask = null" aria-label="关闭"><span class="close-icon" aria-hidden="true">✕</span></button>
              </div>
              <div class="dispatch-detail-body">
                <div class="dispatch-detail-row"><strong>ID:</strong> {{ dispatchDetailTask.id }}</div>
                <div class="dispatch-detail-row"><strong>平台:</strong> {{ dispatchDetailTask.ai_platform }}</div>
                <div class="dispatch-detail-row"><strong>状态:</strong> <span :class="'dispatch-status-' + dispatchDetailTask.status">{{ dispatchStatusLabelMap[dispatchDetailTask.status] || dispatchDetailTask.status }}</span></div>
                <div class="dispatch-detail-row"><strong>创建:</strong> {{ formatTime(dispatchDetailTask.created_at) }}</div>
                <div v-if="dispatchDetailTask.error_message" class="dispatch-detail-row dispatch-detail-error"><strong>错误:</strong> {{ dispatchDetailTask.error_message }}</div>
                <div class="dispatch-detail-row"><strong>初始提示:</strong></div>
                <pre class="dispatch-detail-pre scrollbar-themed">{{ dispatchDetailTask.initial_prompt }}</pre>
                <div v-if="dispatchDetailEvents.length > 0" class="dispatch-detail-events">
                  <h4>事件流 ({{ dispatchDetailEvents.length }})</h4>
                  <div v-for="(evt, idx) in dispatchDetailEvents" :key="idx" class="dispatch-event-item">
                    <span class="dispatch-event-type">{{ evt.event_type }}</span>
                    <span class="dispatch-event-time">{{ formatTime(evt.created_at) }}</span>
                    <pre v-if="evt.payload" class="dispatch-event-payload">{{ JSON.stringify(evt.payload, null, 2).slice(0, 300) }}</pre>
                  </div>
                </div>
              </div>
              <div class="dispatch-detail-actions">
                <button v-if="dispatchDetailTask.status === 'awaiting_input' || dispatchDetailTask.status === 'paused'" type="button" class="picker-btn" @click="resumeFromHistory(dispatchDetailTask)">恢复任务</button>
                <button v-if="['queued','running','awaiting_input'].includes(dispatchDetailTask.status)" type="button" class="picker-btn picker-btn-danger" @click="cancelFromHistory(dispatchDetailTask)">取消任务</button>
              </div>
            </div>
          </div>
        </article>
      </section>

      <section v-else-if="activePage === 'skills-catalog'" class="main-grid skills-catalog-grid">
        <article class="panel skills-catalog-panel">
          <div class="skills-catalog-header">
            <h2>Skills 库</h2>
            <div class="skills-catalog-controls">
              <div class="sg-view-switch">
                <button type="button" class="picker-btn" :class="{ active: skillsCatalogView === 'list' }" @click="skillsCatalogView = 'list'">列表</button>
                <button type="button" class="picker-btn" :class="{ active: skillsCatalogView === 'graph' }" @click="skillsCatalogView = 'graph'">图谱</button>
              </div>
              <template v-if="skillsCatalogView === 'list'">
                <select v-model="skillsCatalogProviderFilter" class="dispatch-filter-select">
                  <option v-for="p in skillsCatalogProviders" :key="p.id" :value="p.id">{{ p.label }}</option>
                </select>
                <select v-model="skillsCatalogCategoryFilter" class="dispatch-filter-select">
                  <option value="全部">全部分类</option>
                  <option v-for="cat in skillsCatalogCategories" :key="cat" :value="cat">{{ cat }}</option>
                </select>
                <select v-model="skillsCatalogTypeFilter" class="dispatch-filter-select">
                  <option value="全部">全部类型</option>
                  <option value="builtin">内置</option>
                  <option value="custom">自建</option>
                  <option value="third-party">第三方</option>
                </select>
                <input v-model="skillsCatalogSearch" class="picker-search-input skills-catalog-search" placeholder="搜索 skill 名称或描述" />
                <button type="button" class="picker-btn ghost" @click="loadSkillsCatalog" :disabled="skillsCatalogLoading">
                  {{ skillsCatalogLoading ? '加载中...' : '刷新' }}
                </button>
              </template>
            </div>
          </div>

          <!-- Graph view -->
          <SkillGraph v-if="skillsCatalogView === 'graph'" :api-base="apiBase" class="sg-embedded" />

          <!-- List view -->
          <div v-if="skillsCatalogView === 'list'">
          <div v-if="skillsCatalogError" class="skills-catalog-error muted">{{ skillsCatalogError }}</div>
          <div v-else-if="skillsCatalogLoading" class="skills-catalog-loading muted">加载中...</div>
          <template v-else>
            <div class="skills-catalog-meta muted">共 {{ filteredCatalogSkills.length }} 个 skills，第 {{ skillsCatalogPage }}/{{ skillsCatalogTotalPages }} 页</div>
            <div class="skills-catalog-list scrollbar-themed">
              <div
                v-for="skill in pagedCatalogSkills"
                :key="skill.provider_id + '/' + skill.name"
                class="skill-card"
                @click="openSkillDetail(skill)"
              >
                <div class="skill-card-badges">
                  <span :class="['skill-type-badge', 'skill-type-' + (skill.skill_type || 'builtin')]">
                    {{ skill.skill_type === 'custom' ? '自建' : skill.skill_type === 'third-party' ? '第三方' : '内置' }}
                  </span>
                  <span class="skill-category-badge">{{ skill.category }}</span>
                </div>
                <div class="skill-card-name">{{ skill.name }}</div>
                <div class="skill-card-desc">{{ skill.description || '暂无描述' }}</div>
              </div>
              <div v-if="filteredCatalogSkills.length === 0" class="muted">无匹配 skills</div>
            </div>
            <div v-if="skillsCatalogTotalPages > 1" class="skills-catalog-pagination">
              <button class="picker-btn ghost" :disabled="skillsCatalogPage <= 1" @click="skillsCatalogPage--">上一页</button>
              <span class="muted">{{ skillsCatalogPage }} / {{ skillsCatalogTotalPages }}</span>
              <button class="picker-btn ghost" :disabled="skillsCatalogPage >= skillsCatalogTotalPages" @click="skillsCatalogPage++">下一页</button>
            </div>
          </template>
          </div><!-- end list view -->
        </article>
      </section>
    </section>

    <!-- Skill Detail Modal -->
    <div v-if="skillDetailTarget" class="skill-detail-overlay" @click.self="closeSkillDetail">
      <div class="skill-detail-modal scrollbar-themed">
        <button class="skill-detail-close" @click="closeSkillDetail" aria-label="关闭">✕</button>
        <div class="skill-detail-title">{{ skillDetailTarget.name }}</div>
        <div class="skill-detail-badges">
          <span :class="['skill-type-badge', 'skill-type-' + (skillDetailTarget.skill_type || 'builtin')]">
            {{ skillDetailTarget.skill_type === 'custom' ? '自建' : skillDetailTarget.skill_type === 'third-party' ? '第三方' : '内置' }}
          </span>
          <span class="skill-category-badge">{{ skillDetailTarget.category }}</span>
        </div>
        <div class="skill-detail-desc">{{ skillDetailTarget.description || '暂无描述' }}</div>
        <div v-if="skillDetailTarget.file_path || skillDetailTarget._api_path" class="skill-detail-path">📄 当前读取：{{ skillDetailTarget._api_path || skillDetailTarget.file_path }}</div>
        <div v-if="skillDetailContentLoading" class="muted skill-detail-content-loading">⏳ 加载内容中...</div>
        <div v-else-if="skillDetailError" class="skill-detail-content-error">❌ {{ skillDetailError }}</div>
        <pre v-else-if="skillDetailContent" class="skill-detail-content scrollbar-themed">{{ skillDetailContent }}</pre>
        <div v-else class="muted skill-detail-content-empty">暂无详细内容</div>
      </div>
    </div>

    <div v-if="isCreateConversationModalOpen" class="picker-modal-overlay" @click.self="closeCreateConversationModal">
      <div class="picker-modal panel create-conversation-modal">
        <div class="picker-modal-header">
          <h3>新建对话</h3>
          <button type="button" class="picker-close-btn" :disabled="creatingConversation" @click="closeCreateConversationModal" aria-label="关闭"><span class="close-icon" aria-hidden="true">✕</span></button>
        </div>

        <div class="create-conversation-form">
          <label class="create-field">
            <span class="create-field-label">平台</span>
            <select
              v-model="createConversationPlatform"
              class="picker-provider-select"
              :disabled="creatingConversation"
            >
              <option v-for="name in platformOptions" :key="name" :value="name">{{ name }}</option>
            </select>
          </label>

          <label class="create-field">
            <span class="create-field-label">初始消息</span>
            <textarea
              v-model="createConversationInitialMessage"
              class="create-initial-message"
              :disabled="creatingConversation"
              placeholder="请输入你想发送的第一条消息"
              @keydown="handleCreateInitialMessageKeydown"
            ></textarea>
          </label>
        </div>

        <div class="picker-actions">
          <button type="button" class="picker-btn ghost" :disabled="creatingConversation" @click="closeCreateConversationModal">取消</button>
          <button
            type="button"
            class="picker-btn"
            :disabled="creatingConversation || !createConversationInitialMessage.trim()"
            @click="submitCreateConversation"
          >
            {{ creatingConversation ? '创建中...' : '创建并发送' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="isProjectCreateModalOpen" class="picker-modal-overlay" @click.self="closeProjectCreateModal">
      <div class="picker-modal panel create-conversation-modal">
        <div class="picker-modal-header">
          <h3>新建项目</h3>
          <button type="button" class="picker-close-btn" :disabled="creatingProject" @click="closeProjectCreateModal" aria-label="关闭"><span class="close-icon" aria-hidden="true">✕</span></button>
        </div>

        <div class="create-conversation-form">
          <label class="create-field">
            <span class="create-field-label">项目名称</span>
            <input v-model="createProjectForm.name" class="picker-search-input" :disabled="creatingProject || creatingGithubRepo" placeholder="请输入项目名称，如 shujietai-demo" />
          </label>

          <label class="create-field">
            <span class="create-field-label">项目简介</span>
            <textarea
              v-model="createProjectForm.description"
              class="create-initial-message"
              :disabled="creatingProject || creatingGithubRepo"
              placeholder="请输入项目简介"
            ></textarea>
          </label>

          <div class="project-repo-mode-card">
            <label class="create-field-checkbox">
              <input type="checkbox" v-model="createRepoEnabled" :disabled="creatingProject || creatingGithubRepo" />
              <span>同时新建 GitHub 仓库（可选）</span>
            </label>

            <template v-if="!createRepoEnabled">
              <label class="create-field">
                <span class="create-field-label">已有仓库（必选）</span>
                <select
                  v-model="createProjectForm.repository_url"
                  class="picker-provider-select"
                  :disabled="creatingProject || creatingGithubRepo"
                  @change="handleRepositoryChange"
                >
                  <option value="" disabled>请选择仓库</option>
                  <option v-for="repo in getRepoChoices()" :key="repo.url" :value="repo.url">{{ repo.full_name }} · {{ repo.description || '无描述' }}</option>
                </select>
              </label>
            </template>

            <template v-else>
              <label class="create-field-checkbox">
                <input type="checkbox" v-model="createProjectForm.private" :disabled="creatingProject || creatingGithubRepo" />
                <span>创建为私有仓库</span>
              </label>
              <div class="project-repo-mode-hint">将使用“项目名称”作为仓库名，“项目简介”作为仓库描述。</div>
            </template>
          </div>
        </div>

        <div class="picker-actions">
          <button type="button" class="picker-btn ghost" :disabled="creatingProject || creatingGithubRepo" @click="closeProjectCreateModal">取消</button>
          <button
            v-if="!createRepoEnabled"
            type="button"
            class="picker-btn"
            :disabled="creatingProject || creatingGithubRepo || !createProjectForm.name.trim() || !createProjectForm.repository_url.trim()"
            @click="submitCreateProject"
          >
            {{ creatingProject ? '创建中...' : '创建项目' }}
          </button>
          <button
            v-else
            type="button"
            class="picker-btn"
            :disabled="creatingProject || creatingGithubRepo || !createProjectForm.name.trim()"
            @click="createGithubRepo"
          >
            {{ creatingGithubRepo ? '创建仓库并建项目中...' : '新建仓库并创建项目' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="isProjectEditModalOpen" class="picker-modal-overlay" @click.self="closeProjectEditModal">
      <div class="picker-modal panel create-conversation-modal">
        <div class="picker-modal-header">
          <h3>编辑项目</h3>
          <button type="button" class="picker-close-btn" :disabled="updatingProject" @click="closeProjectEditModal" aria-label="关闭"><span class="close-icon" aria-hidden="true">✕</span></button>
        </div>

        <div class="create-conversation-form">
          <label class="create-field">
            <span class="create-field-label">项目名称</span>
            <input v-model="editProjectForm.name" class="picker-search-input" :disabled="updatingProject" placeholder="请输入项目名称" />
          </label>

          <label class="create-field">
            <span class="create-field-label">项目简介</span>
            <textarea
              v-model="editProjectForm.description"
              class="create-initial-message"
              :disabled="updatingProject"
              placeholder="请输入项目简介"
            ></textarea>
          </label>
        </div>

        <div class="picker-actions">
          <button type="button" class="picker-btn ghost" :disabled="updatingProject" @click="closeProjectEditModal">取消</button>
          <button type="button" class="picker-btn" :disabled="updatingProject || !editProjectForm.name.trim()" @click="submitEditProject">
            {{ updatingProject ? '保存中...' : '保存修改' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="isModelModalOpen" class="picker-modal-overlay" @click.self="closeModelModal">
      <div class="picker-modal panel">
        <div class="picker-modal-header">
          <h3>选择模型</h3>
          <button type="button" class="picker-close-btn" @click="closeModelModal" aria-label="关闭"><span class="close-icon" aria-hidden="true">✕</span></button>
        </div>
        <div class="picker-search-row picker-provider-row">
          <select v-model="modelProviderDraft" class="picker-provider-select">
            <option v-for="provider in modelProviderOptions" :key="provider" :value="provider">{{ provider }}</option>
          </select>
          <input v-model="modelSearchDraft" class="picker-search-input" placeholder="搜索 model 名称" />
        </div>
        <div class="picker-list">
          <label
            v-for="item in filteredModelItems"
            :key="item.name"
            class="picker-item"
          >
            <input
              type="radio"
              name="model-selection"
              :checked="tempSelectedModel === item.name"
              @change="selectTempModel(item.name)"
            />
            <div class="picker-item-text">
              <div class="picker-item-title">{{ item.name }}</div>
              <div class="picker-item-desc">provider: {{ item.provider || '-' }}</div>
            </div>
          </label>
          <div v-if="filteredModelItems.length === 0" class="muted">无匹配项</div>
        </div>
        <div class="picker-actions">
          <button type="button" class="picker-btn ghost" @click="closeModelModal">取消</button>
          <button type="button" class="picker-btn" @click="applyModelModalSelection">确认</button>
        </div>
      </div>
    </div>

    <div v-if="isSkillModalOpen" class="picker-modal-overlay" @click.self="closeSkillModal">
      <div class="picker-modal panel">
        <div class="picker-modal-header">
          <h3>选择 Skills</h3>
          <button type="button" class="picker-close-btn" @click="closeSkillModal" aria-label="关闭"><span class="close-icon" aria-hidden="true">✕</span></button>
        </div>
        <div class="picker-search-row">
          <input v-model="skillSearchDraft" class="picker-search-input" placeholder="搜索 skill 名称或描述" />
        </div>
        <div class="picker-list">
          <label
            v-for="item in filteredSkillItems"
            :key="item.name"
            class="picker-item"
          >
            <input
              type="checkbox"
              :checked="isTempSkillChecked(item.name)"
              @change="toggleTempSkill(item.name)"
            />
            <div class="picker-item-text">
              <div class="picker-item-title">{{ item.name }}</div>
              <div class="picker-item-desc">{{ item.description || '-' }}</div>
            </div>
          </label>
          <div v-if="filteredSkillItems.length === 0" class="muted">无匹配项</div>
        </div>
        <div class="picker-actions">
          <button type="button" class="picker-btn ghost" @click="closeSkillModal">取消</button>
          <button type="button" class="picker-btn" @click="applySkillModalSelection">确认</button>
        </div>
      </div>
    </div>

    <div v-if="isMcpModalOpen" class="picker-modal-overlay" @click.self="closeMcpModal">
      <div class="picker-modal panel">
        <div class="picker-modal-header">
          <h3>选择 MCP Servers</h3>
          <button type="button" class="picker-close-btn" @click="closeMcpModal" aria-label="关闭"><span class="close-icon" aria-hidden="true">✕</span></button>
        </div>
        <div class="picker-search-row">
          <input v-model="mcpSearchDraft" class="picker-search-input" placeholder="搜索 MCP 名称" />
        </div>
        <div class="picker-list">
          <label
            v-for="name in filteredMcpItems"
            :key="name"
            class="picker-item"
          >
            <input
              type="checkbox"
              :checked="isTempMcpChecked(name)"
              @change="toggleTempMcp(name)"
            />
            <div class="picker-item-text">
              <div class="picker-item-title">{{ name }}</div>
            </div>
          </label>
          <div v-if="filteredMcpItems.length === 0" class="muted">无匹配项</div>
        </div>
        <div class="picker-actions">
          <button type="button" class="picker-btn ghost" @click="closeMcpModal">取消</button>
          <button type="button" class="picker-btn" @click="applyMcpModalSelection">确认</button>
        </div>
      </div>
    </div>

    <div v-if="isTaskBoardCreateModalOpen" class="picker-modal-overlay" @click.self="closeTaskBoardCreateModal">
      <div class="picker-modal panel create-conversation-modal">
        <div class="picker-modal-header">
          <h3>新建任务</h3>
          <button type="button" class="picker-close-btn" :disabled="creatingTaskBoardItem" @click="closeTaskBoardCreateModal" aria-label="关闭"><span class="close-icon" aria-hidden="true">✕</span></button>
        </div>

        <div class="create-conversation-form">
          <label class="create-field">
            <span class="create-field-label">任务名称</span>
            <input v-model="taskBoardCreateForm.name" class="picker-search-input" :disabled="creatingTaskBoardItem" placeholder="请输入任务名称" />
          </label>

          <label class="create-field">
            <span class="create-field-label">任务描述</span>
            <textarea v-model="taskBoardCreateForm.description" class="create-initial-message" :disabled="creatingTaskBoardItem" placeholder="请输入任务描述"></textarea>
          </label>

          <label class="create-field">
            <span class="create-field-label">AI 平台</span>
            <input v-model="taskBoardCreateForm.ai_platform" class="picker-search-input" :disabled="creatingTaskBoardItem" placeholder="hermes" />
          </label>

          <label class="create-field">
            <span class="create-field-label">所属项目</span>
            <select v-model="taskBoardCreateForm.project_id" class="picker-provider-select" :disabled="creatingTaskBoardItem">
              <option value="">不关联项目</option>
              <option v-for="proj in projects" :key="proj.id" :value="proj.id">{{ proj.name }}（{{ proj.code }}）</option>
            </select>
          </label>

          <label class="create-field">
            <span class="create-field-label">上游依赖</span>
            <select v-model="taskBoardCreateForm.upstream_task_id" class="picker-provider-select" :disabled="creatingTaskBoardItem">
              <option value="">无上游依赖</option>
              <option v-for="dep in taskBoardDependencyOptions" :key="dep.value" :value="dep.value">{{ dep.label }}</option>
            </select>
          </label>

          <label class="create-field">
            <span class="create-field-label">父任务</span>
            <select v-model="taskBoardCreateForm.parent_task_id" class="picker-provider-select" :disabled="creatingTaskBoardItem">
              <option value="">无父任务</option>
              <option v-for="dep in taskBoardDependencyOptions" :key="dep.value" :value="dep.value">{{ dep.label }}</option>
            </select>
          </label>

          <label class="create-field">
            <span class="create-field-label">状态</span>
            <select v-model="taskBoardCreateForm.status" class="picker-provider-select" :disabled="creatingTaskBoardItem">
              <option v-for="opt in taskBoardStatusOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>
          </label>
          <label v-if="requiresTaskStatusReason(taskBoardCreateForm.status)" class="create-field">
            <span class="create-field-label">状态原因</span>
            <textarea v-model="taskBoardCreateForm.status_reason" class="create-initial-message" :disabled="creatingTaskBoardItem" :placeholder="`请输入${taskBoardStatusLabelMap[taskBoardCreateForm.status] || taskBoardCreateForm.status}原因`"></textarea>
          </label>
          <label class="create-field-row">
            <span class="create-field-label">优先级</span>
            <select v-model.number="taskBoardCreateForm.priority" class="picker-provider-select" :disabled="creatingTaskBoardItem">
              <option v-for="opt in taskBoardPriorityOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>
          </label>
        </div>

        <div class="picker-actions">
          <button type="button" class="picker-btn ghost" :disabled="creatingTaskBoardItem" @click="closeTaskBoardCreateModal">取消</button>
          <button type="button" class="picker-btn" :disabled="creatingTaskBoardItem || !taskBoardCreateForm.name.trim()" @click="submitCreateTaskBoardItem">
            {{ creatingTaskBoardItem ? '创建中...' : '创建任务' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="taskBoardDetailItem" class="picker-modal-overlay" @click.self="closeTaskBoardDetailModal">
      <div class="picker-modal panel task-detail-modal">
        <div class="picker-modal-header task-detail-header">
          <div>
            <h3>{{ taskBoardDetailItem.name }}</h3>
            <div class="task-detail-subtitle">
              <span :class="['task-board-status-pill', taskBoardStatusClass(taskBoardDetailItem.status)]">{{ taskBoardStatusLabelMap[taskBoardDetailItem.status] || taskBoardDetailItem.status }}</span>
              <span :class="['priority-badge', `priority-P${taskBoardDetailItem.priority || 3}`]">{{ taskBoardPriorityLabelMap[taskBoardDetailItem.priority || 3] || 'P2' }}</span>
            </div>
          </div>
          <button type="button" class="picker-close-btn" @click="closeTaskBoardDetailModal" aria-label="关闭"><span class="close-icon" aria-hidden="true">✕</span></button>
        </div>

        <div class="task-detail-body scrollbar-themed">
          <section class="task-detail-section">
            <h4>任务描述</h4>
            <div v-if="taskBoardDetailItem.description" class="task-detail-markdown" v-html="renderMarkdown(taskBoardDetailItem.description)"></div>
            <div v-else class="muted">暂无描述</div>
          </section>
          <section v-if="requiresTaskStatusReason(taskBoardDetailItem.status) && taskBoardDetailItem.status_reason" class="task-detail-section">
            <h4>状态原因</h4>
            <div class="task-detail-reason">{{ taskBoardDetailItem.status_reason }}</div>
          </section>
          <section class="task-detail-grid">
            <div><span>项目</span><strong>{{ taskBoardDetailField(taskBoardDetailItem.project_name) }}</strong></div>
            <div><span>AI 平台</span><strong>{{ taskBoardDetailField(taskBoardDetailItem.ai_platform) }}</strong></div>
            <div><span>上游任务</span><strong>{{ taskBoardDetailField(taskBoardDetailItem.upstream_task_id) }}</strong></div>
            <div><span>父任务</span><strong>{{ taskBoardDetailField(taskBoardDetailItem.parent_task_id) }}</strong></div>
            <div><span>创建时间</span><strong>{{ formatSessionTime(taskBoardDetailItem.created_at) }}</strong></div>
            <div><span>更新时间</span><strong>{{ formatSessionTime(taskBoardDetailItem.updated_at) }}</strong></div>
          </section>
        </div>

        <div class="picker-actions">
          <button type="button" class="picker-btn ghost" @click="closeTaskBoardDetailModal">关闭</button>
          <button type="button" class="picker-btn" @click="openTaskBoardEditModal(taskBoardDetailItem)">编辑任务</button>
        </div>
      </div>
    </div>

    <div v-if="isTaskBoardEditModalOpen" class="picker-modal-overlay" @click.self="closeTaskBoardEditModal">
      <div class="picker-modal panel create-conversation-modal">
        <div class="picker-modal-header">
          <h3>编辑任务</h3>
          <button type="button" class="picker-close-btn" :disabled="updatingTaskBoardItem" @click="closeTaskBoardEditModal" aria-label="关闭"><span class="close-icon" aria-hidden="true">✕</span></button>
        </div>

        <div class="create-conversation-form">
          <label class="create-field">
            <span class="create-field-label">任务名称</span>
            <input v-model="taskBoardEditForm.name" class="picker-search-input" :disabled="updatingTaskBoardItem" placeholder="请输入任务名称" />
          </label>

          <label class="create-field">
            <span class="create-field-label">任务描述</span>
            <textarea v-model="taskBoardEditForm.description" class="create-initial-message task-description-editor" :disabled="updatingTaskBoardItem" placeholder="请输入任务描述（支持长段落/Markdown）"></textarea>
          </label>

          <label class="create-field">
            <span class="create-field-label">AI 平台</span>
            <input v-model="taskBoardEditForm.ai_platform" class="picker-search-input" :disabled="updatingTaskBoardItem" placeholder="hermes" />
          </label>

          <label class="create-field">
            <span class="create-field-label">所属项目</span>
            <select v-model="taskBoardEditForm.project_id" class="picker-provider-select" :disabled="updatingTaskBoardItem">
              <option value="">不关联项目</option>
              <option v-for="proj in projects" :key="proj.id" :value="proj.id">{{ proj.name }}（{{ proj.code }}）</option>
            </select>
          </label>

          <label class="create-field">
            <span class="create-field-label">上游依赖</span>
            <select v-model="taskBoardEditForm.upstream_task_id" class="picker-provider-select" :disabled="updatingTaskBoardItem">
              <option value="">无上游依赖</option>
              <option v-for="dep in taskBoardDependencyOptions" :key="dep.value" :value="dep.value">{{ dep.label }}</option>
            </select>
          </label>

          <label class="create-field">
            <span class="create-field-label">父任务</span>
            <select v-model="taskBoardEditForm.parent_task_id" class="picker-provider-select" :disabled="updatingTaskBoardItem">
              <option value="">无父任务</option>
              <option v-for="dep in taskBoardDependencyOptions" :key="dep.value" :value="dep.value">{{ dep.label }}</option>
            </select>
          </label>

          <label class="create-field">
            <span class="create-field-label">状态</span>
            <select v-model="taskBoardEditForm.status" class="picker-provider-select" :disabled="updatingTaskBoardItem">
              <option v-for="opt in taskBoardStatusOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>
          </label>
          <label v-if="requiresTaskStatusReason(taskBoardEditForm.status)" class="create-field">
            <span class="create-field-label">状态原因</span>
            <textarea v-model="taskBoardEditForm.status_reason" class="create-initial-message" :disabled="updatingTaskBoardItem" :placeholder="`请输入${taskBoardStatusLabelMap[taskBoardEditForm.status] || taskBoardEditForm.status}原因`"></textarea>
          </label>
          <label class="create-field-row">
            <span class="create-field-label">优先级</span>
            <select v-model.number="taskBoardEditForm.priority" class="picker-provider-select" :disabled="updatingTaskBoardItem">
              <option v-for="opt in taskBoardPriorityOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>
          </label>
        </div>

        <div class="picker-actions">
          <button type="button" class="picker-btn ghost" :disabled="updatingTaskBoardItem" @click="closeTaskBoardEditModal">取消</button>
          <button type="button" class="picker-btn" :disabled="updatingTaskBoardItem || !taskBoardEditForm.name.trim()" @click="submitEditTaskBoardItem">
            {{ updatingTaskBoardItem ? '保存中...' : '保存修改' }}
          </button>
        </div>
      </div>
    </div>

  </main>
</template>
