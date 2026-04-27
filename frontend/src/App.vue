<script setup>
import { computed, onMounted, ref } from 'vue'

const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const sessions = ref([])
const selectedSessionId = ref('')
const timeline = ref({ messages: [], events: [] })
const cockpit = ref(null)
const loading = ref(false)
const errorMessage = ref('')

const selectedSession = computed(() => sessions.value.find((s) => s.id === selectedSessionId.value) || null)

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
  <main class="page">
    <header class="header">
      <div>
        <h1 class="title">枢界台 · 会话驾驶舱</h1>
        <p class="subtitle">Hermes / OpenClaw unified cockpit MVP</p>
      </div>
      <div style="display:flex; gap:8px; align-items:center;">
        <select v-model="selectedSessionId" class="refresh" @change="refreshData">
          <option v-for="session in sessions" :key="session.id" :value="session.id">
            {{ session.title }} ({{ session.platform }})
          </option>
        </select>
        <button class="refresh" :disabled="loading" @click="refreshData">{{ loading ? 'Loading...' : 'Refresh' }}</button>
      </div>
    </header>

    <div v-if="errorMessage" class="error">{{ errorMessage }}</div>

    <section class="grid">
      <article class="panel">
        <h2>任务栏</h2>
        <div class="lanes">
          <div class="lane">
            <h3>ToDo</h3>
            <div v-for="task in taskLanes.todo" :key="task.id" class="task">
              <div>{{ task.title }}</div>
              <div class="muted">Priority {{ task.priority }}</div>
            </div>
            <div v-if="taskLanes.todo.length === 0" class="muted">No tasks</div>
          </div>

          <div class="lane">
            <h3>Doing</h3>
            <div v-for="task in taskLanes.doing" :key="task.id" class="task">
              <div>{{ task.title }}</div>
              <div class="muted">Priority {{ task.priority }}</div>
            </div>
            <div v-if="taskLanes.doing.length === 0" class="muted">No tasks</div>
          </div>

          <div class="lane">
            <h3>Done</h3>
            <div v-for="task in taskLanes.done" :key="task.id" class="task">
              <div>{{ task.title }}</div>
              <div class="muted">Priority {{ task.priority }}</div>
            </div>
            <div v-if="taskLanes.done.length === 0" class="muted">No tasks</div>
          </div>
        </div>
      </article>

      <article class="panel">
        <h2>对话时间线</h2>
        <div v-if="timeline.messages?.length === 0" class="muted">No messages</div>
        <div v-for="message in timeline.messages" :key="message.id" class="timeline-item">
          <div class="timeline-role">{{ message.role }} · {{ new Date(message.created_at).toLocaleString() }}</div>
          <div class="timeline-content">{{ message.content }}</div>
        </div>
      </article>

      <article class="panel">
        <h2>状态面板</h2>
        <div class="kv"><span class="muted">Session</span><span>{{ selectedSession?.title || '-' }}</span></div>
        <div class="kv"><span class="muted">Platform</span><span>{{ selectedSession?.platform || '-' }}</span></div>
        <div class="kv"><span class="muted">Messages</span><span>{{ cockpit?.session?.message_count ?? 0 }}</span></div>
        <div class="kv"><span class="muted">Tasks</span><span>{{ cockpit?.session?.task_count ?? 0 }}</span></div>
        <hr style="border-color:#263a58; opacity:0.5;" />
        <div class="kv"><span class="muted">Token In</span><span>{{ cockpit?.metrics?.token_in ?? 0 }}</span></div>
        <div class="kv"><span class="muted">Token Out</span><span>{{ cockpit?.metrics?.token_out ?? 0 }}</span></div>
        <div class="kv"><span class="muted">Latency P50</span><span>{{ cockpit?.metrics?.latency_ms_p50 ?? 0 }} ms</span></div>
        <div class="kv"><span class="muted">Errors</span><span>{{ cockpit?.metrics?.error_count ?? 0 }}</span></div>
      </article>
    </section>
  </main>
</template>
