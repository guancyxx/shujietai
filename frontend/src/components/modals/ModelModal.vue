<script setup>
import { computed } from 'vue'
import { useConfigStore } from '../../stores/useConfigStore.js'
import { useSessionStore } from '../../stores/useSessionStore.js'

const cs = useConfigStore()
const ss = useSessionStore()

const catalog = computed(() => cs.makeRuntimeCatalog(ss.cockpit))
const providerOptions = computed(() => cs.getModelProviderOptions(catalog.value))
const filteredItems = computed(() => cs.getFilteredModelItems(catalog.value))
</script>

<template>
  <div v-if="cs.isModelModalOpen" class="picker-modal-overlay" @click.self="cs.closeModelModal">
    <div class="picker-modal panel">
      <div class="picker-modal-header">
        <h3>选择模型</h3>
        <button type="button" class="picker-close-btn" @click="cs.closeModelModal" aria-label="关闭"><span class="close-icon" aria-hidden="true">✕</span></button>
      </div>
      <div class="picker-search-row picker-provider-row">
        <select v-model="cs.modelProviderDraft" class="picker-provider-select">
          <option v-for="provider in providerOptions" :key="provider" :value="provider">{{ provider }}</option>
        </select>
        <input v-model="cs.modelSearchDraft" class="picker-search-input" placeholder="搜索 model 名称" />
      </div>
      <div class="picker-list">
        <label v-for="item in filteredItems" :key="item.name" class="picker-item">
          <input type="radio" name="model-selection" :checked="cs.tempSelectedModel === item.name" @change="cs.selectTempModel(item.name)" />
          <div class="picker-item-text">
            <div class="picker-item-title">{{ item.name }}</div>
            <div class="picker-item-desc">provider: {{ item.provider || '-' }}</div>
          </div>
        </label>
        <div v-if="filteredItems.length === 0" class="muted">无匹配项</div>
      </div>
      <div class="picker-actions">
        <button type="button" class="picker-btn ghost" @click="cs.closeModelModal">取消</button>
        <button type="button" class="picker-btn" @click="cs.applyModelModalSelection">确认</button>
      </div>
    </div>
  </div>
</template>
