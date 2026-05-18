<script setup>
import { ref, onMounted } from 'vue'
import { useDispatchHistory } from '../composables/useDispatchHistory.js'
import { useSessionStore } from '../stores/useSessionStore.js'

const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:18000'

const dh = useDispatchHistory()
const ss = useSessionStore()

const dispatchDetailTask = ref(null)
const dispatchDetailEvents = ref([])

const dispatchStatusLabelMap = dh.dispatchStatusLabelMap
const filteredDispatchTasks = dh.filteredTasks
const dispatchStats = dh.taskStats
const dispatchHistoryLoading = dh.historyLoading
const dispatchHistoryError = dh.historyError
const dispatchHistoryStatusFilter = dh.statusFilter

async function refreshDispatchHistory() { await dh.fetchTaskHistory(dispatchHistoryStatusFilter.value) }
async function viewDispatchTaskDetail(task) {
  dispatchDetailTask.value = task
  dispatchDetailEvents.value = []
  try { const data = await dh.fetchTaskEvents(task.id); dispatchDetailEvents.value = data.events || data || [] } catch {}
}
async function resumeFromHistory(task) {
  dispatchDetailTask.value = null
  const esid = task?.external_session_id || `dispatch_${task?.id || ''}`
  const matched = ss.sessions.find(s => s.external_session_id === esid)
  if (matched) { ss.selectedSessionId = matched.id; ss.selectedExternalSessionId = matched.external_session_id }
  else { ss.selectedExternalSessionId = esid }
  await ss.restoreActiveDispatchTask()
}
async function cancelFromHistory(task) {
  try {
    await fetch(`${apiBase}/api/v1/dispatch/${task.id}/cancel`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
    await refreshDispatchHistory()
    dispatchDetailTask.value = null
  } catch {}
}

function formatTime(value) {
  if (!value) return '-'
  const p = new Date(value)
  if (Number.isNaN(p.getTime())) return '-'
  return p.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

onMounted(async () => { await refreshDispatchHistory() })
</script>

<template>
  <section class="main-grid dispatch-history-grid">
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
      <div class="dispatch-stats-bar">
        <span class="dispatch-stat">总计: {{ dispatchStats.total }}</span>
        <span class="dispatch-stat dispatch-stat-success">完成: {{ dispatchStats.completed }}</span>
        <span class="dispatch-stat dispatch-stat-error">失败: {{ dispatchStats.failed }}</span>
        <span class="dispatch-stat dispatch-stat-warn">运行: {{ dispatchStats.running + dispatchStats.queued }}</span>
      </div>
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
</template>
