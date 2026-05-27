<script setup>
import { useTaskStore } from '../stores/useTaskStore.js'
import { useMarkdownRenderer } from '../composables/useMarkdownRenderer.js'
import { onMounted } from 'vue'

const ts = useTaskStore()
const { renderMarkdown } = useMarkdownRenderer()
const KANBAN_STATUSES = ['draft', 'pending_execution', 'in_progress', 'blocked', 'cancelled', 'completed']

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
          <input v-model="ts.taskBoardKeyword" class="project-search task-board-search" placeholder="搜索任务名称/描述" />
          <button type="button" class="session-new-btn" @click="ts.openTaskBoardCreateModal">新建任务</button>
        </div>
      </div>

      <!-- Matrix Kanban: columns=statuses, rows=projects; cards render parent/child task trees -->
      <div class="kanban-matrix-wrap scrollbar-themed">
        <div class="kanban-matrix-header" :style="ts.kanbanMatrixStyle">
          <div class="kanban-row-label-head">项目</div>
          <div v-for="s in KANBAN_STATUSES" :key="s" class="kanban-col-header" :class="['kanban-col-' + s, { 'kanban-col-collapsed': ts.isKanbanStatusCollapsed(s) }]">
            <span class="kanban-status-dot" :class="'task-status-' + s"></span>
            <span class="kanban-col-title">{{ ts.taskBoardStatusLabelMap[s] }}</span>
            <button
              v-if="ts.isKanbanStatusCollapsible(s)"
              type="button"
              class="kanban-col-toggle"
              :aria-label="ts.isKanbanStatusCollapsed(s) ? '展开已完成列' : '折叠已完成列'"
              :title="ts.isKanbanStatusCollapsed(s) ? '展开已完成列' : '折叠已完成列'"
              @click.stop="ts.toggleKanbanStatusColumn(s)"
            >
              {{ ts.isKanbanStatusCollapsed(s) ? '◀' : '▶' }}
            </button>
          </div>
        </div>
        <template v-if="ts.taskBoardMatrix.length > 0">
          <template v-for="project in ts.taskBoardMatrix" :key="project.id">
            <div class="kanban-project-row kanban-project-l1">
              <button type="button" class="kanban-row-header" @click="ts.toggleProjectRow(project.id)">
                <span class="kanban-collapse-icon">{{ ts.collapsedProjectRows.has(project.id) ? '▶' : '▼' }}</span>
                <span class="kanban-project-name">{{ project.name }}</span>
                <span class="kanban-project-count muted">{{ project.taskCount }} 项</span>
              </button>
            </div>
            <div v-if="!ts.collapsedProjectRows.has(project.id)" class="kanban-row-columns" :style="ts.kanbanMatrixStyle">
              <div class="kanban-row-spacer"></div>
              <div
                v-for="s in KANBAN_STATUSES"
                :key="s"
                class="kanban-cell"
                :class="{ 'kanban-cell-drop-active': ts.draggingTaskBoardItemId && !ts.isKanbanStatusCollapsed(s), 'kanban-cell-collapsed': ts.isKanbanStatusCollapsed(s) }"
                @dragover.prevent="!ts.isKanbanStatusCollapsed(s)"
                @drop.prevent="!ts.isKanbanStatusCollapsed(s) && ts.handleTaskBoardDrop(s, $event)"
              >
                <button
                  v-if="ts.isKanbanStatusCollapsed(s)"
                  type="button"
                  class="kanban-collapsed-summary"
                  :aria-label="`展开${ts.taskBoardStatusLabelMap[s]}列`"
                  :title="`展开${ts.taskBoardStatusLabelMap[s]}列`"
                  @click="ts.toggleKanbanStatusColumn(s)"
                >
                  <span class="kanban-collapsed-count">{{ project.columns[s] ? project.columns[s].length : 0 }}</span>
                  <span class="kanban-collapsed-label">项</span>
                </button>
                <template v-else>
                  <div v-if="!project.columns[s] || project.columns[s].length === 0" class="kanban-cell-empty">拖到这里</div>
                  <template v-for="item in project.columns[s]" :key="item.id">
                    <div
                      class="task-board-card"
                      :class="{ 'task-board-card-dragging': ts.draggingTaskBoardItemId === item.id, 'task-board-card-highlighted': ts.highlightedTaskBoardItemId === item.id }"
                      draggable="true"
                      @dragstart="ts.handleTaskBoardDragStart(item, $event)"
                      @dragend="ts.handleTaskBoardDragEnd"
                    >
                      <div class="task-board-card-top">
                        <div class="task-board-card-actions">
                          <select class="priority-badge priority-select" :class="`priority-P${ts.getTaskPriority(item) - 1}`" :value="ts.getTaskPriority(item)" :disabled="ts.quickUpdatingTaskBoardItemId === item.id" aria-label="调整任务优先级" @change.stop="ts.updateTaskBoardPriority(item, $event)" @click.stop>
                            <option v-for="opt in ts.taskBoardPriorityOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                          </select>
                          <button type="button" class="project-btn" @click.stop="ts.openTaskBoardDetailModal(item)">详情</button>
                          <button type="button" class="project-btn project-btn-primary" :disabled="ts.startingConversationFromTask" @click.stop="ts.startConversationFromTask(item)">{{ ts.startingConversationFromTask ? '...' : '会话' }}</button>
                          <button type="button" class="project-btn" @click.stop="ts.openTaskBoardEditModal(item)">编辑</button>
                          <button type="button" class="card-archive-btn" :disabled="ts.archivingTaskId === item.id" :aria-label="`归档任务 ${item.name}`" @click.stop="ts.archiveTaskBoardItem(item)"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2.5 5.5h11v7.333A1.167 1.167 0 0112.333 14H3.667A1.167 1.167 0 012.5 12.833V5.5z"/><path d="M1.833 3.167h12.334V5.5H1.833zM5.333 8h5.334"/></svg></button>
                        </div>
                        <div class="task-board-title-wrap">
                          <div class="task-board-name-row">
                            <button v-if="item.children && item.children.length" type="button" class="task-tree-toggle" @click.stop="ts.toggleTaskNode(item)">{{ ts.collapsedTaskNodes.has(item.id) ? '▶' : '▼' }}</button>
                            <span v-else class="task-tree-spacer"></span>
                            <span class="task-board-name">{{ item.name }}</span>
                          </div>
                          <div class="task-board-badges">
                            <span class="priority-badge" :class="`priority-P${ts.getTaskPriority(item) - 1}`">{{ ts.KANBAN_PRIORITY_LABELS[ts.getTaskPriority(item)] }}</span>
                            <span v-if="item.children && item.children.length" class="task-child-count">{{ item.children.length }} 子任务</span>
                          </div>
                        </div>
                      </div>
                      <div class="task-board-desc task-board-desc-compact">{{ item.description || '暂无描述' }}</div>
                      <div v-if="ts.requiresTaskStatusReason(item.status) && item.status_reason" class="task-board-status-reason">
                        原因：{{ ts.getTaskStatusReasonPreview(item) }}
                      </div>
                      <div class="task-board-meta task-board-meta-inline">
                        <span class="task-board-meta-label">{{ item.ai_platform }}</span>
                        <span class="task-board-meta-label muted">{{ item.updated_at ? new Date(item.updated_at).toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}) : '-' }}</span>
                      </div>
                      <!-- Child tasks -->
                      <div v-if="item.children && item.children.length && !ts.collapsedTaskNodes.has(item.id)" class="task-tree-children">
                        <template v-for="child in item.children" :key="child.id">
                          <div class="task-board-card task-board-card-child" :class="{ 'task-board-card-highlighted': ts.highlightedTaskBoardItemId === child.id }" draggable="true" @dragstart="ts.handleTaskBoardDragStart(child, $event)" @dragend="ts.handleTaskBoardDragEnd">
                            <div class="task-board-card-top">
                              <div class="task-board-card-actions"><button type="button" class="project-btn" @click.stop="ts.openTaskBoardDetailModal(child)">详情</button><button type="button" class="project-btn" @click.stop="ts.openTaskBoardEditModal(child)">编辑</button><button type="button" class="card-archive-btn" :disabled="ts.archivingTaskId === child.id" :aria-label="`归档任务 ${child.name}`" @click.stop="ts.archiveTaskBoardItem(child)"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2.5 5.5h11v7.333A1.167 1.167 0 0112.333 14H3.667A1.167 1.167 0 012.5 12.833V5.5z"/><path d="M1.833 3.167h12.334V5.5H1.833zM5.333 8h5.334"/></svg></button></div>
                              <div class="task-board-title-wrap">
                                <div class="task-board-name-row">
                                  <button v-if="child.children && child.children.length" type="button" class="task-tree-toggle" @click.stop="ts.toggleTaskNode(child)">{{ ts.collapsedTaskNodes.has(child.id) ? '▶' : '▼' }}</button>
                                  <span v-else class="task-tree-spacer"></span>
                                  <span class="task-board-name">{{ child.name }}</span>
                                </div>
                                <div class="task-board-badges">
                                  <span class="priority-badge" :class="`priority-P${ts.getTaskPriority(child) - 1}`">{{ ts.KANBAN_PRIORITY_LABELS[ts.getTaskPriority(child)] }}</span>
                                  <span v-if="child.children && child.children.length" class="task-child-count">{{ child.children.length }} 子任务</span>
                                </div>
                              </div>
                            </div>
                            <div class="task-board-desc task-board-desc-compact">{{ child.description || '暂无描述' }}</div>
                            <div v-if="ts.requiresTaskStatusReason(child.status) && child.status_reason" class="task-board-status-reason">
                              原因：{{ ts.getTaskStatusReasonPreview(child) }}
                            </div>
                            <!-- Grandchild tasks -->
                            <div v-if="child.children && child.children.length && !ts.collapsedTaskNodes.has(child.id)" class="task-tree-children">
                              <template v-for="grandchild in child.children" :key="grandchild.id">
                                <div class="task-board-card task-board-card-child task-board-card-grandchild" :class="{ 'task-board-card-highlighted': ts.highlightedTaskBoardItemId === grandchild.id }">
                                  <div class="task-board-card-top">
                                    <div class="task-board-card-actions"><button type="button" class="project-btn" @click.stop="ts.openTaskBoardDetailModal(grandchild)">详情</button><button type="button" class="project-btn" @click.stop="ts.openTaskBoardEditModal(grandchild)">编辑</button></div>
                                    <div class="task-board-title-wrap">
                                      <div class="task-board-name-row">
                                        <span class="task-tree-spacer"></span>
                                        <span class="task-board-name">{{ grandchild.name }}</span>
                                      </div>
                                    </div>
                                  </div>
                                  <div class="task-board-desc task-board-desc-compact">{{ grandchild.description || '暂无描述' }}</div>
                                </div>
                              </template>
                            </div>
                          </div>
                        </template>
                      </div>
                    </div>
                  </template>
                </template>
              </div>
            </div>
          </template>
        </template>
        <div v-else class="project-empty">暂无任务，点击"新建任务"开始。</div>
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
          <h4>{{ ts.taskBoardDetailItem.name }}</h4>
          <div class="task-detail-subtitle">
            <span class="priority-badge" :class="`priority-P${ts.getTaskPriority(ts.taskBoardDetailItem) - 1}`">{{ ts.KANBAN_PRIORITY_LABELS[ts.getTaskPriority(ts.taskBoardDetailItem)] }}</span>
            <span class="task-board-status-pill" :class="ts.taskBoardStatusClass(ts.taskBoardDetailItem.status)">{{ ts.taskBoardStatusLabelMap[ts.taskBoardDetailItem.status] }}</span>
            <span class="muted">{{ ts.taskBoardDetailItem.ai_platform }}</span>
            <span v-if="ts.taskBoardDetailItem.project_name" class="muted">| {{ ts.taskBoardDetailItem.project_name }}</span>
          </div>
        </section>
        <section class="task-detail-section">
          <h4>描述</h4>
          <div class="task-detail-markdown" v-html="renderMarkdown(ts.taskBoardDetailItem.description || '暂无描述')"></div>
        </section>
        <section class="task-detail-section">
          <h4>关联</h4>
          <div class="task-detail-grid">
            <div><span>父任务</span><strong>{{ ts.taskBoardDetailItem.parent_task_name || '-' }}</strong></div>
            <div><span>上游任务</span><strong>{{ ts.taskBoardDetailItem.upstream_task_name || '-' }}</strong></div>
          </div>
        </section>
        <section class="task-detail-section">
          <h4>时间</h4>
          <div class="task-detail-grid">
            <div><span>创建</span><strong>{{ ts.taskBoardDetailItem.created_at ? new Date(ts.taskBoardDetailItem.created_at).toLocaleString('zh-CN') : '-' }}</strong></div>
            <div><span>更新</span><strong>{{ ts.taskBoardDetailItem.updated_at ? new Date(ts.taskBoardDetailItem.updated_at).toLocaleString('zh-CN') : '-' }}</strong></div>
          </div>
        </section>
      </div>
      <div class="modal-footer">
        <button type="button" class="project-btn" @click="ts.closeTaskBoardDetailModal">关闭</button>
        <button type="button" class="project-btn project-btn-primary" @click="ts.openTaskBoardEditModal(ts.taskBoardDetailItem)">编辑</button>
      </div>
    </div>
  </div>
</template>
