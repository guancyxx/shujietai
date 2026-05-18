<script setup>
import { useSessionStore } from '../../stores/useSessionStore.js'

const ss = useSessionStore()
</script>

<template>
  <div v-if="ss.isCreateConversationModalOpen" class="picker-modal-overlay" @click.self="ss.closeCreateConversationModal">
    <div class="picker-modal panel create-conversation-modal">
      <div class="picker-modal-header">
        <h3>新建对话</h3>
        <button type="button" class="picker-close-btn" :disabled="ss.creatingConversation" @click="ss.closeCreateConversationModal" aria-label="关闭"><span class="close-icon" aria-hidden="true">✕</span></button>
      </div>
      <div class="create-conversation-form">
        <label class="create-field">
          <span class="create-field-label">平台</span>
          <select v-model="ss.createConversationPlatform" class="picker-provider-select" :disabled="ss.creatingConversation">
            <option v-for="name in ss.platformOptions" :key="name" :value="name">{{ name }}</option>
          </select>
        </label>
        <label class="create-field">
          <span class="create-field-label">初始消息</span>
          <textarea v-model="ss.createConversationInitialMessage" class="create-initial-message" :disabled="ss.creatingConversation" placeholder="请输入你想发送的第一条消息" @keydown="ss.handleCreateInitialMessageKeydown"></textarea>
        </label>
      </div>
      <div class="picker-actions">
        <button type="button" class="picker-btn ghost" :disabled="ss.creatingConversation" @click="ss.closeCreateConversationModal">取消</button>
        <button type="button" class="picker-btn" :disabled="ss.creatingConversation || !ss.createConversationInitialMessage.trim()" @click="ss.submitCreateConversation">
          {{ ss.creatingConversation ? '创建中...' : '创建并发送' }}
        </button>
      </div>
    </div>
  </div>
</template>
