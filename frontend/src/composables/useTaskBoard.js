import { computed, ref } from 'vue'
import { fetchJson, patchJson, postJson } from '../services/apiClient.js'
import { buildTaskTree, countTaskTreeNodes, getTaskPriority, makeTaskNodeKey } from '../services/taskBoardTree.js'
import {
  COLLAPSIBLE_KANBAN_STATUSES,
  KANBAN_PRIORITY_LABELS,
  KANBAN_STATUSES,
  TASK_BOARD_PRIORITY_LABEL_MAP,
  TASK_BOARD_PRIORITY_OPTIONS,
  TASK_BOARD_STATUS_LABEL_MAP,
  TASK_BOARD_STATUS_OPTIONS,
} from '../constants/appConstants.js'

const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:18000'

export function useTaskBoard(projectsRef) {
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
  const taskBoardDetailItem = ref(null)
  const highlightedTaskBoardItemId = ref('')
  const startingConversationFromTask = ref(false)
  const editingTaskBoardItemId = ref('')
  const collapsedProjectRows = ref(new Set())
  const collapsedTaskNodes = ref(new Set())
  const collapsedKanbanStatuses = ref(new Set(['completed']))

  const taskBoardCreateForm = ref({
    name: '', description: '', ai_platform: 'hermes',
    project_id: '', upstream_task_id: '', parent_task_id: '',
    status: 'draft', status_reason: '', priority: 3,
  })
  const taskBoardEditForm = ref({
    name: '', description: '', ai_platform: 'hermes',
    project_id: '', upstream_task_id: '', parent_task_id: '',
    status: 'draft', status_reason: '', priority: 3,
  })

  const taskBoardStatusOptions = TASK_BOARD_STATUS_OPTIONS
  const taskBoardStatusLabelMap = TASK_BOARD_STATUS_LABEL_MAP
  const taskBoardPriorityOptions = TASK_BOARD_PRIORITY_OPTIONS
  const taskBoardPriorityLabelMap = TASK_BOARD_PRIORITY_LABEL_MAP

  const taskBoardProjectOptions = computed(() => [
    { value: '', label: '全部项目' },
    ...(projectsRef?.value || []).map((item) => ({ value: item.id, label: `${item.name}（${item.code}）` })),
  ])

  const taskBoardDependencyOptions = computed(() => taskBoardItems.value.map((item) => ({ value: item.id, label: item.name })))

  const filteredTaskBoardItems = computed(() => {
    const keyword = taskBoardKeyword.value.trim().toLowerCase()
    const projectId = taskBoardProjectFilter.value.trim()
    const statusFilter = taskBoardStatusFilter.value.trim()
    return taskBoardItems.value.filter((item) => {
      if (projectId && item.project_id !== projectId) return false
      if (statusFilter && item.status !== statusFilter) return false
      if (!keyword) return true
      const text = `${item.name} ${item.description} ${item.ai_platform} ${item.project_name || ''}`.toLowerCase()
      return text.includes(keyword)
    })
  })

  const KANBAN_LABEL_TRACK = 'minmax(clamp(8rem, 13vw, 11rem), 0.52fr)'
  const KANBAN_EXPANDED_TRACK = 'minmax(clamp(10rem, 12vw, 14rem), 1fr)'
  const KANBAN_COLLAPSED_TRACK = 'minmax(4.4rem, 0.22fr)'
  const KANBAN_LABEL_MIN_REM = 8
  const KANBAN_EXPANDED_MIN_REM = 10
  const KANBAN_COLLAPSED_MIN_REM = 4.4

  const kanbanGridTemplate = computed(() => (
    [KANBAN_LABEL_TRACK, ...KANBAN_STATUSES.map((status) => (
      collapsedKanbanStatuses.value.has(status) ? KANBAN_COLLAPSED_TRACK : KANBAN_EXPANDED_TRACK
    ))].join(' ')
  ))

  const kanbanMatrixMinWidth = computed(() => {
    const w = KANBAN_STATUSES.reduce((sum, s) => (
      sum + (collapsedKanbanStatuses.value.has(s) ? KANBAN_COLLAPSED_MIN_REM : KANBAN_EXPANDED_MIN_REM)
    ), 0)
    return `${KANBAN_LABEL_MIN_REM + w}rem`
  })

  const kanbanMatrixStyle = computed(() => ({
    '--kanban-grid-template': kanbanGridTemplate.value,
    '--kanban-matrix-min-width': kanbanMatrixMinWidth.value,
  }))

  const taskBoardMatrix = computed(() => {
    const projectMap = new Map()
    for (const item of filteredTaskBoardItems.value) {
      const projectKey = item.project_id || '__none__'
      const projectName = item.project_name || '未关联项目'
      if (!projectMap.has(projectKey)) {
        projectMap.set(projectKey, { id: projectKey, name: projectName, columns: Object.fromEntries(KANBAN_STATUSES.map((s) => [s, []])) })
      }
      const project = projectMap.get(projectKey)
      const status = KANBAN_STATUSES.includes(item.status) ? item.status : 'draft'
      project.columns[status].push(item)
    }
    return [...projectMap.values()]
      .map((project) => {
        const columns = Object.fromEntries(KANBAN_STATUSES.map((s) => [s, buildTaskTree(project.columns[s])]))
        return { ...project, columns, taskCount: KANBAN_STATUSES.reduce((sum, s) => sum + countTaskTreeNodes(columns[s]), 0) }
      })
      .sort((a, b) => {
        if (a.id === '__none__') return 1
        if (b.id === '__none__') return -1
        return a.name.localeCompare(b.name)
      })
  })

  function safePlatform(value) {
    const v = (value || '').trim().toLowerCase()
    return (v === 'none' || v === '') ? 'hermes' : (v || 'hermes')
  }

  function isKanbanStatusCollapsible(status) { return COLLAPSIBLE_KANBAN_STATUSES.includes(status) }
  function isKanbanStatusCollapsed(status) { return collapsedKanbanStatuses.value.has(status) }

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

  function requiresTaskStatusReason(status) { return status === 'blocked' || status === 'cancelled' }

  function normalizeTaskStatusReason(status, reason) {
    if (!requiresTaskStatusReason(status)) return ''
    return String(reason || '').trim()
  }

  function getTaskStatusReasonPreview(item, maxLength = 96) {
    const reason = String(item?.status_reason || '').trim()
    if (!reason) return ''
    if (reason.length <= maxLength) return reason
    return `${reason.slice(0, maxLength).trimEnd()}...`
  }

  function ensureTaskStatusReasonBeforeSave(formState) {
    const normalizedReason = normalizeTaskStatusReason(formState.status, formState.status_reason)
    if (requiresTaskStatusReason(formState.status) && !normalizedReason) {
      throw new Error('阻塞或取消任务时必须填写原因')
    }
    return normalizedReason
  }

  function buildTaskBoardPayload(formState) {
    const normalizedReason = ensureTaskStatusReasonBeforeSave(formState)
    return {
      name: formState.name.trim(),
      description: formState.description.trim(),
      ai_platform: safePlatform(formState.ai_platform),
      status: formState.status,
      status_reason: normalizedReason,
      priority: formState.priority,
      project_id: formState.project_id || null,
      upstream_task_id: formState.upstream_task_id || null,
      parent_task_id: formState.parent_task_id || null,
    }
  }

  function buildTaskBoardUpdatePayload(item, patch) {
    const nextStatus = patch.status ?? item.status ?? 'draft'
    const nextReasonSource = Object.prototype.hasOwnProperty.call(patch, 'status_reason')
      ? patch.status_reason
      : (item.status_reason || '')
    return {
      name: item.name,
      description: item.description || '',
      ai_platform: safePlatform(item.ai_platform),
      status: nextStatus,
      status_reason: normalizeTaskStatusReason(nextStatus, nextReasonSource),
      priority: item.priority ?? 3,
      project_id: item.project_id || null,
      upstream_task_id: item.upstream_task_id || null,
      parent_task_id: item.parent_task_id || null,
      ...patch,
    }
  }

  function taskBoardDetailField(value) {
    const normalized = String(value || '').trim()
    return normalized || '-'
  }

  function taskBoardStatusClass(status) { return `task-status-${status || 'draft'}` }

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

  async function loadTaskBoardItems() {
    const params = new URLSearchParams()
    if (taskBoardProjectFilter.value.trim()) params.set('project_id', taskBoardProjectFilter.value.trim())
    if (taskBoardKeyword.value.trim()) params.set('keyword', taskBoardKeyword.value.trim())
    const query = params.toString()
    const endpoint = query ? `${apiBase}/api/v1/task-board?${query}` : `${apiBase}/api/v1/task-board`
    const data = await fetchJson(endpoint)
    taskBoardItems.value = data.items || []
    collapseAllTaskNodes()
  }

  function resetTaskBoardCreateForm() {
    taskBoardCreateForm.value = {
      name: '', description: '', ai_platform: 'hermes',
      project_id: '', upstream_task_id: '', parent_task_id: '',
      status: 'draft', status_reason: '', priority: 3,
    }
  }

  function openTaskBoardCreateModal() {
    resetTaskBoardCreateForm()
    isTaskBoardCreateModalOpen.value = true
  }

  function closeTaskBoardCreateModal() {
    if (creatingTaskBoardItem.value) return
    isTaskBoardCreateModalOpen.value = false
  }

  function openTaskBoardEditModal(item) {
    editingTaskBoardItemId.value = item.id
    taskBoardEditForm.value = {
      name: item.name,
      description: item.description || '',
      ai_platform: safePlatform(item.ai_platform),
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
    if (updatingTaskBoardItem.value) return
    isTaskBoardEditModalOpen.value = false
    editingTaskBoardItemId.value = ''
  }

  function openTaskBoardDetailModal(item) { taskBoardDetailItem.value = item }
  function closeTaskBoardDetailModal() { taskBoardDetailItem.value = null }

  async function updateTaskBoardItemQuick(item, patch, onError) {
    if (!item?.id || quickUpdatingTaskBoardItemId.value === item.id) return
    const targetStatus = patch.status ?? item.status ?? 'draft'
    if (
      requiresTaskStatusReason(targetStatus)
      && targetStatus !== (item.status ?? 'draft')
      && !Object.prototype.hasOwnProperty.call(patch, 'status_reason')
    ) {
      openTaskBoardEditModal({ ...item, status: targetStatus, status_reason: '' })
      if (onError) onError(`请先填写${taskBoardStatusLabelMap[targetStatus] || targetStatus}原因`)
      return
    }
    quickUpdatingTaskBoardItemId.value = item.id
    try {
      const updated = await patchJson(`${apiBase}/api/v1/task-board/${item.id}`, buildTaskBoardUpdatePayload(item, patch))
      taskBoardItems.value = taskBoardItems.value.map((entry) => (entry.id === item.id ? updated : entry))
      if (taskBoardDetailItem.value?.id === item.id) taskBoardDetailItem.value = updated
    } catch (error) {
      if (onError) onError(error instanceof Error ? error.message : 'Unknown error')
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

  function handleTaskBoardDragEnd() { draggingTaskBoardItemId.value = '' }

  async function handleTaskBoardDrop(status, event, onError) {
    const taskId = event.dataTransfer.getData('text/plain') || draggingTaskBoardItemId.value
    draggingTaskBoardItemId.value = ''
    const item = taskBoardItems.value.find((entry) => entry.id === taskId)
    if (!item || item.status === status) return
    await updateTaskBoardItemQuick(item, { status }, onError)
  }

  async function updateTaskBoardPriority(item, event, onError) {
    const priority = Number(event.target.value)
    if (!item || !Number.isInteger(priority) || item.priority === priority) return
    await updateTaskBoardItemQuick(item, { priority }, onError)
  }

  async function submitCreateTaskBoardItem(onError) {
    if (creatingTaskBoardItem.value || !taskBoardCreateForm.value.name.trim()) return
    creatingTaskBoardItem.value = true
    try {
      await postJson(`${apiBase}/api/v1/task-board`, buildTaskBoardPayload(taskBoardCreateForm.value))
      isTaskBoardCreateModalOpen.value = false
      await loadTaskBoardItems()
    } catch (error) {
      if (onError) onError(error instanceof Error ? error.message : 'Unknown error')
    } finally {
      creatingTaskBoardItem.value = false
    }
  }

  async function submitEditTaskBoardItem(onError) {
    if (updatingTaskBoardItem.value || !editingTaskBoardItemId.value || !taskBoardEditForm.value.name.trim()) return
    updatingTaskBoardItem.value = true
    try {
      await patchJson(`${apiBase}/api/v1/task-board/${editingTaskBoardItemId.value}`, buildTaskBoardPayload(taskBoardEditForm.value))
      isTaskBoardEditModalOpen.value = false
      editingTaskBoardItemId.value = ''
      await loadTaskBoardItems()
    } catch (error) {
      if (onError) onError(error instanceof Error ? error.message : 'Unknown error')
    } finally {
      updatingTaskBoardItem.value = false
    }
  }

  function findTaskBoardItemById(taskId) {
    if (!taskId) return null
    return taskBoardItems.value.find((item) => item.id === taskId) || null
  }

  function formatSessionTime(value) {
    if (!value) return '-'
    const parsed = new Date(value)
    if (Number.isNaN(parsed.getTime())) return '-'
    return parsed.toLocaleString()
  }

  return {
    taskBoardItems,
    taskBoardProjectFilter,
    taskBoardKeyword,
    taskBoardStatusFilter,
    isTaskBoardCreateModalOpen,
    isTaskBoardEditModalOpen,
    creatingTaskBoardItem,
    updatingTaskBoardItem,
    quickUpdatingTaskBoardItemId,
    draggingTaskBoardItemId,
    taskBoardDetailItem,
    highlightedTaskBoardItemId,
    startingConversationFromTask,
    editingTaskBoardItemId,
    collapsedProjectRows,
    collapsedTaskNodes,
    collapsedKanbanStatuses,
    taskBoardCreateForm,
    taskBoardEditForm,
    taskBoardStatusOptions,
    taskBoardStatusLabelMap,
    taskBoardPriorityOptions,
    taskBoardPriorityLabelMap,
    taskBoardProjectOptions,
    taskBoardDependencyOptions,
    filteredTaskBoardItems,
    kanbanMatrixStyle,
    taskBoardMatrix,
    KANBAN_STATUSES,
    KANBAN_PRIORITY_LABELS,
    safePlatform,
    isKanbanStatusCollapsible,
    isKanbanStatusCollapsed,
    toggleKanbanStatusColumn,
    toggleProjectRow,
    toggleTaskNode,
    requiresTaskStatusReason,
    getTaskStatusReasonPreview,
    taskBoardDetailField,
    taskBoardStatusClass,
    loadTaskBoardItems,
    openTaskBoardCreateModal,
    closeTaskBoardCreateModal,
    openTaskBoardEditModal,
    closeTaskBoardEditModal,
    openTaskBoardDetailModal,
    closeTaskBoardDetailModal,
    updateTaskBoardItemQuick,
    handleTaskBoardDragStart,
    handleTaskBoardDragEnd,
    handleTaskBoardDrop,
    updateTaskBoardPriority,
    submitCreateTaskBoardItem,
    submitEditTaskBoardItem,
    findTaskBoardItemById,
    getTaskPriority,
    countTaskTreeNodes,
    formatSessionTime,
  }
}
