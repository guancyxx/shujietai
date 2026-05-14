import { computed, ref } from 'vue'
import { fetchJson, putJson } from '../services/apiClient.js'

const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:18000'

/**
 * Runtime configuration composable — model / skill / MCP selection state.
 *
 * Accepts a `cockpitRef` (Ref<object|null>) so it can sync selections from
 * the cockpit response without creating a hard circular dependency.
 */
export function useRuntimeConfig(cockpitRef) {
  // --- Persisted selections ---
  const selectedModel = ref('')
  const selectedSkills = ref([])
  const selectedMcpServers = ref([])

  // --- Modal open/close state ---
  const isModelModalOpen = ref(false)
  const isSkillModalOpen = ref(false)
  const isMcpModalOpen = ref(false)

  // --- Temporary draft selections (inside modal, not yet applied) ---
  const modelSearchDraft = ref('')
  const modelProviderDraft = ref('')
  const tempSelectedModel = ref('')
  const skillSearch = ref('')
  const mcpSearch = ref('')
  const skillSearchDraft = ref('')
  const mcpSearchDraft = ref('')
  const tempSelectedSkills = ref([])
  const tempSelectedMcpServers = ref([])

  // --- System config ---
  const systemConfig = ref(null)

  async function loadSystemConfig() {
    try {
      systemConfig.value = await fetchJson(`${apiBase}/api/v1/system/config`)
    } catch (e) {
      console.warn('Failed to load system config', e)
    }
  }

  // --- Runtime summary (derived from cockpit) ---
  const runtimeSummary = computed(() => {
    const runtime = cockpitRef?.value?.runtime
    const skillItems = runtime?.available_skill_items ?? []
    const modelItems = runtime?.available_model_items ?? []
    const modelProviderMap = Object.fromEntries(modelItems.map((item) => [item.name, item.provider || '-']))
    const selectedProvider = runtime?.selected_model_provider || modelProviderMap[selectedModel.value] || '-'
    return {
      availableModels: runtime?.available_models ?? [],
      availableModelItems: modelItems,
      selectedModelProvider: selectedProvider,
      currentModelProvider: runtime?.current_model_provider || '-',
      availableSkills: runtime?.available_skills ?? [],
      availableSkillItems: skillItems,
      availableMcpServers: runtime?.available_mcp_servers ?? [],
      availablePlatforms: runtime?.available_platforms ?? ['hermes'],
      selectedModelText: selectedModel.value || '-',
      selectedSkillsText: selectedSkills.value.length > 0 ? selectedSkills.value.join(' · ') : '-',
      selectedMcpText: selectedMcpServers.value.length > 0 ? selectedMcpServers.value.join(' · ') : '-',
    }
  })

  const modelRuntimeCatalog = computed(() => runtimeSummary.value)
  const skillRuntimeCatalog = computed(() => runtimeSummary.value)
  const mcpRuntimeCatalog = computed(() => runtimeSummary.value)

  // --- Filtered lists for modal search ---
  const modelProviderOptions = computed(() => {
    const values = new Set(modelRuntimeCatalog.value.availableModelItems.map((item) => item.provider || '-'))
    return ['全部', ...Array.from(values).filter((v) => v && v !== '-').sort()]
  })

  const filteredModelItems = computed(() => {
    const providerFilter = modelProviderDraft.value
    const keyword = modelSearchDraft.value.trim().toLowerCase()
    return modelRuntimeCatalog.value.availableModelItems.filter((item) => {
      const provider = item.provider || '-'
      const providerMatched = providerFilter === '全部' || !providerFilter ? true : provider === providerFilter
      if (!providerMatched) return false
      if (!keyword) return true
      return `${item.name} ${provider}`.toLowerCase().includes(keyword)
    })
  })

  const filteredSkillItems = computed(() => {
    const keyword = skillSearchDraft.value.trim().toLowerCase()
    if (!keyword) return skillRuntimeCatalog.value.availableSkillItems
    return skillRuntimeCatalog.value.availableSkillItems.filter((item) => {
      const name = item.name?.toLowerCase() ?? ''
      const description = item.description?.toLowerCase() ?? ''
      return name.includes(keyword) || description.includes(keyword)
    })
  })

  const filteredMcpItems = computed(() => {
    const keyword = mcpSearchDraft.value.trim().toLowerCase()
    if (!keyword) return mcpRuntimeCatalog.value.availableMcpServers
    return mcpRuntimeCatalog.value.availableMcpServers.filter((item) => item.toLowerCase().includes(keyword))
  })

  const selectedSkillsCountText = computed(() => {
    const count = selectedSkills.value.length
    return count > 0 ? `已选择 ${count} 项` : '未选择'
  })

  const selectedMcpCountText = computed(() => {
    const count = selectedMcpServers.value.length
    return count > 0 ? `已选择 ${count} 项` : '未选择'
  })

  // --- Sync from cockpit response ---
  function syncRuntimeSelectionsFromCockpit() {
    const runtime = cockpitRef?.value?.runtime
    if (!runtime) {
      selectedModel.value = ''
      selectedSkills.value = []
      selectedMcpServers.value = []
      return
    }

    const modelCandidates = runtime.available_models ?? []
    const selectedModelFromServer = runtime.selected_model ?? ''
    selectedModel.value = modelCandidates.includes(selectedModelFromServer)
      ? selectedModelFromServer
      : (modelCandidates[0] || selectedModelFromServer)

    const skillCandidates = new Set(runtime.available_skills ?? [])
    selectedSkills.value = (runtime.selected_skills ?? []).filter((item) => skillCandidates.has(item))

    const mcpCandidates = new Set(runtime.available_mcp_servers ?? [])
    selectedMcpServers.value = (runtime.selected_mcp_servers ?? []).filter((item) => mcpCandidates.has(item))
  }

  // --- Persist preferences to backend ---
  async function persistRuntimePreferences() {
    const payload = {
      selected_model: selectedModel.value || null,
      selected_skills: selectedSkills.value,
      selected_mcp_servers: selectedMcpServers.value,
    }
    const runtime = await putJson(`${apiBase}/api/v1/runtime/preferences`, payload)

    const modelCandidates = runtime.available_models ?? []
    const selectedModelFromServer = runtime.selected_model ?? ''
    selectedModel.value = modelCandidates.includes(selectedModelFromServer)
      ? selectedModelFromServer
      : (modelCandidates[0] || selectedModelFromServer)

    const skillCandidates = new Set(runtime.available_skills ?? [])
    selectedSkills.value = (runtime.selected_skills ?? []).filter((item) => skillCandidates.has(item))

    const mcpCandidates = new Set(runtime.available_mcp_servers ?? [])
    selectedMcpServers.value = (runtime.selected_mcp_servers ?? []).filter((item) => mcpCandidates.has(item))
  }

  // --- Model modal actions ---
  function openModelModal() {
    tempSelectedModel.value = selectedModel.value
    const currentProvider = runtimeSummary.value.availableModelItems.find(
      (item) => item.name === selectedModel.value,
    )?.provider || ''
    modelProviderDraft.value = currentProvider || '全部'
    modelSearchDraft.value = ''
    isModelModalOpen.value = true
  }

  function closeModelModal() {
    isModelModalOpen.value = false
  }

  async function applyModelModalSelection() {
    if (tempSelectedModel.value) selectedModel.value = tempSelectedModel.value
    await persistRuntimePreferences()
    isModelModalOpen.value = false
  }

  function selectTempModel(name) {
    tempSelectedModel.value = name
  }

  // --- Skill modal actions ---
  function openSkillModal() {
    tempSelectedSkills.value = [...selectedSkills.value]
    skillSearchDraft.value = skillSearch.value
    isSkillModalOpen.value = true
  }

  function closeSkillModal() {
    isSkillModalOpen.value = false
  }

  async function applySkillModalSelection() {
    selectedSkills.value = [...tempSelectedSkills.value]
    skillSearch.value = skillSearchDraft.value
    await persistRuntimePreferences()
    isSkillModalOpen.value = false
  }

  function toggleTempSkill(name) {
    const next = new Set(tempSelectedSkills.value)
    if (next.has(name)) { next.delete(name) } else { next.add(name) }
    tempSelectedSkills.value = [...next]
  }

  function isTempSkillChecked(name) {
    return tempSelectedSkills.value.includes(name)
  }

  // --- MCP modal actions ---
  function openMcpModal() {
    tempSelectedMcpServers.value = [...selectedMcpServers.value]
    mcpSearchDraft.value = mcpSearch.value
    isMcpModalOpen.value = true
  }

  function closeMcpModal() {
    isMcpModalOpen.value = false
  }

  async function applyMcpModalSelection() {
    selectedMcpServers.value = [...tempSelectedMcpServers.value]
    mcpSearch.value = mcpSearchDraft.value
    await persistRuntimePreferences()
    isMcpModalOpen.value = false
  }

  function toggleTempMcp(name) {
    const next = new Set(tempSelectedMcpServers.value)
    if (next.has(name)) { next.delete(name) } else { next.add(name) }
    tempSelectedMcpServers.value = [...next]
  }

  function isTempMcpChecked(name) {
    return tempSelectedMcpServers.value.includes(name)
  }

  return {
    // State
    selectedModel,
    selectedSkills,
    selectedMcpServers,
    systemConfig,
    isModelModalOpen,
    isSkillModalOpen,
    isMcpModalOpen,
    modelSearchDraft,
    modelProviderDraft,
    tempSelectedModel,
    skillSearch,
    mcpSearch,
    skillSearchDraft,
    mcpSearchDraft,
    tempSelectedSkills,
    tempSelectedMcpServers,
    // Computed
    runtimeSummary,
    modelRuntimeCatalog,
    skillRuntimeCatalog,
    mcpRuntimeCatalog,
    modelProviderOptions,
    filteredModelItems,
    filteredSkillItems,
    filteredMcpItems,
    selectedSkillsCountText,
    selectedMcpCountText,
    // Actions
    loadSystemConfig,
    syncRuntimeSelectionsFromCockpit,
    persistRuntimePreferences,
    openModelModal,
    closeModelModal,
    applyModelModalSelection,
    selectTempModel,
    openSkillModal,
    closeSkillModal,
    applySkillModalSelection,
    toggleTempSkill,
    isTempSkillChecked,
    openMcpModal,
    closeMcpModal,
    applyMcpModalSelection,
    toggleTempMcp,
    isTempMcpChecked,
  }
}
