<script setup>
import { useConfigStore } from '../stores/useConfigStore.js'
import { useProjectStore } from '../stores/useProjectStore.js'

const cs = useConfigStore()
const ps = useProjectStore()
</script>

<template>
  <section class="main-grid config-grid">
    <article class="panel state-panel config-panel config-panel-system">
      <div class="config-panel-head">
        <h2>系统配置</h2>
        <p class="config-panel-subtitle">集中管理平台级连接能力，所有配置即时生效并用于项目仓库操作。</p>
      </div>
      <div class="state-group config-card system-config-card">
        <div class="state-group-title">GitHub 集成</div>
        <div class="system-config-layout">
          <div class="system-config-main">
            <label class="create-field system-config-field">
              <span class="create-field-label">GitHub Token</span>
              <input v-model="cs.githubTokenDraft" type="password" class="picker-search-input system-token-input" :disabled="cs.githubTokenSaving" placeholder="输入 GITHUB_TOKEN" />
            </label>
            <p class="system-config-hint">建议使用具备 repo 权限的 Personal Access Token，用于仓库读取与创建。</p>
          </div>
          <aside class="system-config-side">
            <div class="system-status-card" :class="{ 'system-status-card-ready': cs.githubTokenConfigured }">
              <span class="system-status-label">当前状态</span>
              <span class="system-status-value">{{ cs.githubTokenConfigured ? '已配置' : '未配置' }}</span>
            </div>
            <div class="picker-actions system-config-actions">
              <button type="button" class="picker-btn system-save-btn" :disabled="cs.githubTokenSaving || !cs.githubTokenDraft.trim()" @click="cs.saveGithubToken">
                {{ cs.githubTokenSaving ? '保存中...' : '保存 Token' }}
              </button>
            </div>
          </aside>
        </div>
      </div>
    </article>
  </section>
</template>
