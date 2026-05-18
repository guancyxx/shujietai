<script setup>
import { ref } from 'vue'
import { useSessionStore } from '../../stores/useSessionStore.js'
import { useConfigStore } from '../../stores/useConfigStore.js'

const ss = useSessionStore()
const cs = useConfigStore()

const timelineScrollRef = ref(null)
// Expose ref so parent can pass to ChatTimeline; in this split we attach at composer level
defineExpose({ timelineScrollRef })
</script>

<template>
  <form class="chat-composer" @submit.prevent="ss.sendMessageToHermes">
    <div class="conversation-latest-status" :class="`status-${ss.conversationLatestStatus.tone}`">
      <span class="latest-status-label">会话状态</span>
      <span class="latest-status-text">{{ ss.conversationLatestStatus.text }}</span>
      <span class="latest-status-time">{{ ss.conversationLatestStatus.time }}</span>
    </div>

    <textarea
      v-model="ss.composerText"
      class="composer-input"
      :disabled="ss.sending"
      :placeholder="ss.dispatchIsRunning ? '输入修正内容，将打断当前 AI 回复并重新发送' : (ss.dispatchAwaitingInput ? 'AI 正在等待你的回复...' : '输入消息，直接与 AI 对话')"
      @keydown="ss.handleComposerKeydown"
    ></textarea>

    <button class="composer-send" type="submit" :disabled="ss.sending || !ss.composerText.trim()">
      {{ ss.sending ? '处理中...' : (ss.dispatchIsRunning ? '打断并发送' : '发送') }}
    </button>
  </form>
</template>
