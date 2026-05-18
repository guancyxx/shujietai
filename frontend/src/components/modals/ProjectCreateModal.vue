<script setup>
import { useProjectStore } from '../../stores/useProjectStore.js'

const ps = useProjectStore()
</script>

<template>
  <div v-if="ps.isProjectCreateModalOpen" class="picker-modal-overlay" @click.self="ps.closeProjectCreateModal">
    <div class="picker-modal panel create-conversation-modal">
      <div class="picker-modal-header">
        <h3>新建项目</h3>
        <button type="button" class="picker-close-btn" :disabled="ps.creatingProject" @click="ps.closeProjectCreateModal" aria-label="关闭"><span class="close-icon" aria-hidden="true">✕</span></button>
      </div>
      <div class="create-conversation-form">
        <label class="create-field">
          <span class="create-field-label">项目名称</span>
          <input v-model="ps.createProjectForm.name" class="picker-search-input" :disabled="ps.creatingProject || ps.creatingGithubRepo" placeholder="请输入项目名称，如 shujietai-demo" />
        </label>
        <label class="create-field">
          <span class="create-field-label">项目简介</span>
          <textarea v-model="ps.createProjectForm.description" class="create-initial-message" :disabled="ps.creatingProject || ps.creatingGithubRepo" placeholder="请输入项目简介"></textarea>
        </label>
        <div class="project-repo-mode-card">
          <label class="create-field-checkbox">
            <input type="checkbox" v-model="ps.createRepoEnabled" :disabled="ps.creatingProject || ps.creatingGithubRepo" />
            <span>同时新建 GitHub 仓库（可选）</span>
          </label>
          <template v-if="!ps.createRepoEnabled">
            <label class="create-field">
              <span class="create-field-label">已有仓库（必选）</span>
              <select v-model="ps.createProjectForm.repository_url" class="picker-provider-select" :disabled="ps.creatingProject || ps.creatingGithubRepo" @change="ps.handleRepositoryChange">
                <option value="" disabled>请选择仓库</option>
                <option v-for="repo in ps.getRepoChoices()" :key="repo.url" :value="repo.url">{{ repo.full_name }} · {{ repo.description || '无描述' }}</option>
              </select>
            </label>
          </template>
          <template v-else>
            <label class="create-field-checkbox">
              <input type="checkbox" v-model="ps.createProjectForm.private" :disabled="ps.creatingProject || ps.creatingGithubRepo" />
              <span>创建为私有仓库</span>
            </label>
            <div class="project-repo-mode-hint">将使用"项目名称"作为仓库名，"项目简介"作为仓库描述。</div>
          </template>
        </div>
      </div>
      <div class="picker-actions">
        <button type="button" class="picker-btn ghost" :disabled="ps.creatingProject || ps.creatingGithubRepo" @click="ps.closeProjectCreateModal">取消</button>
        <button v-if="!ps.createRepoEnabled" type="button" class="picker-btn" :disabled="ps.creatingProject || ps.creatingGithubRepo || !ps.createProjectForm.name.trim() || !ps.createProjectForm.repository_url.trim()" @click="ps.submitCreateProject">
          {{ ps.creatingProject ? '创建中...' : '创建项目' }}
        </button>
        <button v-else type="button" class="picker-btn" :disabled="ps.creatingProject || ps.creatingGithubRepo || !ps.createProjectForm.name.trim()" @click="ps.createGithubRepo">
          {{ ps.creatingGithubRepo ? '创建仓库并建项目中...' : '新建仓库并创建项目' }}
        </button>
      </div>
    </div>
  </div>
</template>
