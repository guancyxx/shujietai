<script setup>
import { ref, computed, onMounted } from 'vue'
import { fetchJson } from '../services/apiClient.js'

const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:18000'

const skillsCatalog = ref(null)
const skillsCatalogLoading = ref(false)
const skillsCatalogError = ref('')
const skillsCatalogSearch = ref('')
const skillsCatalogCategoryFilter = ref('全部')
const skillsCatalogProviderFilter = ref('hermes')
const skillsCatalogTypeFilter = ref('全部')
const skillDetailTarget = ref(null)
const skillDetailContent = ref('')
const skillDetailContentLoading = ref(false)
const skillDetailError = ref('')
const skillsCatalogPage = ref(1)
const skillsCatalogPageSize = 30
const skillsCatalogView = ref('list')

const skillsCatalogProviders = computed(() => {
  if (!skillsCatalog.value) return [{ id: 'hermes', label: 'Hermes Agent' }]
  return skillsCatalog.value.providers.map(p => ({ id: p.id, label: p.label }))
})

const skillsCatalogCategories = computed(() => {
  if (!skillsCatalog.value) return []
  const provider = skillsCatalog.value.providers.find(p => p.id === skillsCatalogProviderFilter.value)
  if (!provider) return []
  return [...new Set(provider.skills.map(s => s.category))].sort()
})

const filteredCatalogSkills = computed(() => {
  if (!skillsCatalog.value) return []
  const provider = skillsCatalog.value.providers.find(p => p.id === skillsCatalogProviderFilter.value)
  if (!provider) return []
  const kw = skillsCatalogSearch.value.trim().toLowerCase()
  const cf = skillsCatalogCategoryFilter.value
  const tf = skillsCatalogTypeFilter.value
  return provider.skills
    .filter(s => {
      if (cf !== '全部' && s.category !== cf) return false
      if (tf !== '全部' && (s.skill_type || 'builtin') !== tf) return false
      if (!kw) return true
      return s.name.toLowerCase().includes(kw) || (s.description || '').toLowerCase().includes(kw)
    })
    .map(s => ({ ...s, provider_id: provider.id, provider_label: provider.label }))
})

const skillsCatalogTotalPages = computed(() => Math.max(1, Math.ceil(filteredCatalogSkills.value.length / skillsCatalogPageSize)))
const pagedCatalogSkills = computed(() => {
  const start = (skillsCatalogPage.value - 1) * skillsCatalogPageSize
  return filteredCatalogSkills.value.slice(start, start + skillsCatalogPageSize)
})

async function openSkillDetail(skill) {
  skillDetailTarget.value = skill
  skillDetailContent.value = ''
  skillDetailError.value = ''
  skillDetailContentLoading.value = true
  try {
    const res = await fetch(`${apiBase}/api/v1/skills/${encodeURIComponent(skill.name)}/content`)
    if (res.ok) {
      const data = await res.json()
      skillDetailContent.value = data.content || ''
    } else if (res.status === 404) {
      skillDetailError.value = '技能内容文件未找到。'
    } else {
      skillDetailError.value = `加载失败 (HTTP ${res.status})`
    }
  } catch { skillDetailError.value = '网络请求失败。' }
  skillDetailContentLoading.value = false
}

function closeSkillDetail() { skillDetailTarget.value = null; skillDetailContent.value = ''; skillDetailError.value = '' }

async function loadSkillsCatalog() {
  skillsCatalogLoading.value = true
  skillsCatalogError.value = ''
  try {
    skillsCatalog.value = await fetchJson(`${apiBase}/api/v1/skills`)
  } catch (e) { skillsCatalogError.value = e?.message || 'Failed to load skills' }
  finally { skillsCatalogLoading.value = false }
}

onMounted(async () => { await loadSkillsCatalog() })
</script>

<template>
  <section class="main-grid skills-catalog-grid">
    <article class="panel skills-catalog-panel">
      <div class="skills-catalog-header">
        <h2>Skills 库</h2>
        <div class="skills-catalog-controls">
          <div class="sg-view-switch">
            <button type="button" class="picker-btn" :class="{ active: skillsCatalogView === 'list' }" @click="skillsCatalogView = 'list'">列表</button>
            <button type="button" class="picker-btn" :class="{ active: skillsCatalogView === 'graph' }" @click="skillsCatalogView = 'graph'">图谱</button>
          </div>
          <template v-if="skillsCatalogView === 'list'">
            <select v-model="skillsCatalogProviderFilter" class="dispatch-filter-select">
              <option v-for="p in skillsCatalogProviders" :key="p.id" :value="p.id">{{ p.label }}</option>
            </select>
            <select v-model="skillsCatalogCategoryFilter" class="dispatch-filter-select">
              <option value="全部">全部分类</option>
              <option v-for="cat in skillsCatalogCategories" :key="cat" :value="cat">{{ cat }}</option>
            </select>
            <select v-model="skillsCatalogTypeFilter" class="dispatch-filter-select">
              <option value="全部">全部类型</option>
              <option value="builtin">内置</option>
              <option value="custom">自建</option>
              <option value="third-party">第三方</option>
            </select>
            <input v-model="skillsCatalogSearch" class="picker-search-input skills-catalog-search" placeholder="搜索 skill 名称或描述" />
            <button type="button" class="picker-btn ghost" @click="loadSkillsCatalog" :disabled="skillsCatalogLoading">{{ skillsCatalogLoading ? '加载中...' : '刷新' }}</button>
          </template>
        </div>
      </div>
      <template v-if="skillsCatalogView === 'list'">
        <div v-if="skillsCatalogError" class="skills-catalog-error muted">{{ skillsCatalogError }}</div>
        <div v-else-if="skillsCatalogLoading" class="skills-catalog-loading muted">加载中...</div>
        <template v-else>
          <div class="skills-catalog-meta muted">共 {{ filteredCatalogSkills.length }} 个 skills，第 {{ skillsCatalogPage }}/{{ skillsCatalogTotalPages }} 页</div>
          <div class="skills-catalog-list scrollbar-themed">
            <div v-for="skill in pagedCatalogSkills" :key="skill.provider_id + '/' + skill.name" class="skill-card" @click="openSkillDetail(skill)">
              <div class="skill-card-badges">
                <span :class="['skill-type-badge', 'skill-type-' + (skill.skill_type || 'builtin')]">{{ skill.skill_type === 'custom' ? '自建' : skill.skill_type === 'third-party' ? '第三方' : '内置' }}</span>
                <span class="skill-category-badge">{{ skill.category }}</span>
              </div>
              <div class="skill-card-name">{{ skill.name }}</div>
              <div class="skill-card-desc">{{ skill.description || '暂无描述' }}</div>
            </div>
            <div v-if="filteredCatalogSkills.length === 0" class="muted">无匹配 skills</div>
          </div>
          <div v-if="skillsCatalogTotalPages > 1" class="skills-catalog-pagination">
            <button class="picker-btn ghost" :disabled="skillsCatalogPage <= 1" @click="skillsCatalogPage--">上一页</button>
            <span class="muted">{{ skillsCatalogPage }} / {{ skillsCatalogTotalPages }}</span>
            <button class="picker-btn ghost" :disabled="skillsCatalogPage >= skillsCatalogTotalPages" @click="skillsCatalogPage++">下一页</button>
          </div>
        </template>
      </template>
    </article>
  </section>

  <!-- Skill Detail Modal -->
  <div v-if="skillDetailTarget" class="skill-detail-overlay" @click.self="closeSkillDetail">
    <div class="skill-detail-modal scrollbar-themed">
      <button class="skill-detail-close" @click="closeSkillDetail" aria-label="关闭">✕</button>
      <div class="skill-detail-title">{{ skillDetailTarget.name }}</div>
      <div class="skill-detail-badges">
        <span :class="['skill-type-badge', 'skill-type-' + (skillDetailTarget.skill_type || 'builtin')]">{{ skillDetailTarget.skill_type === 'custom' ? '自建' : skillDetailTarget.skill_type === 'third-party' ? '第三方' : '内置' }}</span>
        <span class="skill-category-badge">{{ skillDetailTarget.category }}</span>
      </div>
      <div class="skill-detail-desc">{{ skillDetailTarget.description || '暂无描述' }}</div>
      <div v-if="skillDetailContentLoading" class="muted skill-detail-content-loading">⏳ 加载内容中...</div>
      <div v-else-if="skillDetailError" class="skill-detail-content-error">❌ {{ skillDetailError }}</div>
      <pre v-else-if="skillDetailContent" class="skill-detail-content scrollbar-themed">{{ skillDetailContent }}</pre>
      <div v-else class="muted skill-detail-content-empty">暂无详细内容</div>
    </div>
  </div>
</template>
