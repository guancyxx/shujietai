import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { fetchJson, putJson } from '../services/apiClient.js'

const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:18000'

export const useConfigStore = defineStore('config', () => {
  // --- Model / Skill / MCP ---
  const selectedModel = ref('')
  const selectedSkills = ref([])
  const selectedMcpServers = ref([])
  const isModelModalOpen = ref(false)
  const isSkillModalOpen = ref(false)
  const isMcpModalOpen = ref(false)
  const tempSelectedModel = ref('')
  const tempSelectedSkills = ref([])
  const tempSelectedMcpServers = ref([])
  const modelProviderDraft = ref('全部')
  const modelSearchDraft = ref('')
  const skillSearchDraft = ref('')
  const mcpSearchDraft = ref('')

  // --- System Config ---
  const githubTokenConfigured = ref(false)
  const githubTokenDraft = ref('')
  const githubTokenSaving = ref(false)

  // --- Getters (depend on cockpit from session store) ---
  function makeRuntimeCatalog(cockpit) {
    const runtime = cockpit?.runtime
    const modelItems = runtime?.available_model_items ?? []
    const skillItems = runtime?.available_skill_items ?? []
    const mcpServers = runtime?.available_mcp_servers ?? []
    const modelProvMap = Object.fromEntries(modelItems.map(i => [i.name, i.provider || '-']))
    return {
      availableModels: runtime?.available_models ?? [],
      availableModelItems: modelItems,
      availableSkills: runtime?.available_skills ?? [],
      availableSkillItems: skillItems,
      availableMcpServers: mcpServers,
      availablePlatforms: runtime?.available_platforms ?? ['hermes'],
      selectedModelProvider: selectedModel.value ? (modelProvMap[selectedModel.value] || '-') : '-',
      currentModelProvider: runtime?.current_model_provider || '-',
      selectedModelText: selectedModel.value || '-',
      selectedSkillsText: selectedSkills.value.length > 0 ? selectedSkills.value.join(' · ') : '-',
      selectedMcpText: selectedMcpServers.value.length > 0 ? selectedMcpServers.value.join(' · ') : '-',
    }
  }

  const selectedSkillsCountText = computed(() => {
    const c = selectedSkills.value.length
    return c > 0 ? `已选择 ${c} 项` : '未选择'
  })

  const selectedMcpCountText = computed(() => {
    const c = selectedMcpServers.value.length
    return c > 0 ? `已选择 ${c} 项` : '未选择'
  })

  // --- Model modal ---
  function getModelProviderOptions(catalog) {
    const vals = new Set(catalog.availableModelItems.map(i => i.provider || '-'))
    return ['全部', ...Array.from(vals).filter(v => v && v !== '-').sort()]
  }

  function getFilteredModelItems(catalog) {
    const pf = modelProviderDraft.value
    const kw = modelSearchDraft.value.trim().toLowerCase()
    return catalog.availableModelItems.filter(item => {
      const p = item.provider || '-'
      if (pf !== '全部' && pf && p !== pf) return false
      if (!kw) return true
      return `${item.name} ${p}`.toLowerCase().includes(kw)
    })
  }

  function openModelModal(catalog) {
    tempSelectedModel.value = selectedModel.value
    const cp = catalog.availableModelItems.find(i => i.name === selectedModel.value)?.provider || ''
    modelProviderDraft.value = cp || '全部'
    modelSearchDraft.value = ''
    isModelModalOpen.value = true
  }

  function closeModelModal() { isModelModalOpen.value = false }
  function selectTempModel(name) { tempSelectedModel.value = name }

  async function applyModelModalSelection() {
    if (tempSelectedModel.value) selectedModel.value = tempSelectedModel.value
    await persistRuntimePreferences()
    isModelModalOpen.value = false
  }

  // --- Skill modal ---
  function getFilteredSkillItems(catalog) {
    const kw = skillSearchDraft.value.trim().toLowerCase()
    if (!kw) return catalog.availableSkillItems
    return catalog.availableSkillItems.filter(i => (i.name?.toLowerCase() || '').includes(kw) || (i.description?.toLowerCase() || '').includes(kw))
  }

  function openSkillModal() {
    tempSelectedSkills.value = [...selectedSkills.value]
    skillSearchDraft.value = ''
    isSkillModalOpen.value = true
  }

  function closeSkillModal() { isSkillModalOpen.value = false }

  async function applySkillModalSelection() {
    selectedSkills.value = [...tempSelectedSkills.value]
    await persistRuntimePreferences()
    isSkillModalOpen.value = false
  }

  function toggleTempSkill(name) {
    const n = new Set(tempSelectedSkills.value)
    n.has(name) ? n.delete(name) : n.add(name)
    tempSelectedSkills.value = [...n]
  }

  function isTempSkillChecked(name) { return tempSelectedSkills.value.includes(name) }

  // --- MCP modal ---
  function getFilteredMcpItems(catalog) {
    const kw = mcpSearchDraft.value.trim().toLowerCase()
    if (!kw) return catalog.availableMcpServers
    return catalog.availableMcpServers.filter(i => i.toLowerCase().includes(kw))
  }

  function openMcpModal() {
    tempSelectedMcpServers.value = [...selectedMcpServers.value]
    mcpSearchDraft.value = ''
    isMcpModalOpen.value = true
  }

  function closeMcpModal() { isMcpModalOpen.value = false }

  async function applyMcpModalSelection() {
    selectedMcpServers.value = [...tempSelectedMcpServers.value]
    await persistRuntimePreferences()
    isMcpModalOpen.value = false
  }

  function toggleTempMcp(name) {
    const n = new Set(tempSelectedMcpServers.value)
    n.has(name) ? n.delete(name) : n.add(name)
    tempSelectedMcpServers.value = [...n]
  }

  function isTempMcpChecked(name) { return tempSelectedMcpServers.value.includes(name) }

  // --- Persist ---
  async function persistRuntimePreferences() {
    const payload = {
      selected_model: selectedModel.value || null,
      selected_skills: selectedSkills.value,
      selected_mcp_servers: selectedMcpServers.value,
    }
    const runtime = await putJson(`${apiBase}/api/v1/runtime/preferences`, payload)
    const modelCands = runtime.available_models ?? []
    const smfs = runtime.selected_model ?? ''
    selectedModel.value = modelCands.includes(smfs) ? smfs : (modelCands[0] || smfs)
    const scs = new Set(runtime.available_skills ?? [])
    selectedSkills.value = (runtime.selected_skills ?? []).filter(s => scs.has(s))
    const mcs = new Set(runtime.available_mcp_servers ?? [])
    selectedMcpServers.value = (runtime.selected_mcp_servers ?? []).filter(s => mcs.has(s))
  }

  function syncRuntimeSelectionsFromCockpit(cockpit) {
    const runtime = cockpit?.runtime
    if (!runtime) { selectedModel.value = ''; selectedSkills.value = []; selectedMcpServers.value = []; return }
    const mc = runtime.available_models ?? []
    const smfs = runtime.selected_model ?? ''
    selectedModel.value = mc.includes(smfs) ? smfs : (mc[0] || smfs)
    const scs = new Set(runtime.available_skills ?? [])
    selectedSkills.value = (runtime.selected_skills ?? []).filter(s => scs.has(s))
    const mcs = new Set(runtime.available_mcp_servers ?? [])
    selectedMcpServers.value = (runtime.selected_mcp_servers ?? []).filter(s => mcs.has(s))
  }

  // --- System Config ---
  async function loadSystemConfig() {
    try {
      const data = await fetchJson(`${apiBase}/api/v1/system/config`)
      githubTokenConfigured.value = Boolean(data?.github_token_configured)
    } catch { githubTokenConfigured.value = false }
  }

  async function saveGithubToken() {
    if (githubTokenSaving.value) return
    githubTokenSaving.value = true
    try {
      const data = await putJson(`${apiBase}/api/v1/system/config/github-token`, { github_token: githubTokenDraft.value.trim() })
      githubTokenConfigured.value = Boolean(data?.github_token_configured)
      githubTokenDraft.value = ''
    } finally { githubTokenSaving.value = false }
  }

  return {
    selectedModel, selectedSkills, selectedMcpServers,
    isModelModalOpen, isSkillModalOpen, isMcpModalOpen,
    tempSelectedModel, tempSelectedSkills, tempSelectedMcpServers,
    modelProviderDraft, modelSearchDraft, skillSearchDraft, mcpSearchDraft,
    githubTokenConfigured, githubTokenDraft, githubTokenSaving,
    makeRuntimeCatalog, selectedSkillsCountText, selectedMcpCountText,
    getModelProviderOptions, getFilteredModelItems,
    openModelModal, closeModelModal, selectTempModel, applyModelModalSelection,
    getFilteredSkillItems, openSkillModal, closeSkillModal,
    applySkillModalSelection, toggleTempSkill, isTempSkillChecked,
    getFilteredMcpItems, openMcpModal, closeMcpModal,
    applyMcpModalSelection, toggleTempMcp, isTempMcpChecked,
    persistRuntimePreferences, syncRuntimeSelectionsFromCockpit,
    loadSystemConfig, saveGithubToken,
  }
})
