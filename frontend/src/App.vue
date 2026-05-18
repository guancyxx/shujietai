<script setup>
import { onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useSessionStore } from './stores/useSessionStore.js'
import { useTaskStore } from './stores/useTaskStore.js'
import { useProjectStore } from './stores/useProjectStore.js'
import { useConfigStore } from './stores/useConfigStore.js'

import CreateConversationModal from './components/modals/CreateConversationModal.vue'
import ProjectCreateModal from './components/modals/ProjectCreateModal.vue'
import ProjectEditModal from './components/modals/ProjectEditModal.vue'
import ModelModal from './components/modals/ModelModal.vue'
import SkillModal from './components/modals/SkillModal.vue'
import McpModal from './components/modals/McpModal.vue'
import TaskBoardCreateModal from './components/modals/TaskBoardCreateModal.vue'
import TaskBoardEditModal from './components/modals/TaskBoardEditModal.vue'

const router = useRouter()
const route = useRoute()

const ss = useSessionStore()
const ts = useTaskStore()
const ps = useProjectStore()
const cs = useConfigStore()

function switchToTaskArchive() {
  router.push('/task-archive')
  ts.loadArchivedTasks()
}

function openTaskBoardByProject(_project) {
  ts.openTaskBoardByProject(_project)
  router.push('/task-board')
}

onMounted(async () => {
  ss.wsConnect()
  ss.errorMessage = ''
  try {
    await Promise.all([ss.loadSessions(), ps.loadProjects(), ts.loadTaskBoardItems(), ps.loadGithubRepos(), cs.loadSystemConfig()])
    await ss.loadSessionData()
    await ss.restoreActiveDispatchTask()
  } catch (error) {
    ss.errorMessage = error instanceof Error ? error.message : 'Unknown error'
  }
})

onUnmounted(() => { ss.clearActiveTask() })
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
          <router-link to="/" class="top-nav-btn" :class="{ 'top-nav-btn-active': route.name === 'chat' }">
            <span class="top-nav-btn-icon" aria-hidden="true">💬</span>
            <span class="top-nav-btn-label">会话中心</span>
          </router-link>
          <router-link to="/projects" class="top-nav-btn" :class="{ 'top-nav-btn-active': route.name === 'projects' }">
            <span class="top-nav-btn-icon" aria-hidden="true">📁</span>
            <span class="top-nav-btn-label">项目管理</span>
          </router-link>
          <router-link to="/task-board" class="top-nav-btn" :class="{ 'top-nav-btn-active': route.name === 'task-board' }">
            <span class="top-nav-btn-icon" aria-hidden="true">🗂️</span>
            <span class="top-nav-btn-label">任务看板</span>
          </router-link>
          <router-link to="/task-archive" class="top-nav-btn" :class="{ 'top-nav-btn-active': route.name === 'task-archive' }" @click="switchToTaskArchive">
            <span class="top-nav-btn-icon" aria-hidden="true">📦</span>
            <span class="top-nav-btn-label">归档任务</span>
          </router-link>
          <router-link to="/model-config" class="top-nav-btn" :class="{ 'top-nav-btn-active': route.name === 'model-config' }">
            <span class="top-nav-btn-icon" aria-hidden="true">🤖</span>
            <span class="top-nav-btn-label">模型配置</span>
          </router-link>
          <router-link to="/skills-catalog" class="top-nav-btn" :class="{ 'top-nav-btn-active': route.name === 'skills-catalog' }">
            <span class="top-nav-btn-icon" aria-hidden="true">🧩</span>
            <span class="top-nav-btn-label">Skills 库</span>
          </router-link>
          <router-link to="/system-config" class="top-nav-btn" :class="{ 'top-nav-btn-active': route.name === 'system-config' }">
            <span class="top-nav-btn-icon" aria-hidden="true">⚙️</span>
            <span class="top-nav-btn-label">系统配置</span>
          </router-link>
          <router-link to="/dispatch-history" class="top-nav-btn" :class="{ 'top-nav-btn-active': route.name === 'dispatch-history' }">
            <span class="top-nav-btn-icon" aria-hidden="true">📋</span>
            <span class="top-nav-btn-label">调度历史</span>
          </router-link>
        </nav>
      </header>

      <div v-if="ss.errorMessage" class="error panel">{{ ss.errorMessage }}</div>

      <router-view />
    </section>

    <!-- Global modals -->
    <CreateConversationModal />
    <ProjectCreateModal />
    <ProjectEditModal />
    <ModelModal />
    <SkillModal />
    <McpModal />
    <TaskBoardCreateModal />
    <TaskBoardEditModal />
  </main>
</template>
