<script setup>
import { computed, onMounted, ref } from 'vue'

const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:18000'

const sessions = ref([])
const selectedSessionId = ref('')
const timeline = ref({ messages: [], events: [] })
const cockpit = ref(null)
const loading = ref(false)
const errorMessage = ref('')

const selectedSession = computed(() => sessions.value.find((s) => s.id === selectedSessionId.value) || null)

const laneTitleMap = {
  todo: '待处理',
  doing: '进行中',
  done: '已完成',
}

const roleLabelMap = {
  user: '用户',
  assistant: '助手',
  system: '系统',
  tool: '工具',
}

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

const sessionSummary = computed(() => {
  const session = cockpit.value?.session
  const metrics = cockpit.value?.metrics
  return {
    messages: session?.message_count ?? 0,
    tasks: session?.task_count ?? 0,
    tokenIn: metrics?.token_in ?? 0,
    tokenOut: metrics?.token_out ?? 0,
    latency: metrics?.latency_ms_p50 ?? 0,
    errors: metrics?.error_count ?? 0,
  }
})

function laneClass(lane) {
  return `lane-${lane}`
}

function roleClass(role) {
  return `role-${role || 'assistant'}`
}

async function fetchJson(url) {
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }
  return response.json()
}

async function loadSessions() {
  const data = await fetchJson(`${apiBase}/api/v1/sessions`)
  sessions.value = data
  if (!selectedSessionId.value && data.length > 0) {
    selectedSessionId.value = data[0].id
  }
}

async function loadSessionData() {
  if (!selectedSessionId.value) {
    return
  }
  const [timelineData, cockpitData] = await Promise.all([
    fetchJson(`${apiBase}/api/v1/sessions/${selectedSessionId.value}/timeline`),
    fetchJson(`${apiBase}/api/v1/board/cockpit?session_id=${selectedSessionId.value}`),
  ])
  timeline.value = timelineData
  cockpit.value = cockpitData
}

async function refreshData() {
  loading.value = true
  errorMessage.value = ''
  try {
    await loadSessions()
    await loadSessionData()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    loading.value = false
  }
}

onMounted(refreshData)
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

        <div class="toolbar">
          <select v-model="selectedSessionId" class="input" @change="refreshData">
            <option v-for="session in sessions" :key="session.id" :value="session.id">
              {{ session.title }} ({{ session.platform }})
            </option>
          </select>
          <button class="refresh" :disabled="loading" @click="refreshData">{{ loading ? '刷新中...' : '刷新' }}</button>
        </div>
      </header>

      <div v-if="errorMessage" class="error panel">{{ errorMessage }}</div>

      <section class="main-grid">
        <article class="panel tasks-panel">
          <h2>任务看板</h2>
          <div class="lanes">
            <div v-for="lane in ['todo', 'doing', 'done']" :key="lane" class="lane" :class="laneClass(lane)">
              <h3>{{ laneTitleMap[lane] }}</h3>
              <div v-for="task in taskLanes[lane]" :key="task.id" class="task">
                <div class="task-title">{{ task.title }}</div>
                <div class="muted">优先级 {{ task.priority }}</div>
              </div>
              <div v-if="taskLanes[lane].length === 0" class="muted">暂无任务</div>
            </div>
          </div>

          <section class="kpi-corner panel-soft">
            <article class="kpi-mini">
              <div class="kpi-label">消息数</div>
              <div class="kpi-value">{{ sessionSummary.messages }}</div>
            </article>
            <article class="kpi-mini">
              <div class="kpi-label">任务数</div>
              <div class="kpi-value">{{ sessionSummary.tasks }}</div>
            </article>
            <article class="kpi-mini">
              <div class="kpi-label">延迟 P50</div>
              <div class="kpi-value">{{ sessionSummary.latency }} ms</div>
            </article>
            <article class="kpi-mini">
              <div class="kpi-label">错误数</div>
              <div class="kpi-value">{{ sessionSummary.errors }}</div>
            </article>
          </section>
        </article>

        <article class="panel timeline-panel">
          <h2>对话时间线</h2>
          <div v-if="timeline.messages?.length === 0" class="muted">暂无消息</div>
          <div v-for="message in timeline.messages" :key="message.id" class="timeline-item">
            <div class="role-chip" :class="roleClass(message.role)">{{ roleLabelMap[message.role] || message.role }}</div>
            <div class="timeline-meta">{{ new Date(message.created_at).toLocaleString() }}</div>
            <div class="timeline-content">{{ message.content }}</div>
          </div>
        </article>

        <article class="panel state-panel">
          <h2>会话状态</h2>
          <div class="kv"><span class="muted">会话</span><span>{{ selectedSession?.title || '-' }}</span></div>
          <div class="kv"><span class="muted">平台</span><span>{{ selectedSession?.platform || '-' }}</span></div>
          <div class="kv"><span class="muted">Token In</span><span>{{ sessionSummary.tokenIn }}</span></div>
          <div class="kv"><span class="muted">Token Out</span><span>{{ sessionSummary.tokenOut }}</span></div>
          <div class="kv"><span class="muted">延迟 P50</span><span>{{ sessionSummary.latency }} ms</span></div>
          <div class="kv"><span class="muted">错误数</span><span>{{ sessionSummary.errors }}</span></div>
          <hr class="sep" />
          <div class="next-step">下一步建议：优先清理进行中任务并继续拉取最新会话事件。</div>
        </article>
      </section>
    </section>
  </main>
</template>
