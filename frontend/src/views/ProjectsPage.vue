<script setup>
import { useRouter } from 'vue-router'
import { useProjectStore } from '../stores/useProjectStore.js'
import { useTaskStore } from '../stores/useTaskStore.js'

const router = useRouter()
const ps = useProjectStore()
const ts = useTaskStore()

function openTaskBoardByProject(project) {
  ts.openTaskBoardByProject(project)
  router.push('/task-board')
}
</script>

<template>
  <section class="main-grid project-grid">
    <article class="panel project-panel">
      <div class="project-panel-header">
        <h2>项目管理</h2>
        <div class="project-actions">
          <input v-model="ps.projectSearch" class="project-search" placeholder="搜索项目名称/编号/仓库" />
          <button type="button" class="session-new-btn" @click="ps.openProjectCreateModal">新建项目</button>
        </div>
      </div>

      <div class="project-list scrollbar-themed" v-if="ps.filteredProjects.length > 0">
        <div v-for="item in ps.filteredProjects" :key="item.id" class="project-card project-card-clickable" @click="openTaskBoardByProject(item)">
          <div class="project-card-top">
            <div class="project-title-wrap">
              <div class="project-name">{{ item.name }}</div>
              <div class="project-code">{{ item.code }}</div>
            </div>
            <div class="project-card-actions">
              <button type="button" class="project-btn" @click.stop="ps.openProjectEditModal(item)">编辑</button>
              <button type="button" class="card-delete-btn" :disabled="ps.deletingProjectId === item.id" :aria-label="`删除项目 ${item.name}`" @click.stop="ps.deleteProject(item)">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 4h12M5.333 4V2.667a1.333 1.333 0 011.334-1.334h2.666a1.333 1.333 0 011.334 1.334V4m2 0v9.333a1.333 1.333 0 01-1.334 1.334H4.667a1.333 1.333 0 01-1.334-1.334V4h9.334zM6.667 7.333v4M9.333 7.333v4"/></svg>
              </button>
            </div>
          </div>
          <div class="project-desc">{{ item.description || '暂无简介' }}</div>
          <div class="project-meta">
            <span class="project-meta-label">仓库</span>
            <span class="project-meta-value">{{ item.repository_name }}</span>
          </div>
          <div class="project-meta">
            <span class="project-meta-label">更新时间</span>
            <span class="project-meta-value">{{ item.updated_at ? new Date(item.updated_at).toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}) : '-' }}</span>
          </div>
        </div>
      </div>
      <div v-else class="project-empty">暂无项目，点击"新建项目"开始。</div>
    </article>
  </section>
</template>
