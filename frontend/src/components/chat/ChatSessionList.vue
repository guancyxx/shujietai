<script setup>
import { useSessionStore } from '../../stores/useSessionStore.js'

const ss = useSessionStore()
</script>

<template>
  <article class="panel tasks-panel">
    <div class="tasks-panel-header">
      <h2>对话列表</h2>
      <div class="tasks-panel-actions">
        <button type="button" class="session-new-btn" @click="ss.createNewConversation">新建对话</button>
        <button
          type="button"
          class="session-clear-btn"
          :disabled="ss.clearingSessions || ss.deletingSessionId || ss.sessions.length === 0"
          @click="ss.clearAllSessions"
        >
          {{ ss.clearingSessions ? '清空中...' : '清空对话' }}
        </button>
      </div>
    </div>

    <div
      class="pinned-ai-entry"
      :class="{ 'pinned-ai-entry-active': ss.isBlankChatMode }"
      @click="ss.activateBlankChat"
    >
      <div class="pinned-ai-icon">🤖</div>
      <div class="pinned-ai-body">
        <div class="pinned-ai-title">AI Assistant</div>
        <div class="pinned-ai-subtitle">AI provider: {{ ss.blankChatProvider || 'hermes' }}</div>
      </div>
      <select
        v-if="ss.blankChatProviders.length > 1"
        v-model="ss.blankChatProvider"
        class="pinned-ai-provider-select"
        @click.stop
      >
        <option v-for="provider in ss.blankChatProviders" :key="provider" :value="provider">{{ provider }}</option>
      </select>
    </div>

    <div class="conversation-only-list scrollbar-themed-auto-hide">
      <div
        v-for="item in ss.sessions"
        :key="item.id"
        class="task conversation-task"
        :class="{ 'conversation-task-active': item.id === ss.selectedSessionId }"
      >
        <button
          type="button"
          class="conversation-task-main"
          @click="ss.selectConversation(item.id, item.external_session_id)"
        >
          <div class="conversation-task-header">
            <div class="task-title conversation-task-title">{{ item.title }}</div>
            <span class="conversation-platform-pill">{{ item.platform }}</span>
          </div>
          <div class="conversation-task-subtitle">{{ item.external_session_id }}</div>
          <div class="conversation-task-meta-row">
            <span class="conversation-meta-label">开始时间</span>
            <span class="conversation-meta-value">{{ ss.formatSessionTime(item.started_at) }}</span>
          </div>
        </button>
        <button
          type="button"
          class="card-delete-btn conversation-delete-btn"
          :aria-label="`删除对话 ${item.title}`"
          :disabled="ss.clearingSessions || ss.deletingSessionId === item.id"
          @click="ss.deleteSession(item.id)"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 4h12M5.333 4V2.667a1.333 1.333 0 011.334-1.334h2.666a1.333 1.333 0 011.334 1.334V4m2 0v9.333a1.333 1.333 0 01-1.334 1.334H4.667a1.333 1.333 0 01-1.334-1.334V4h9.334zM6.667 7.333v4M9.333 7.333v4"/></svg>
        </button>
      </div>
      <div v-if="ss.sessions.length === 0" class="muted">暂无会话</div>
    </div>
  </article>
</template>
