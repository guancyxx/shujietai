<script setup>
import { useConfigStore } from '../stores/useConfigStore.js'
import { useSessionStore } from '../stores/useSessionStore.js'
import { computed } from 'vue'

const cs = useConfigStore()
const ss = useSessionStore()
const catalog = computed(() => cs.makeRuntimeCatalog(ss.cockpit))
</script>

<template>
  <section class="main-grid config-grid">
    <article class="panel state-panel config-panel">
      <h2>模型与 AI 配置</h2>
      <div class="state-group">
        <div class="state-group-title">模型</div>
        <div class="kv">
          <span class="muted">selected_model</span>
          <button type="button" class="state-picker-btn" @click="cs.openModelModal(catalog)">
            {{ catalog.selectedModelText }}
          </button>
        </div>
        <div class="kv">
          <span class="muted">provider</span>
          <span class="state-value">{{ catalog.selectedModelProvider }}</span>
        </div>
      </div>
      <div class="state-group">
        <div class="state-group-title">技能</div>
        <div class="kv">
          <span class="muted">selected_skills</span>
          <button type="button" class="state-picker-btn" @click="cs.openSkillModal">{{ cs.selectedSkillsCountText }}</button>
        </div>
      </div>
      <div class="state-group">
        <div class="state-group-title">MCP</div>
        <div class="kv">
          <span class="muted">selected_mcp_servers</span>
          <button type="button" class="state-picker-btn" @click="cs.openMcpModal">{{ cs.selectedMcpCountText }}</button>
        </div>
      </div>
    </article>
  </section>
</template>
