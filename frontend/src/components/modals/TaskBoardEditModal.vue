<script setup>
import { useTaskStore } from '../../stores/useTaskStore.js'
import { useProjectStore } from '../../stores/useProjectStore.js'

const ts = useTaskStore()
const ps = useProjectStore()
</script>

<template>
  <div v-if="ts.isTaskBoardEditModalOpen" class="picker-modal-overlay" @click.self="ts.closeTaskBoardEditModal">
    <div class="picker-modal panel create-conversation-modal">
      <div class="picker-modal-header">
        <h3>编辑任务</h3>
        <button type="button" class="picker-close-btn" :disabled="ts.updatingTaskBoardItem" @click="ts.closeTaskBoardEditModal" aria-label="关闭"><span class="close-icon" aria-hidden="true">✕</span></button>
      </div>
      <div class="create-conversation-form">
        <label class="create-field">
          <span class="create-field-label">任务名称</span>
          <input v-model="ts.taskBoardEditForm.name" class="picker-search-input" :disabled="ts.updatingTaskBoardItem" placeholder="请输入任务名称" />
        </label>
        <label class="create-field">
          <span class="create-field-label">描述</span>
          <textarea v-model="ts.taskBoardEditForm.description" class="create-initial-message" :disabled="ts.updatingTaskBoardItem" placeholder="请输入任务描述"></textarea>
        </label>
        <label class="create-field">
          <span class="create-field-label">AI 平台</span>
          <select v-model="ts.taskBoardEditForm.ai_platform" class="picker-provider-select" :disabled="ts.updatingTaskBoardItem">
            <option value="hermes">hermes</option>
          </select>
        </label>
        <label class="create-field">
          <span class="create-field-label">所属项目</span>
          <select v-model="ts.taskBoardEditForm.project_id" class="picker-provider-select" :disabled="ts.updatingTaskBoardItem">
            <option v-for="opt in ts.taskBoardProjectOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
          </select>
        </label>
        <label class="create-field">
          <span class="create-field-label">上游任务</span>
          <select v-model="ts.taskBoardEditForm.upstream_task_id" class="picker-provider-select" :disabled="ts.updatingTaskBoardItem">
            <option value="">无</option>
            <option v-for="opt in ts.taskBoardDependencyOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
          </select>
        </label>
        <label class="create-field">
          <span class="create-field-label">父任务</span>
          <select v-model="ts.taskBoardEditForm.parent_task_id" class="picker-provider-select" :disabled="ts.updatingTaskBoardItem">
            <option value="">无（顶级任务）</option>
            <option v-for="opt in ts.taskBoardDependencyOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
          </select>
        </label>
        <label class="create-field">
          <span class="create-field-label">状态</span>
          <select v-model="ts.taskBoardEditForm.status" class="picker-provider-select" :disabled="ts.updatingTaskBoardItem">
            <option v-for="opt in ts.taskBoardStatusOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
          </select>
        </label>
        <label v-if="ts.requiresTaskStatusReason(ts.taskBoardEditForm.status)" class="create-field">
          <span class="create-field-label">原因</span>
          <input v-model="ts.taskBoardEditForm.status_reason" class="picker-search-input" :disabled="ts.updatingTaskBoardItem" placeholder="阻塞或取消原因" />
        </label>
        <label class="create-field">
          <span class="create-field-label">优先级</span>
          <select v-model="ts.taskBoardEditForm.priority" class="picker-provider-select" :disabled="ts.updatingTaskBoardItem">
            <option v-for="opt in ts.taskBoardPriorityOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
          </select>
        </label>
      </div>
      <div class="picker-actions">
        <button type="button" class="picker-btn ghost" :disabled="ts.updatingTaskBoardItem" @click="ts.closeTaskBoardEditModal">取消</button>
        <button type="button" class="picker-btn" :disabled="ts.updatingTaskBoardItem || !ts.taskBoardEditForm.name.trim()" @click="ts.submitEditTaskBoardItem">
          {{ ts.updatingTaskBoardItem ? '保存中...' : '保存修改' }}
        </button>
      </div>
    </div>
  </div>
</template>
