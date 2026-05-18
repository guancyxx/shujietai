<script setup>
import { computed } from 'vue'
import { useConfigStore } from '../../stores/useConfigStore.js'
import { useSessionStore } from '../../stores/useSessionStore.js'

const cs = useConfigStore()
const ss = useSessionStore()
const catalog = computed(() => cs.makeRuntimeCatalog(ss.cockpit))
const filteredItems = computed(() => cs.getFilteredMcpItems(catalog.value))
</script>

<template>
  <div v-if="cs.isMcpModalOpen" class="picker-modal-overlay" @click.self="cs.closeMcpModal">
    <div class="picker-modal panel">
      <div class="picker-modal-header">
        <h3>选择 MCP 服务器</h3>
        <button type="button" class="picker-close-btn" @click="cs.closeMcpModal" aria-label="关闭"><span class="close-icon" aria-hidden="true">✕</span></button>
      </div>
      <div class="picker-search-row">
        <input v-model="cs.mcpSearchDraft" class="picker-search-input" placeholder="搜索 MCP 服务器名称" />
      </div>
      <div class="picker-list">
        <label v-for="item in filteredItems" :key="item" class="picker-item">
          <input type="checkbox" :checked="cs.isTempMcpChecked(item)" @change="cs.toggleTempMcp(item)" />
          <div class="picker-item-text">
            <div class="picker-item-title">{{ item }}</div>
          </div>
        </label>
        <div v-if="filteredItems.length === 0" class="muted">无匹配项</div>
      </div>
      <div class="picker-actions">
        <button type="button" class="picker-btn ghost" @click="cs.closeMcpModal">取消</button>
        <button type="button" class="picker-btn" @click="cs.applyMcpModalSelection">确认</button>
      </div>
    </div>
  </div>
</template>
