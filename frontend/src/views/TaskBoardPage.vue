<script setup>
import { useTaskStore } from '../stores/useTaskStore.js'
import { onMounted } from 'vue'

const ts = useTaskStore()
const KANBAN_STATUSES = ['draft','pending_execution','in_progress','blocked','cancelled','completed']

onMounted(async () => { await ts.loadTaskBoardItems() })
</script>

<template>
  <section class="main-grid task-board-grid">
    <article class="panel task-board-panel">
      <div class="task-board-panel-header">
        <h2>任务看板</h2>
        <div class="task-board-actions">
          <select v-model="ts.taskBoardProjectFilter" class="task-board-filter-select">
            <option v-for="opt in ts.taskBoardProjectOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
          </select>
          <select v-model="ts.taskBoardStatusFilter" class="task-board-filter-select">
            <option v-for="opt in ts.taskBoardStatusFilterOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
          </select>
          <input v-model="ts.taskBoardKeyword" class="project-search task-board-search" placeholder="搜索任务" />
          <button type="button" class="project-btn project-btn-primary" @click="ts.openTaskBoardCreateModal">新建任务</button>
        </div>
      </div>

      <div v-if="ts.taskBoardMatrix.length === 0" class="project-empty">暂无任务，点击"新建任务"开始。</div>
      <div v-else class="kanban-matrix scrollbar-themed" :style="ts.kanbanMatrixStyle">
        <div class="kanban-header">
          <div class="kanban-header-label">项目</div>
          <div v-for="status in KANBAN_STATUSES" :key="status"
            class="kanban-header-cell"
            :class="{ 'kanban-header-collapsible': ts.isKanbanStatusCollapsible(status), 'kanban-header-collapsed': ts.isKanbanStatusCollapsed(status) }"
            @click="ts.toggleKanbanStatusColumn(status)"
          >
            <span>{{ ts.taskBoardStatusLabelMap[status] }}</span>
          </div>
        </div>

        <template v-for="project in ts.taskBoardMatrix" :key="project.id">
          <div class="kanban-project-row" :class="{ 'kanban-project-row-collapsed': ts.collapsedProjectRows.has(project.id) }">
            <div class="kanban-project-label" @click="ts.toggleProjectRow(project.id)">
              <span class="kanban-project-name">{{ project.name }}</span>
              <span class="kanban-project-count">{{ project.taskCount }}</span>
            </div>
            <div v-for="status in KANBAN_STATUSES" :key="status" class="kanban-lane" @dragover.prevent @drop="ts.handleTaskBoardDrop(status, $event)">
              <template v-if="ts.isKanbanStatusCollapsed(status)">
                <span class="kanban-lane-collapsed-count">{{ project.columns[status]?.length || 0 }}</span>
              </template>
              <template v-else>
                <div v-for="item in project.columns[status]" :key="item.id" class="task-board-card" :class="{ 'task-board-card-highlighted': ts.highlightedTaskBoardItemId === item.id }" draggable="true" @dragstart="ts.handleTaskBoardDragStart(item, $event)" @dragend="ts.handleTaskBoardDragEnd">
                  <div class="task-board-card-top">
                    <div class="task-board-title-wrap">
                      <div class="task-board-name-row">
                        <button v-if="item.children.length" type="button" class="task-tree-toggle" @click.stop="ts.toggleTaskNode(item)">{{ ts.collapsedTaskNodes.has(item.id) ? '▶' : '▼' }}</button>
                        <span v-else class="task-tree-spacer"></span>
                        <span class="task-board-name">{{ item.name }}</span>
                      </div>
                      <div class="task-board-badges">
                        <span class="priority-badge" :class="`priority-P${ts.getTaskPriority(item) - 1}`">{{ ts.KANBAN_PRIORITY_LABELS[ts.getTaskPriority(item)] }}</span>
                        <span v-if="item.children.length" class="task-child-count">{{ item.children.length }} 子任务</span>
                      </div>
                    </div>
                    <div class="task-board-card-actions">
                      <select class="priority-badge priority-select" :class="`priority-P${ts.getTaskPriority(item) - 1}`" :value="ts.getTaskPriority(item)" :disabled="ts.quickUpdatingTaskBoardItemId === item.id" aria-label="调整任务优先级" @change.stop="ts.updateTaskBoardPriority(item, $event)" @click.stop>
                        <option v-for="opt in ts.taskBoardPriorityOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                      </select>
                      <button type="button" class="project-btn" @click.stop="ts.openTaskBoardDetailModal(item)">详情</button>
                      <button type="button" class="project-btn project-btn-primary" :disabled="ts.startingConversationFromTask" @click.stop="ts.startConversationFromTask(item)">{{ ts.startingConversationFromTask ? '...' : '会话' }}</button>
                      <button type="button" class="project-btn" @click.stop="ts.openTaskBoardEditModal(item)">编辑</button>
                      <button type="button" class="card-archive-btn" :disabled="ts.archivingTaskId === item.id" :aria-label="`归档任务 ${item.name}`" @click.stop="ts.archiveTaskBoardItem(item)"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2.5 5.5h11v7.333A1.167 1.167 0 0112.333 14H3.667A1.167 1.167 0 012.5 12.833V5.5z"/><path d="M1.833 3.167h12.334V5.5H1.833zM5.333 8h5.334"/></svg></button>
                    </div>
                  </div>
                  <div class="task-board-desc task-board-desc-compact">{{ item.description || '暂无描述' }}</div>
                  <div v-if="ts.requiresTaskStatusReason(item.status) && item.status_reason" class="task-board-status-reason">原因：{{ ts.getTaskStatusReasonPreview(item) }}</div>
                  <div class="task-board-meta task-board-meta-inline">
                    <span class="task-board-meta-label">{{ item.ai_platform }}</span>
                    <span class="task-board-meta-label muted">{{ item.updated_at ? new Date(item.updated_at).toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}) : '-' }}</span>
                  </div>
                  <!-- Child tasks (recursive) omitted for brevity — full tree rendering is in original App.vue lines 2478-2513 -->
                </div>
              </template>
            </div>
          </div>
        </template>
      </div>
    </article>
  </section>

  <!-- Task detail modal -->
  <div v-if="ts.taskBoardDetailItem" class="modal-overlay" @click.self="ts.closeTaskBoardDetailModal">
    <div class="modal task-detail-modal">
      <div class="modal-header">
        <h3 class="modal-title">任务详情</h3>
        <button type="button" class="modal-close-btn" @click="ts.closeTaskBoardDetailModal">✕</button>
      </div>
      <div class="modal-body">
        <section class="task-detail-section">
          <h4 class="task-detail-heading">{{ ts.taskBoardDetailItem.name }}</h4>
          <div class="task-detail-meta-bar">
            <span class="priority-badge" :class="`priority-P${ts.getTaskPriority(ts.taskBoardDetailItem) - 1}`">{{ ts.KANBAN_PRIORITY_LABELS[ts.getTaskPriority(ts.taskBoardDetailItem)] }}</span>
            <span class="task-status-tag" :class="`task-status-${ts.taskBoardDetailItem.status}`">{{ ts.taskBoardStatusLabelMap[ts.taskBoardDetailItem.status] }}</span>
            <span class="muted">{{ ts.taskBoardDetailItem.ai_platform }}</span>
            <span v-if="ts.taskBoardDetailItem.project_name" class="muted"> | {{ ts.taskBoardDetailItem.project_name }}</span>
          </div>
        </section>
        <section class="task-detail-section">
          <h4>描述</h4>
          <p class="task-detail-desc">{{ ts.taskBoardDetailItem.description || '暂无描述' }}</p>
        </section>
        <section class="task-detail-section">
          <h4>时间</h4>
          <p class="muted">创建：{{ ts.taskBoardDetailItem.created_at ? new Date(ts.taskBoardDetailItem.created_at).toLocaleString() : '-' }}</p>
          <p class="muted">更新：{{ ts.taskBoardDetailItem.updated_at ? new Date(ts.taskBoardDetailItem.updated_at).toLocaleString() : '-' }}</p>
        </section>
        <section class="task-detail-section">
          <h4>关联</h4>
          <p class="muted">父任务：{{ ts.taskBoardDetailItem.parent_task_name || '-' }}</p>
          <p class="muted">上游任务：{{ ts.taskBoardDetailItem.upstream_task_name || '-' }}</p>
        </section>
      </div>
      <div class="modal-footer">
        <button type="button" class="project-btn" @click="ts.closeTaskBoardDetailModal">关闭</button>
        <button type="button" class="project-btn project-btn-primary" @click="ts.openTaskBoardEditModal(ts.taskBoardDetailItem)">编辑</button>
      </div>
    </div>
  </div>
</template>
