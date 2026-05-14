import { ref } from 'vue'
import { fetchJson, patchJson } from '../services/apiClient.js'
import { KANBAN_PRIORITY_LABELS, TASK_BOARD_STATUS_LABEL_MAP } from '../constants/appConstants.js'

const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:18000'

export function useArchive() {
  const archivedTaskItems = ref([])
  const archiveProjectFilter = ref('')
  const archiveKeyword = ref('')
  const archiveStatusFilter = ref('')
  const archiveLoading = ref(false)
  const archivingTaskId = ref('')
  const unarchivingTaskId = ref('')
  const archiveDetailItem = ref(null)
  const isArchiveDetailOpen = ref(false)

  const taskBoardStatusLabelMap = TASK_BOARD_STATUS_LABEL_MAP

  async function loadArchivedTasks() {
    archiveLoading.value = true
    try {
      const params = new URLSearchParams()
      if (archiveProjectFilter.value) params.set('project_id', archiveProjectFilter.value)
      if (archiveKeyword.value) params.set('keyword', archiveKeyword.value)
      if (archiveStatusFilter.value) params.set('status', archiveStatusFilter.value)
      const qs = params.toString()
      const url = `${apiBase}/api/v1/task-board/archived${qs ? '?' + qs : ''}`
      archivedTaskItems.value = (await fetchJson(url)).items
    } catch (err) {
      console.error('Failed to load archived tasks', err)
    } finally {
      archiveLoading.value = false
    }
  }

  async function archiveTaskBoardItem(item, onTaskBoardReload, onError) {
    if (!item?.id || archivingTaskId.value) return
    const statusWarning = ['in_progress', 'pending_execution'].includes(item.status)
      ? '进行中的异步任务将被取消。'
      : ''
    const confirmed = window.confirm(`归档任务「${item.name}」？${statusWarning}`)
    if (!confirmed) return
    archivingTaskId.value = item.id
    try {
      await patchJson(`${apiBase}/api/v1/task-board/${item.id}/archive`, {})
      if (onTaskBoardReload) await onTaskBoardReload()
      await loadArchivedTasks()
    } catch (error) {
      if (onError) onError(error instanceof Error ? error.message : 'Unknown error')
    } finally {
      archivingTaskId.value = ''
    }
  }

  async function unarchiveTaskBoardItem(item, onTaskBoardReload) {
    unarchivingTaskId.value = item.id
    try {
      await patchJson(`${apiBase}/api/v1/task-board/${item.id}/unarchive`, {})
      await loadArchivedTasks()
      if (onTaskBoardReload) await onTaskBoardReload()
    } catch (err) {
      console.error('Failed to unarchive task', err)
    } finally {
      unarchivingTaskId.value = ''
    }
  }

  function getTaskPriorityLocal(item) {
    return item?.priority ?? 3
  }

  function formatSessionTime(value) {
    if (!value) return '-'
    const parsed = new Date(value)
    if (Number.isNaN(parsed.getTime())) return '-'
    return parsed.toLocaleString()
  }

  return {
    archivedTaskItems,
    archiveProjectFilter,
    archiveKeyword,
    archiveStatusFilter,
    archiveLoading,
    archivingTaskId,
    unarchivingTaskId,
    archiveDetailItem,
    isArchiveDetailOpen,
    taskBoardStatusLabelMap,
    KANBAN_PRIORITY_LABELS,
    loadArchivedTasks,
    archiveTaskBoardItem,
    unarchiveTaskBoardItem,
    getTaskPriorityLocal,
    formatSessionTime,
  }
}
