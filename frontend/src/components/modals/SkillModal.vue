<script setup>
import { computed } from 'vue'
import { useConfigStore } from '../../stores/useConfigStore.js'
import { useSessionStore } from '../../stores/useSessionStore.js'

const cs = useConfigStore()
const ss = useSessionStore()
const catalog = computed(() => cs.makeRuntimeCatalog(ss.cockpit))
const filteredItems = computed(() => cs.getFilteredSkillItems(catalog.value))
</script>

<template>
  <div v-if="cs.isSkillModalOpen" class="picker-modal-overlay" @click.self="cs.closeSkillModal">
    <div class="picker-modal panel">
      <div class="picker-modal-header">
        <h3>选择 Skills</h3>
        <button type="button" class="picker-close-btn" @click="cs.closeSkillModal" aria-label="关闭"><span class="close-icon" aria-hidden="true">✕</span></button>
      </div>
      <div class="picker-search-row">
        <input v-model="cs.skillSearchDraft" class="picker-search-input" placeholder="搜索 skill 名称或描述" />
      </div>
      <div class="picker-list">
        <label v-for="item in filteredItems" :key="item.name" class="picker-item">
          <input type="checkbox" :checked="cs.isTempSkillChecked(item.name)" @change="cs.toggleTempSkill(item.name)" />
          <div class="picker-item-text">
            <div class="picker-item-title">{{ item.name }}</div>
            <div class="picker-item-desc">{{ item.description || '-' }}</div>
          </div>
        </label>
        <div v-if="filteredItems.length === 0" class="muted">无匹配项</div>
      </div>
      <div class="picker-actions">
        <button type="button" class="picker-btn ghost" @click="cs.closeSkillModal">取消</button>
        <button type="button" class="picker-btn" @click="cs.applySkillModalSelection">确认</button>
      </div>
    </div>
  </div>
</template>
