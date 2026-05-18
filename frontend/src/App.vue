<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useSessionStore } from './stores/useSessionStore.js'
import { useTaskStore } from './stores/useTaskStore.js'
import { useProjectStore } from './stores/useProjectStore.js'
import { useConfigStore } from './stores/useConfigStore.js'

import ChatPage from './views/ChatPage.vue'
import ProjectsPage from './views/ProjectsPage.vue'
import TaskBoardPage from './views/TaskBoardPage.vue'
import TaskArchivePage from './views/TaskArchivePage.vue'
import ModelConfigPage from './views/ModelConfigPage.vue'
import SystemConfigPage from './views/SystemConfigPage.vue'
import DispatchHistoryPage from './views/DispatchHistoryPage.vue'
import SkillsCatalogPage from './views/SkillsCatalogPage.vue'

import CreateConversationModal from './components/modals/CreateConversationModal.vue'
import ProjectCreateModal from './components/modals/ProjectCreateModal.vue'
import ProjectEditModal from './components/modals/ProjectEditModal.vue'
import ModelModal from './components/modals/ModelModal.vue'
import SkillModal from './components/modals/SkillModal.vue'
import McpModal from './components/modals/McpModal.vue'
import TaskBoardCreateModal from './components/modals/TaskBoardCreateModal.vue'
import TaskBoardEditModal from './components/modals/TaskBoardEditModal.vue'

const ss = useSessionStore()
const ts = useTaskStore()
const ps = useProjectStore()
const cs = useConfigStore()

const activePage = ref('chat')

function switchToTaskArchive() { activePage.value = 'task-archive'; ts.loadArchivedTasks() }
function switchToSystemConfig() { activePage.value = 'system-config' }
function switchToDispatchHistory() { activePage.value = 'dispatch-history' }
function switchToSkillsCatalog() { activePage.value = 'skills-catalog' }

function openTaskBoardByProject(project) { ts.openTaskBoardByProject(project); activePage.value = 'task-board' }

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

defineExpose({ activePage })
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
          <button type="button" class="top-nav-btn" :class="{ 'top-nav-btn-active': activePage === 'task-archive' }" @click="switchToTaskArchive">
            <span class="top-nav-btn-icon" aria-hidden="true">📦</span>
            <span class="top-nav-btn-label">归档任务</span>
          </button>
          <button type="button" class="top-nav-btn" :class="{ 'top-nav-btn-active': activePage === 'model-config' }" @click="activePage = 'model-config'">
            <span class="top-nav-btn-icon" aria-hidden="true">🤖</span>
            <span class="top-nav-btn-label">模型配置</span>
          </button>
          <button type="button" class="top-nav-btn" :class="{ 'top-nav-btn-active': activePage === 'skills-catalog' }" @click="switchToSkillsCatalog">
            <span class="top-nav-btn-icon" aria-hidden="true">🧩</span>
            <span class="top-nav-btn-label">Skills 库</span>
          </button>
          <button type="button" class="top-nav-btn" :class="{ 'top-nav-btn-active': activePage === 'system-config' }" @click="switchToSystemConfig">
            <span class="top-nav-btn-icon" aria-hidden="true">⚙️</span>
            <span class="top-nav-btn-label">系统配置</span>
          </button>
          <button type="button" class="top-nav-btn" :class="{ 'top-nav-btn-active': activePage === 'dispatch-history' }" @click="switchToDispatchHistory">
            <span class="top-nav-btn-icon" aria-hidden="true">📋</span>
            <span class="top-nav-btn-label">调度历史</span>
          </button>
        </nav>
      </header>

      <div v-if="ss.errorMessage" class="error panel">{{ ss.errorMessage }}</div>

      <ChatPage v-if="activePage === 'chat'" />
      <ProjectsPage v-else-if="activePage === 'projects'" @openTaskBoard="openTaskBoardByProject" />
      <TaskBoardPage v-else-if="activePage === 'task-board'" />
      <TaskArchivePage v-else-if="activePage === 'task-archive'" />
      <ModelConfigPage v-else-if="activePage === 'model-config'" />
      <SystemConfigPage v-else-if="activePage === 'system-config'" />
      <DispatchHistoryPage v-else-if="activePage === 'dispatch-history'" />
      <SkillsCatalogPage v-else-if="activePage === 'skills-catalog'" />
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
