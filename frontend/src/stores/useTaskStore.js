import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { fetchJson, postJson, patchJson } from '../services/apiClient.js'
import {
  TASK_BOARD_STATUS_OPTIONS, TASK_BOARD_STATUS_LABEL_MAP,
  TASK_BOARD_PRIORITY_OPTIONS, TASK_BOARD_PRIORITY_LABEL_MAP,
  KANBAN_STATUSES, COLLAPSIBLE_KANBAN_STATUSES, KANBAN_PRIORITY_LABELS,
} from '../constants/appConstants.js'
import { useSessionStore } from './useSessionStore.js'

const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:18000'

export const useTaskStore = defineStore('task', () => {
  // --- Task Board ---
  const taskBoardItems = ref([])
  const taskBoardProjectFilter = ref('')
  const taskBoardKeyword = ref('')
  const taskBoardStatusFilter = ref('')
  const isTaskBoardCreateModalOpen = ref(false)
  const isTaskBoardEditModalOpen = ref(false)
  const creatingTaskBoardItem = ref(false)
  const updatingTaskBoardItem = ref(false)
  const quickUpdatingTaskBoardItemId = ref('')
  const draggingTaskBoardItemId = ref('')
  const editingTaskBoardItemId = ref('')
  const taskBoardDetailItem = ref(null)
  const highlightedTaskBoardItemId = ref('')
  const startingConversationFromTask = ref(false)

  const taskBoardCreateForm = ref({
    name: '', description: '', ai_platform: 'hermes', project_id: '',
    upstream_task_id: '', parent_task_id: '', status: 'draft', status_reason: '', priority: 3,
  })
  const taskBoardEditForm = ref({
    name: '', description: '', ai_platform: 'hermes', project_id: '',
    upstream_task_id: '', parent_task_id: '', status: 'draft', status_reason: '', priority: 3,
  })

  const collapsedProjectRows = ref(new Set())
  const collapsedTaskNodes = ref(new Set())
  const collapsedKanbanStatuses = ref(new Set(['completed']))

  // --- Task Archive ---
  const archivedTaskItems = ref([])
  const archiveProjectFilter = ref('')
  const archiveKeyword = ref('')
  const archiveStatusFilter = ref('')
  const archiveLoading = ref(false)
  const archivingTaskId = ref('')
  const unarchivingTaskId = ref('')
  const archiveDetailItem = ref(null)
  const isArchiveDetailOpen = ref(false)

  // --- Constants ---
  const taskBoardStatusOptions = TASK_BOARD_STATUS_OPTIONS
  const taskBoardStatusLabelMap = TASK_BOARD_STATUS_LABEL_MAP
  const taskBoardPriorityOptions = TASK_BOARD_PRIORITY_OPTIONS
  const taskBoardPriorityLabelMap = TASK_BOARD_PRIORITY_LABEL_MAP
  const KANBAN_LABEL_TRACK = 'minmax(clamp(8rem, 13vw, 11rem), 0.52fr)'
  const KANBAN_EXPANDED_TRACK = 'minmax(clamp(10rem, 12vw, 14rem), 1fr)'
  const KANBAN_COLLAPSED_TRACK = 'minmax(4.4rem, 0.22fr)'
  const KANBAN_LABEL_MIN_REM = 8
  const KANBAN_EXPANDED_MIN_REM = 10
  const KANBAN_COLLAPSED_MIN_REM = 4.4

  // --- Getters ---
  const filteredTaskBoardItems = computed(() => {
    const keyword = taskBoardKeyword.value.trim().toLowerCase()
    const projectId = taskBoardProjectFilter.value.trim()
    const statusFilter = taskBoardStatusFilter.value.trim()
    return taskBoardItems.value.filter(item => {
      if (projectId && item.project_id !== projectId) return false
      if (statusFilter && item.status !== statusFilter) return false
      if (!keyword) return true
      const text = `${item.name} ${item.description} ${item.ai_platform} ${item.project_name || ''}`.toLowerCase()
      return text.includes(keyword)
    })
  })

  const taskBoardProjectOptions = computed(() => {
    const ss = useSessionStore()
    const projects = ss?.projects ?? []
    return [{ value: '', label: '全部项目' }, ...projects.map(p => ({ value: p.id, label: `${p.name}（${p.code}）` }))]
  })

  const taskBoardDependencyOptions = computed(() =>
    taskBoardItems.value.map(item => ({ value: item.id, label: item.name })))

  const taskBoardStatusFilterOptions = computed(() => [
    { value: '', label: '全部状态' }, ...taskBoardStatusOptions,
  ])

  const taskBoardMatrix = computed(() => {
    const projectMap = new Map()
    for (const item of filteredTaskBoardItems.value) {
      const pkey = item.project_id || '__none__'
      const pname = item.project_name || '未关联项目'
      if (!projectMap.has(pkey)) {
        projectMap.set(pkey, { id: pkey, name: pname, columns: Object.fromEntries(KANBAN_STATUSES.map(s => [s, []])) })
      }
      const proj = projectMap.get(pkey)
      const status = KANBAN_STATUSES.includes(item.status) ? item.status : 'draft'
      proj.columns[status].push(item)
    }
    return [...projectMap.values()]
      .map(proj => {
        const columns = Object.fromEntries(KANBAN_STATUSES.map(s => [s, buildTaskTree(proj.columns[s])]))
        return { ...proj, columns, taskCount: KANBAN_STATUSES.reduce((s, st) => s + countTaskTreeNodes(columns[st]), 0) }
      })
      .sort((a, b) => { if (a.id === '__none__') return 1; if (b.id === '__none__') return -1; return a.name.localeCompare(b.name) })
  })

  const kanbanGridTemplate = computed(() =>
    [KANBAN_LABEL_TRACK, ...KANBAN_STATUSES.map(s => collapsedKanbanStatuses.value.has(s) ? KANBAN_COLLAPSED_TRACK : KANBAN_EXPANDED_TRACK)].join(' '))

  const kanbanMatrixMinWidth = computed(() => {
    const sm = KANBAN_STATUSES.reduce((s, st) => s + (collapsedKanbanStatuses.value.has(st) ? KANBAN_COLLAPSED_MIN_REM : KANBAN_EXPANDED_MIN_REM), 0)
    return `${KANBAN_LABEL_MIN_REM + sm}rem`
  })

  const kanbanMatrixStyle = computed(() => ({ '--kanban-grid-template': kanbanGridTemplate.value, '--kanban-matrix-min-width': kanbanMatrixMinWidth.value }))

  // --- Helpers ---
  function buildTaskTree(items) {
    if (!Array.isArray(items) || items.length === 0) return []
    const map = new Map(items.map(i => [i.id, { ...i, children: [] }]))
    const roots = []
    for (const node of map.values()) {
      if (node.parent_task_id && map.has(node.parent_task_id)) {
        map.get(node.parent_task_id).children.push(node)
      } else { roots.push(node) }
    }
    return roots
  }
  function makeTaskNodeKey(item) { return item?.id || '' }
  function countTaskTreeNodes(nodes) {
    let c = 0
    const walk = ns => { for (const n of ns) { c++; walk(n.children) } }
    walk(nodes)
    return c
  }

  function findTaskBoardItemById(id) {
    if (!id) return null
    return taskBoardItems.value.find(i => i.id === id) || null
  }

  function isKanbanStatusCollapsible(s) { return COLLAPSIBLE_KANBAN_STATUSES.includes(s) }
  function isKanbanStatusCollapsed(s) { return collapsedKanbanStatuses.value.has(s) }
  function toggleKanbanStatusColumn(s) {
    if (!isKanbanStatusCollapsible(s)) return
    const n = new Set(collapsedKanbanStatuses.value)
    n.has(s) ? n.delete(s) : n.add(s)
    collapsedKanbanStatuses.value = n
  }

  function toggleProjectRow(id) {
    const s = new Set(collapsedProjectRows.value)
    s.has(id) ? s.delete(id) : s.add(id)
    collapsedProjectRows.value = s
  }

  function toggleTaskNode(item) {
    const k = makeTaskNodeKey(item)
    if (!k) return
    const s = new Set(collapsedTaskNodes.value)
    s.has(k) ? s.delete(k) : s.add(k)
    collapsedTaskNodes.value = s
  }

  function getTaskPriority(item) { return item?.priority ?? 3 }
  function taskBoardStatusClass(s) { return `task-status-${s || 'draft'}` }
  function taskBoardDetailField(v) { const n = String(v || '').trim(); return n || '-' }
  function requiresTaskStatusReason(s) { return s === 'blocked' || s === 'cancelled' }
  function normalizeTaskStatusReason(status, reason) { return requiresTaskStatusReason(status) ? String(reason || '').trim() : '' }
  function getTaskStatusReasonPreview(item, maxLen = 96) {
    const r = String(item?.status_reason || '').trim()
    if (!r) return ''
    return r.length <= maxLen ? r : `${r.slice(0, maxLen).trimEnd()}...`
  }

  // --- Actions ---
  async function loadTaskBoardItems() {
    const params = new URLSearchParams()
    if (taskBoardProjectFilter.value.trim()) params.set('project_id', taskBoardProjectFilter.value.trim())
    if (taskBoardKeyword.value.trim()) params.set('keyword', taskBoardKeyword.value.trim())
    const q = params.toString()
    const endpoint = q ? `${apiBase}/api/v1/task-board?${q}` : `${apiBase}/api/v1/task-board`
    const data = await fetchJson(endpoint)
    taskBoardItems.value = data.items || []
    collapseAllTaskNodes()
  }

  function collapseAllTaskNodes() {
    const tree = buildTaskTree(taskBoardItems.value)
    const pids = new Set()
    const walk = nodes => { for (const n of nodes) { if (n.children.length) pids.add(n.id); walk(n.children) } }
    walk(tree)
    collapsedTaskNodes.value = pids
  }

  function resetTaskBoardCreateForm() {
    taskBoardCreateForm.value = { name: '', description: '', ai_platform: 'hermes', project_id: '', upstream_task_id: '', parent_task_id: '', status: 'draft', status_reason: '', priority: 3 }
  }

  function openTaskBoardCreateModal() { resetTaskBoardCreateForm(); isTaskBoardCreateModalOpen.value = true }
  function closeTaskBoardCreateModal() { if (!creatingTaskBoardItem.value) isTaskBoardCreateModalOpen.value = false }

  function openTaskBoardEditModal(item) {
    editingTaskBoardItemId.value = item.id
    taskBoardEditForm.value = {
      name: item.name, description: item.description || '',
      ai_platform: (item.ai_platform || '').trim().toLowerCase() === 'none' || !item.ai_platform ? 'hermes' : item.ai_platform.trim().toLowerCase(),
      project_id: item.project_id || '', upstream_task_id: item.upstream_task_id || '',
      parent_task_id: item.parent_task_id || '', status: item.status || 'draft',
      status_reason: item.status_reason || '', priority: item.priority ?? 3,
    }
    isTaskBoardEditModalOpen.value = true
  }

  function closeTaskBoardEditModal() { if (!updatingTaskBoardItem.value) { isTaskBoardEditModalOpen.value = false; editingTaskBoardItemId.value = '' } }
  function openTaskBoardDetailModal(item) { taskBoardDetailItem.value = item }
  function closeTaskBoardDetailModal() { taskBoardDetailItem.value = null }

  function openTaskBoardByProject(project) {
    taskBoardProjectFilter.value = project.id
    taskBoardKeyword.value = ''
    taskBoardStatusFilter.value = ''
  }

  function resolveTaskProjectContext(task) {
    const ss = useSessionStore()
    const projects = ss?.projects ?? []
    const pb = task.project_id ? projects.find(p => p.id === task.project_id) : null
    const repoUrl = task.project_repository_url || pb?.repository_url || ''
    const repoName = task.project_repository_name || pb?.repository_name || (repoUrl ? repoUrl.split('/').pop() : '') || ''
    return { name: task.project_name || pb?.name || '', repositoryName: repoName, repositoryUrl: repoUrl }
  }

  function buildTaskSystemPrompt(task, projectCtx = null) {
    const ctx = projectCtx || resolveTaskProjectContext(task)
    const lines = ['[Task Context]', `Task: ${task.name}`]
    if (task.description) lines.push(`Description: ${task.description}`)
    lines.push(`Status: ${taskBoardStatusLabelMap[task.status] || task.status}`)
    lines.push(`AI Platform: ${(task.ai_platform || '').trim().toLowerCase() === 'none' ? 'hermes' : task.ai_platform}`)
    if (ctx?.name || ctx?.repositoryName || ctx?.repositoryUrl) {
      lines.push('\n[Project]')
      if (ctx.name) lines.push(`Project: ${ctx.name}`)
      if (ctx.repositoryName) lines.push(`Repository: ${ctx.repositoryName}`)
      if (ctx.repositoryUrl) lines.push(`Repository URL: ${ctx.repositoryUrl}`)
    }
    if (task.upstream_task_name) lines.push(`\n[Upstream Dependency] ${task.upstream_task_name}`)
    if (task.parent_task_name) lines.push(`[Parent Task] ${task.parent_task_name}`)
    return lines.join('\n')
  }

  function buildTaskStartMessage(task, projectCtx = null) {
    const ctx = projectCtx || resolveTaskProjectContext(task)
    const lines = ['请根据任务上下文开始工作。']
    if (ctx?.name) lines.push(`关联项目: ${ctx.name}`)
    if (ctx?.repositoryName) lines.push(`仓库: ${ctx.repositoryName}`)
    if (ctx?.repositoryUrl) lines.push(`仓库地址: ${ctx.repositoryUrl}`)
    lines.push(`任务: ${task.name}`)
    return lines.join('\n')
  }

  async function selectExistingDispatchSession(task, dispatchTask) {
    const ss = useSessionStore()
    const esid = dispatchTask.external_session_id || dispatchTask.id
    await ss.loadSessions()
    const safePlat = (v) => { const v2 = (v || '').trim().toLowerCase(); return v2 === 'none' || !v2 ? 'hermes' : v2 }
    const matched = ss.sessions.find(s => s.platform === safePlat(task.ai_platform) && s.external_session_id === esid)
    if (matched) {
      ss.selectedSessionId = matched.id
      ss.selectedExternalSessionId = matched.external_session_id
    } else {
      ss.selectedExternalSessionId = esid
    }
    await ss.restoreActiveDispatchTask()
  }

  async function startConversationFromTask(task) {
    if (startingConversationFromTask.value) return
    startingConversationFromTask.value = true
    const ss = useSessionStore()
    ss.errorMessage = ''
    try {
      let resolved = null
      try { resolved = await fetchJson(`${apiBase}/api/v1/dispatch/task-board/${encodeURIComponent(task.id)}/work-session`) } catch {}
      const action = resolved?.recommended_action || 'create_new'
      if (action === 'resume' && resolved?.active_dispatch_task) { await selectExistingDispatchSession(task, resolved.active_dispatch_task); return }
      if (action === 'view_history' && resolved?.latest_dispatch_task) { await selectExistingDispatchSession(task, resolved.latest_dispatch_task); return }
      const projectCtx = resolveTaskProjectContext(task)
      const sysPrompt = buildTaskSystemPrompt(task, projectCtx)
      const platform = (task.ai_platform || '').trim().toLowerCase() === 'none' ? 'hermes' : task.ai_platform
      const promptMsg = buildTaskStartMessage(task, projectCtx)
      const esid = `task_board_${task.id}`
      const dispatchTask = await ss.createDispatchTask({
        aiPlatform: platform, initialPrompt: promptMsg, systemPrompt: sysPrompt,
        model: '', skills: [], mcpServers: [],
        taskBoardItemId: task.id, externalSessionId: esid,
      })
      await postJson(`${apiBase}/api/v1/events/ingest`, {
        platform, event_id: `evt_init_${dispatchTask.id}`, event_type: 'session_started',
        external_session_id: esid, title: task.name,
        payload_json: { source: 'task-board', task_board_item_id: task.id, dispatch_task_id: dispatchTask.id },
        message: { role: 'user', content: promptMsg },
      })
      await postJson(`${apiBase}/api/v1/events/ingest`, {
        platform, event_id: `evt_progress_${dispatchTask.id}`, event_type: 'dispatch_created',
        external_session_id: esid, title: task.name,
        payload_json: { source: 'task-board', status: 'running', dispatch_task_id: dispatchTask.id },
        message: { role: 'system', content: '🔄 已提交 Dispatch 任务，等待 AI Agent 处理中...' },
      })
      await ss.loadSessions()
      ss.selectedSessionId = ss.sessions.find(s => s.platform === platform && s.external_session_id === esid)?.id || ss.selectedSessionId
    } catch (error) {
      ss.errorMessage = error instanceof Error ? error.message : 'Unknown error'
    } finally {
      startingConversationFromTask.value = false
    }
  }

  function ensureTaskStatusReasonBeforeSave(form) {
    const nr = normalizeTaskStatusReason(form.status, form.status_reason)
    if (requiresTaskStatusReason(form.status) && !nr) throw new Error('阻塞或取消任务时必须填写原因')
    return nr
  }

  function buildTaskBoardPayload(formState) {
    return {
      name: formState.name.trim(), description: formState.description.trim(),
      ai_platform: (formState.ai_platform || '').trim().toLowerCase(),
      status: formState.status, status_reason: ensureTaskStatusReasonBeforeSave(formState),
      priority: formState.priority,
      project_id: formState.project_id || null,
      upstream_task_id: formState.upstream_task_id || null,
      parent_task_id: formState.parent_task_id || null,
    }
  }

  function buildTaskBoardUpdatePayload(item, patch) {
    const ns = patch.status ?? item.status ?? 'draft'
    const nrs = Object.prototype.hasOwnProperty.call(patch, 'status_reason') ? patch.status_reason : (item.status_reason || '')
    return {
      name: item.name, description: item.description || '',
      ai_platform: (item.ai_platform || '').trim().toLowerCase(),
      status: ns, status_reason: normalizeTaskStatusReason(ns, nrs),
      priority: item.priority ?? 3,
      project_id: item.project_id || null,
      upstream_task_id: item.upstream_task_id || null,
      parent_task_id: item.parent_task_id || null,
      ...patch,
    }
  }

  async function updateTaskBoardItemQuick(item, patch) {
    if (!item?.id || quickUpdatingTaskBoardItemId.value === item.id) return
    const ts = patch.status ?? item.status ?? 'draft'
    if (requiresTaskStatusReason(ts) && ts !== (item.status ?? 'draft') && !Object.prototype.hasOwnProperty.call(patch, 'status_reason')) {
      openTaskBoardEditModal({ ...item, status: ts, status_reason: '' })
      useSessionStore().errorMessage = `请先填写${taskBoardStatusLabelMap[ts] || ts}原因`
      return
    }
    quickUpdatingTaskBoardItemId.value = item.id
    try {
      const updated = await patchJson(`${apiBase}/api/v1/task-board/${item.id}`, buildTaskBoardUpdatePayload(item, patch))
      taskBoardItems.value = taskBoardItems.value.map(e => e.id === item.id ? updated : e)
      if (taskBoardDetailItem.value?.id === item.id) taskBoardDetailItem.value = updated
    } catch (e) {
      useSessionStore().errorMessage = e instanceof Error ? e.message : 'Unknown error'
    } finally { quickUpdatingTaskBoardItemId.value = '' }
  }

  function handleTaskBoardDragStart(item, event) {
    if (!item?.id) return
    draggingTaskBoardItemId.value = item.id
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', item.id)
  }
  function handleTaskBoardDragEnd() { draggingTaskBoardItemId.value = '' }
  async function handleTaskBoardDrop(status, event) {
    const tid = event.dataTransfer.getData('text/plain') || draggingTaskBoardItemId.value
    draggingTaskBoardItemId.value = ''
    const item = taskBoardItems.value.find(e => e.id === tid)
    if (!item || item.status === status) return
    await updateTaskBoardItemQuick(item, { status })
  }
  async function updateTaskBoardPriority(item, event) {
    const p = Number(event.target.value)
    if (!item || !Number.isInteger(p) || item.priority === p) return
    await updateTaskBoardItemQuick(item, { priority })
  }

  async function submitCreateTaskBoardItem() {
    if (creatingTaskBoardItem.value || !taskBoardCreateForm.value.name.trim()) return
    creatingTaskBoardItem.value = true
    try {
      await postJson(`${apiBase}/api/v1/task-board`, buildTaskBoardPayload(taskBoardCreateForm.value))
      isTaskBoardCreateModalOpen.value = false
      await loadTaskBoardItems()
    } catch (e) {
      useSessionStore().errorMessage = e instanceof Error ? e.message : 'Unknown error'
    } finally { creatingTaskBoardItem.value = false }
  }

  async function submitEditTaskBoardItem() {
    if (updatingTaskBoardItem.value || !editingTaskBoardItemId.value || !taskBoardEditForm.value.name.trim()) return
    updatingTaskBoardItem.value = true
    try {
      await patchJson(`${apiBase}/api/v1/task-board/${editingTaskBoardItemId.value}`, buildTaskBoardPayload(taskBoardEditForm.value))
      isTaskBoardEditModalOpen.value = false
      editingTaskBoardItemId.value = ''
      await loadTaskBoardItems()
    } catch (e) {
      useSessionStore().errorMessage = e instanceof Error ? e.message : 'Unknown error'
    } finally { updatingTaskBoardItem.value = false }
  }

  // --- Archive ---
  async function loadArchivedTasks() {
    archiveLoading.value = true
    try {
      const params = new URLSearchParams()
      if (archiveProjectFilter.value) params.set('project_id', archiveProjectFilter.value)
      if (archiveKeyword.value) params.set('keyword', archiveKeyword.value)
      if (archiveStatusFilter.value) params.set('status', archiveStatusFilter.value)
      const qs = params.toString()
      archivedTaskItems.value = (await fetchJson(`${apiBase}/api/v1/task-board/archived${qs ? '?' + qs : ''}`)).items
    } catch (e) { console.error('Failed to load archived tasks', e) }
    finally { archiveLoading.value = false }
  }

  async function archiveTaskBoardItem(item) {
    if (!item?.id || archivingTaskId.value) return
    const warn = ['in_progress', 'pending_execution'].includes(item.status) ? '进行中的异步任务将被取消。' : ''
    if (!window.confirm(`归档任务「${item.name}」？${warn}`)) return
    archivingTaskId.value = item.id
    try {
      await patchJson(`${apiBase}/api/v1/task-board/${item.id}/archive`, {})
      await loadTaskBoardItems()
      await loadArchivedTasks()
    } catch (e) { useSessionStore().errorMessage = e instanceof Error ? e.message : 'Unknown error' }
    finally { archivingTaskId.value = '' }
  }

  async function unarchiveTaskBoardItem(item) {
    unarchivingTaskId.value = item.id
    try {
      await patchJson(`${apiBase}/api/v1/task-board/${item.id}/unarchive`, {})
      await loadArchivedTasks()
      await loadTaskBoardItems()
    } catch (e) { console.error('Failed to unarchive task', e) }
    finally { unarchivingTaskId.value = '' }
  }

  async function switchToTaskArchive() {
    await loadArchivedTasks()
  }

  return {
    taskBoardItems, taskBoardProjectFilter, taskBoardKeyword, taskBoardStatusFilter,
    isTaskBoardCreateModalOpen, isTaskBoardEditModalOpen,
    creatingTaskBoardItem, updatingTaskBoardItem, quickUpdatingTaskBoardItemId,
    draggingTaskBoardItemId, editingTaskBoardItemId,
    taskBoardDetailItem, highlightedTaskBoardItemId, startingConversationFromTask,
    taskBoardCreateForm, taskBoardEditForm,
    collapsedProjectRows, collapsedTaskNodes, collapsedKanbanStatuses,
    archivedTaskItems, archiveProjectFilter, archiveKeyword, archiveStatusFilter,
    archiveLoading, archivingTaskId, unarchivingTaskId, archiveDetailItem, isArchiveDetailOpen,
    taskBoardStatusOptions, taskBoardStatusLabelMap, taskBoardPriorityOptions, taskBoardPriorityLabelMap,
    filteredTaskBoardItems, taskBoardProjectOptions, taskBoardDependencyOptions,
    taskBoardStatusFilterOptions, taskBoardMatrix,
    kanbanGridTemplate, kanbanMatrixMinWidth, kanbanMatrixStyle,
    loadTaskBoardItems, collapseAllTaskNodes,
    resetTaskBoardCreateForm, openTaskBoardCreateModal, closeTaskBoardCreateModal,
    openTaskBoardEditModal, closeTaskBoardEditModal,
    openTaskBoardDetailModal, closeTaskBoardDetailModal,
    openTaskBoardByProject,
    resolveTaskProjectContext, buildTaskSystemPrompt, buildTaskStartMessage,
    selectExistingDispatchSession, startConversationFromTask,
    findTaskBoardItemById, getTaskPriority,
    isKanbanStatusCollapsible, isKanbanStatusCollapsed, toggleKanbanStatusColumn,
    toggleProjectRow, toggleTaskNode,
    taskBoardStatusClass, taskBoardDetailField,
    requiresTaskStatusReason, normalizeTaskStatusReason, getTaskStatusReasonPreview,
    ensureTaskStatusReasonBeforeSave, buildTaskBoardPayload, buildTaskBoardUpdatePayload,
    updateTaskBoardItemQuick,
    handleTaskBoardDragStart, handleTaskBoardDragEnd, handleTaskBoardDrop, updateTaskBoardPriority,
    submitCreateTaskBoardItem, submitEditTaskBoardItem,
    loadArchivedTasks, archiveTaskBoardItem, unarchiveTaskBoardItem, switchToTaskArchive,
    KANBAN_PRIORITY_LABELS,
  }
})
