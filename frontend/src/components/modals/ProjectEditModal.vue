<script setup>
import { useProjectStore } from '../../stores/useProjectStore.js'

const ps = useProjectStore()
</script>

<template>
  <div v-if="ps.isProjectEditModalOpen" class="picker-modal-overlay" @click.self="ps.closeProjectEditModal">
    <div class="picker-modal panel create-conversation-modal">
      <div class="picker-modal-header">
        <h3>编辑项目</h3>
        <button type="button" class="picker-close-btn" :disabled="ps.updatingProject" @click="ps.closeProjectEditModal" aria-label="关闭"><span class="close-icon" aria-hidden="true">✕</span></button>
      </div>
      <div class="create-conversation-form">
        <label class="create-field">
          <span class="create-field-label">项目名称</span>
          <input v-model="ps.editProjectForm.name" class="picker-search-input" :disabled="ps.updatingProject" placeholder="请输入项目名称" />
        </label>
        <label class="create-field">
          <span class="create-field-label">项目简介</span>
          <textarea v-model="ps.editProjectForm.description" class="create-initial-message" :disabled="ps.updatingProject" placeholder="请输入项目简介"></textarea>
        </label>
      </div>
      <div class="picker-actions">
        <button type="button" class="picker-btn ghost" :disabled="ps.updatingProject" @click="ps.closeProjectEditModal">取消</button>
        <button type="button" class="picker-btn" :disabled="ps.updatingProject || !ps.editProjectForm.name.trim()" @click="ps.submitEditProject">
          {{ ps.updatingProject ? '保存中...' : '保存修改' }}
        </button>
      </div>
    </div>
  </div>
</template>
