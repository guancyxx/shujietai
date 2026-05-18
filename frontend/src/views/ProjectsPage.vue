<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectStore } from '../stores/useProjectStore.js'
import { useTaskStore } from '../stores/useTaskStore.js'

const router = useRouter()
const ps = useProjectStore()
const ts = useTaskStore()
const activeProjectTab = ref('')

function toggleProjectTab(id) {
  activeProjectTab.value = activeProjectTab.value === id ? '' : id
}

function openTaskBoard(project) {
  ts.openTaskBoardByProject(project)
  router.push('/task-board')
}
</script>

<template>
  <section class="main-grid project-grid">
    <article class="panel project-panel">
      <div class="project-panel-header">
        <h2>{{ ps.filteredProjects.length > 0 ? '项目' : '没有项目' }}</h2>
        <div class="project-header-actions">
          <input v-model="ps.projectSearch" class="project-search" placeholder="搜索项目" />
          <button type="button" class="project-btn project-btn-primary" @click="ps.openProjectCreateModal">新建项目</button>
        </div>
      </div>

      <div class="project-list scrollbar-themed">
        <div v-for="item in ps.filteredProjects" :key="item.id" class="project-card">
          <div class="project-card-head" @click="toggleProjectTab(item.id)">
            <div class="project-card-title-row">
              <span class="project-card-code">{{ item.code }}</span>
              <span class="project-card-name">{{ item.name }}</span>
            </div>
            <span class="project-card-toggle">{{ activeProjectTab === item.id ? '▲' : '▼' }}</span>
          </div>
          <div v-if="item.description" class="project-card-desc">{{ item.description }}</div>
          <div class="project-card-meta">
            <span v-if="item.repository_name">{{ item.repository_name }}</span>
            <a v-if="item.repository_url" :href="item.repository_url" target="_blank" class="project-card-repo-link">{{ item.repository_url }}</a>
          </div>
          <div v-if="activeProjectTab === item.id" class="project-card-actions">
            <button type="button" class="project-btn" @click="ps.openProjectEditModal(item)">编辑</button>
            <button type="button" class="project-btn" @click="ps.deleteProject(item)">删除</button>
            <button type="button" class="project-btn project-btn-primary" @click="openTaskBoard(item)">任务看板</button>
          </div>
        </div>
      </div>
    </article>
  </section>
</template>
