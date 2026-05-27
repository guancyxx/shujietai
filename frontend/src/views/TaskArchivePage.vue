<script setup>
import { useTaskStore } from '../stores/useTaskStore.js'
import { useMarkdownRenderer } from '../composables/useMarkdownRenderer.js'

const ts = useTaskStore()
const { renderMarkdown } = useMarkdownRenderer()
</script>

<template>
  <section class="main-grid task-board-grid">
    <article class="panel task-board-panel">
      <div class="task-board-panel-header">
        <h2>归档任务</h2>
        <div class="task-board-actions">
          <select v-model="ts.archiveProjectFilter" class="task-board-filter-select" @change="ts.loadArchivedTasks">
            <option value="">全部项目</option>
            <option v-for="opt in ts.taskBoardProjectOptions.filter(o => o.value)" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
          </select>
          <select v-model="ts.archiveStatusFilter" class="task-board-filter-select" @change="ts.loadArchivedTasks">
            <option value="">全部状态</option>
            <option value="completed">已完成</option>
            <option value="cancelled">取消</option>
          </select>
          <input v-model="ts.archiveKeyword" class="project-search task-board-search" placeholder="搜索归档任务" @input="ts.loadArchivedTasks" />
        </div>
      </div>

      <div v-if="ts.archiveLoading" class="project-empty">加载中...</div>
      <div v-else-if="ts.archivedTaskItems.length === 0" class="project-empty">暂无归档任务。</div>
      <div v-else class="archive-list scrollbar-themed">
        <div v-for="item in ts.archivedTaskItems" :key="item.id" class="task-board-card">
          <div class="task-board-card-top">
            <div class="task-board-card-actions">
              <button type="button" class="project-btn" @click.stop="ts.archiveDetailItem = item; ts.isArchiveDetailOpen = true">详情</button>
              <button type="button" class="project-btn project-btn-primary" :disabled="ts.unarchivingTaskId === item.id" @click.stop="ts.unarchiveTaskBoardItem(item)">{{ ts.unarchivingTaskId === item.id ? '...' : '恢复' }}</button>
            </div>
            <div class="task-board-title-wrap">
              <div class="task-board-name-row">
                <span class="task-board-name">{{ item.name }}</span>
              </div>
              <div class="task-board-badges">
                <span class="priority-badge" :class="`priority-P${ts.getTaskPriority(item) - 1}`">{{ ts.KANBAN_PRIORITY_LABELS[ts.getTaskPriority(item)] }}</span>
                <span class="task-status-tag" :class="`task-status-${item.status}`">{{ ts.taskBoardStatusLabelMap[item.status] }}</span>
                <span v-if="item.project_name" class="task-board-meta-label muted">{{ item.project_name }}</span>
              </div>
            </div>
          </div>
          <div class="task-board-desc task-board-desc-compact">{{ item.description || '暂无描述' }}</div>
          <div class="task-board-meta task-board-meta-inline">
            <span class="task-board-meta-label">{{ item.ai_platform }}</span>
            <span class="task-board-meta-label muted">归档于 {{ item.archived_at ? new Date(item.archived_at).toLocaleString() : '-' }}</span>
          </div>
        </div>
      </div>
    </article>
  </section>

  <!-- Archive detail modal -->
  <div v-if="ts.isArchiveDetailOpen" class="modal-overlay" @click.self="ts.isArchiveDetailOpen = false; ts.archiveDetailItem = null">
    <div class="modal task-detail-modal">
      <div class="modal-header">
        <h3 class="modal-title">任务详情</h3>
        <button type="button" class="modal-close-btn" @click="ts.isArchiveDetailOpen = false; ts.archiveDetailItem = null">✕</button>
      </div>
      <div v-if="ts.archiveDetailItem" class="modal-body">
        <section class="task-detail-section">
          <h4 class="task-detail-heading">{{ ts.archiveDetailItem.name }}</h4>
          <div class="task-detail-meta-bar">
            <span class="priority-badge" :class="`priority-P${ts.getTaskPriority(ts.archiveDetailItem) - 1}`">{{ ts.KANBAN_PRIORITY_LABELS[ts.getTaskPriority(ts.archiveDetailItem)] }}</span>
            <span class="task-status-tag" :class="`task-status-${ts.archiveDetailItem.status}`">{{ ts.taskBoardStatusLabelMap[ts.archiveDetailItem.status] }}</span>
            <span class="muted">{{ ts.archiveDetailItem.ai_platform }}</span>
            <span v-if="ts.archiveDetailItem.project_name" class="muted"> | {{ ts.archiveDetailItem.project_name }}</span>
          </div>
        </section>
        <section class="task-detail-section">
          <h4>描述</h4>
          <p class="task-detail-desc" v-html="renderMarkdown(ts.archiveDetailItem.description || '暂无描述')"></p>
        </section>
        <section class="task-detail-section">
          <h4>时间</h4>
          <p class="muted">创建：{{ ts.archiveDetailItem.created_at ? new Date(ts.archiveDetailItem.created_at).toLocaleString() : '-' }}</p>
          <p class="muted">更新：{{ ts.archiveDetailItem.updated_at ? new Date(ts.archiveDetailItem.updated_at).toLocaleString() : '-' }}</p>
          <p class="muted">归档：{{ ts.archiveDetailItem.archived_at ? new Date(ts.archiveDetailItem.archived_at).toLocaleString() : '-' }}</p>
        </section>
      </div>
      <div class="modal-footer">
        <button type="button" class="project-btn project-btn-primary" @click="ts.unarchiveTaskBoardItem(ts.archiveDetailItem); ts.isArchiveDetailOpen = false; ts.archiveDetailItem = null">恢复至看板</button>
        <button type="button" class="project-btn" @click="ts.isArchiveDetailOpen = false; ts.archiveDetailItem = null">关闭</button>
      </div>
    </div>
  </div>
</template>
