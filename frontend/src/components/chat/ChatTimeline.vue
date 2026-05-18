<script setup>
import { useSessionStore } from '../../stores/useSessionStore.js'
import { useTimelineScroll } from '../../composables/useTimelineScroll.js'

const ss = useSessionStore()
const { timelineScrollRef, onTimelineScroll } = useTimelineScroll()
</script>

<template>
  <div class="timeline-panel-header">
    <h2>对话时间线</h2>
    <div v-if="ss.dispatchActiveTask" class="dispatch-status-bar" :class="ss.dispatchStatusClassMap[ss.dispatchActiveTask.status] || ''">
      <span class="dispatch-status-label">{{ ss.dispatchStatusLabelMap[ss.dispatchActiveTask.status] || ss.dispatchActiveTask.status }}</span>
      <span class="dispatch-task-id">{{ ss.dispatchActiveTask.id }}</span>
      <div class="dispatch-actions">
        <button v-if="ss.dispatchIsCancellable" type="button" class="dispatch-action-btn dispatch-cancel-btn" @click="ss.cancelDispatchTask">取消任务</button>
        <button v-if="ss.dispatchIsResumable" type="button" class="dispatch-action-btn dispatch-resume-btn" @click="ss.clearActiveTask">关闭任务</button>
        <button v-if="ss.dispatchActiveTask.status === 'completed' || ss.dispatchActiveTask.status === 'failed' || ss.dispatchActiveTask.status === 'cancelled'" type="button" class="dispatch-action-btn dispatch-close-btn" @click="ss.clearActiveTask">清除</button>
      </div>
    </div>
    <div v-if="ss.dispatchError" class="dispatch-friendly-error">{{ ss.dispatchError }}</div>
  </div>

  <div class="timeline-scroll scrollbar-themed" ref="timelineScrollRef" @scroll="onTimelineScroll">
    <div v-if="ss.displayMessages.length === 0 && ss.dispatchTaskId && ss.dispatchActiveTask && ['queued','running','awaiting_input','paused'].includes(ss.dispatchActiveTask.status)" class="muted">⏳ 正在恢复任务进度，接入实时数据流中...</div>
    <div v-else-if="ss.displayMessages.length === 0 && ss.dispatchTaskId" class="muted">📭 暂无执行记录</div>
    <div v-else-if="ss.displayMessages.length === 0" class="muted">暂无消息</div>
    <div
      v-for="message in ss.displayMessages"
      :key="message.id"
      class="timeline-item"
      :class="[
        ss.messageSideClass(message.role),
        message.meta_json?.thinking ? 'msg-thinking' : '',
        message.meta_json?.tool_call ? 'msg-tool' : '',
        message.meta_json?.streaming ? 'streaming' : '',
      ]"
    >
      <template v-if="message.meta_json?.thinking">
        <details class="thinking-bubble">
          <summary class="thinking-summary">
            <span class="thinking-icon">🧠</span> 思考过程
            <span class="thinking-chars">{{ message.content.length }} 字符</span>
          </summary>
          <pre class="thinking-content">{{ message.content }}</pre>
        </details>
      </template>

      <template v-else-if="message.meta_json?.tool_call">
        <div class="tool-bubble" :class="message.meta_json?.completed ? 'tool-done' : 'tool-running'">
          <div class="tool-header">
            <span class="tool-status-icon">{{ message.meta_json?.tool_error ? '❌' : message.meta_json?.completed ? '✅' : '⚙️' }}</span>
            <span class="tool-name">{{ message.content }}</span>
            <span v-if="message.meta_json?.completed && message.meta_json?.duration_ms != null" class="tool-duration">{{ message.meta_json.duration_ms }}ms</span>
            <span v-else-if="!message.meta_json?.completed" class="tool-spinning">…</span>
          </div>
          <div v-if="message.meta_json?.tool_error" class="tool-error-text">{{ message.meta_json.tool_error }}</div>
          <details v-if="message.meta_json?.function_args" class="tool-args-details">
            <summary>参数</summary>
            <pre class="tool-args-pre">{{ message.meta_json.function_args }}</pre>
          </details>
        </div>
      </template>

      <template v-else>
        <div class="role-chip" :class="ss.roleClass(message.role)">{{ ss.roleLabelMap[message.role] || message.role }}</div>
        <div class="timeline-meta">
          {{ new Date(message.created_at).toLocaleString() }}
          <span v-if="message.meta_json?.streaming" class="streaming-indicator">生成中…</span>
        </div>
        <div class="timeline-content" v-html="message.role === 'assistant' ? ss.renderMarkdown(message.content) : message.content"></div>
      </template>
    </div>
  </div>
</template>
