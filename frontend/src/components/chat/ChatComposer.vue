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
  <div class="chat-composer">
    <aside class="cockpit-status cockpit-status-inline">
      <div class="cpi-status" :class="`status-${ss.conversationLatestStatus.tone}`">
        <span class="cpi-status-dot" aria-hidden="true"></span>
        <span class="cpi-status-text">{{ ss.conversationLatestStatus.text }}</span>
        <span class="cpi-status-time">{{ ss.conversationLatestStatus.time }}</span>
      </div>
    </aside>

    <div v-if="ss.dispatchIsResumable" class="dispatch-composer-hint">
      需要你的输入以继续任务。输入回复后按 Enter 发送。
    </div>

    <div class="chat-composer-input-row">
      <textarea
        v-model="ss.composerText"
        class="chat-composer-textarea"
        placeholder="输入消息，按 Enter 发送..."
        rows="2"
        :disabled="ss.sending"
        @keydown="ss.handleComposerKeydown"
      ></textarea>
      <button
        type="button"
        class="chat-composer-send-btn"
        :disabled="ss.sending || !ss.composerText.trim()"
        @click="ss.sendMessageToHermes"
      >
        {{ ss.sending ? '发送中...' : '发送' }}
      </button>
    </div>
  </div>
</template>
