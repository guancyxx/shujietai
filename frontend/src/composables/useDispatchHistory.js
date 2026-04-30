// Dispatch task history composable — list past dispatch tasks.
// Independent of the active-task composable (useDispatchTask).

import { ref, computed } from 'vue'

const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:18000'

const allTasks = ref([])
const historyLoading = ref(false)
const historyError = ref('')
const statusFilter = ref('')  // empty = all

const dispatchStatusLabelMap = {
  queued: '排队中',
  running: '运行中',
  awaiting_input: '等待输入',
  paused: '已暂停',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
}

async function fetchTaskHistory(status = '') {
  historyLoading.value = true
  historyError.value = ''

  try {
    const params = new URLSearchParams()
    if (status) params.set('status', status)
    const url = `${apiBase}/api/v1/dispatch${params.toString() ? '?' + params.toString() : ''}`
    const response = await fetch(url)
    if (!response.ok) throw new Error(`Request failed: ${response.status}`)
    const data = await response.json()
    allTasks.value = data.tasks || data || []
  } catch (error) {
    historyError.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    historyLoading.value = false
  }
}

async function fetchTaskEvents(taskId) {
  const response = await fetch(`${apiBase}/api/v1/dispatch/${taskId}/events`)
  if (!response.ok) throw new Error(`Request failed: ${response.status}`)
  return response.json()
}

const filteredTasks = computed(() => {
  if (!statusFilter.value) return allTasks.value
  return allTasks.value.filter(t => t.status === statusFilter.value)
})

const taskStats = computed(() => {
  const stats = { total: allTasks.value.length, queued: 0, running: 0, completed: 0, failed: 0, cancelled: 0, awaiting_input: 0, paused: 0 }
  for (const t of allTasks.value) {
    if (stats[t.status] !== undefined) stats[t.status]++
  }
  return stats
})

export function useDispatchHistory() {
  return {
    allTasks,
    filteredTasks,
    taskStats,
    historyLoading,
    historyError,
    statusFilter,
    dispatchStatusLabelMap,
    fetchTaskHistory,
    fetchTaskEvents,
  }
}