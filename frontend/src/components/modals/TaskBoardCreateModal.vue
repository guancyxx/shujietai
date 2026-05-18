<script setup>
import { useTaskStore } from '../../stores/useTaskStore.js'
import { useProjectStore } from '../../stores/useProjectStore.js'

const ts = useTaskStore()
const ps = useProjectStore()
</script>

<template>
  <div v-if="ts.isTaskBoardCreateModalOpen" class="picker-modal-overlay" @click.self="ts.closeTaskBoardCreateModal">
    <div class="picker-modal panel create-conversation-modal">
      <div class="picker-modal-header">
        <h3>新建任务</h3>
        <button type="button" class="picker-close-btn" :disabled="ts.creatingTaskBoardItem" @click="ts.closeTaskBoardCreateModal" aria-label="关闭"><span class="close-icon" aria-hidden="true">✕</span></button>
      </div>
      <div class="create-conversation-form">
        <label class="create-field">
          <span class="create-field-label">任务名称</span>
          <input v-model="ts.taskBoardCreateForm.name" class="picker-search-input" :disabled="ts.creatingTaskBoardItem" placeholder="请输入任务名称" />
        </label>
        <label class="create-field">
          <span class="create-field-label">描述</span>
          <textarea v-model="ts.taskBoardCreateForm.description" class="create-initial-message" :disabled="ts.creatingTaskBoardItem" placeholder="请输入任务描述"></textarea>
        </label>
        <label class="create-field">
          <span class="create-field-label">AI 平台</span>
          <select v-model="ts.taskBoardCreateForm.ai_platform" class="picker-provider-select" :disabled="ts.creatingTaskBoardItem">
            <option value="hermes">hermes</option>
          </select>
        </label>
        <label class="create-field">
          <span class="create-field-label">所属项目</span>
          <select v-model="ts.taskBoardCreateForm.project_id" class="picker-provider-select" :disabled="ts.creatingTaskBoardItem">
            <option v-for="opt in ts.taskBoardProjectOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
          </select>
        </label>
        <label class="create-field">
          <span class="create-field-label">上游任务</span>
          <select v-model="ts.taskBoardCreateForm.upstream_task_id" class="picker-provider-select" :disabled="ts.creatingTaskBoardItem">
            <option value="">无</option>
            <option v-for="opt in ts.taskBoardDependencyOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
          </select>
        </label>
        <label class="create-field">
          <span class="create-field-label">父任务</span>
          <select v-model="ts.taskBoardCreateForm.parent_task_id" class="picker-provider-select" :disabled="ts.creatingTaskBoardItem">
            <option value="">无（顶级任务）</option>
            <option v-for="opt in ts.taskBoardDependencyOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
          </select>
        </label>
        <label class="create-field">
          <span class="create-field-label">优先级</span>
          <select v-model="ts.taskBoardCreateForm.priority" class="picker-provider-select" :disabled="ts.creatingTaskBoardItem">
            <option v-for="opt in ts.taskBoardPriorityOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
          </select>
        </label>
      </div>
      <div class="picker-actions">
        <button type="button" class="picker-btn ghost" :disabled="ts.creatingTaskBoardItem" @click="ts.closeTaskBoardCreateModal">取消</button>
        <button type="button" class="picker-btn" :disabled="ts.creatingTaskBoardItem || !ts.taskBoardCreateForm.name.trim()" @click="ts.submitCreateTaskBoardItem">
          {{ ts.creatingTaskBoardItem ? '创建中...' : '创建任务' }}
        </button>
      </div>
    </div>
  </div>
</template>
