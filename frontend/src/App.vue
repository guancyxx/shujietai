<script setup>
import { computed, onMounted, ref, watch } from 'vue'

const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:18000'

const sessions = ref([])
const selectedSessionId = ref('')
const selectedExternalSessionId = ref('')
const timeline = ref({ messages: [], events: [] })
const cockpit = ref(null)
const loading = ref(false)
const errorMessage = ref('')
const selectedModel = ref('')
const selectedSkills = ref([])
const selectedMcpServers = ref([])
const isModelModalOpen = ref(false)
const isSkillModalOpen = ref(false)
const isMcpModalOpen = ref(false)
const isCreateConversationModalOpen = ref(false)
const modelSearchDraft = ref('')
const modelProviderDraft = ref('')
const tempSelectedModel = ref('')
const skillSearch = ref('')
const mcpSearch = ref('')
const skillSearchDraft = ref('')
const mcpSearchDraft = ref('')
const tempSelectedSkills = ref([])
const tempSelectedMcpServers = ref([])
const createConversationPlatform = ref('hermes')
const createConversationInitialMessage = ref('')
const creatingConversation = ref(false)
const sending = ref(false)
const deletingSessionId = ref('')
const clearingSessions = ref(false)
const composerText = ref('')
const activePage = ref('chat')
const projects = ref([])
const githubRepos = ref([])
const projectSearch = ref('')
const creatingProject = ref(false)
const updatingProject = ref(false)
const deletingProjectId = ref('')
const creatingGithubRepo = ref(false)
const githubTokenDraft = ref('')
const githubTokenSaving = ref(false)
const githubTokenConfigured = ref(false)
const taskBoardItems = ref([])
const taskBoardProjectFilter = ref('')
const taskBoardKeyword = ref('')
const taskBoardStatusFilter = ref('')
const isTaskBoardCreateModalOpen = ref(false)
const isTaskBoardEditModalOpen = ref(false)
const creatingTaskBoardItem = ref(false)
const updatingTaskBoardItem = ref(false)
const deletingTaskBoardItemId = ref('')
const editingTaskBoardItemId = ref('')
const taskBoardCreateForm = ref({
  name: '',
  description: '',
  ai_platform: 'hermes',
  project_id: '',
  upstream_task_id: '',
  parent_task_id: '',
  status: 'draft',
})
const taskBoardEditForm = ref({
  name: '',
  description: '',
  ai_platform: 'hermes',
  project_id: '',
  upstream_task_id: '',
  parent_task_id: '',
  status: 'draft',
})
const isProjectCreateModalOpen = ref(false)
const isProjectEditModalOpen = ref(false)
const createRepoEnabled = ref(false)
const createProjectForm = ref({
  repository_url: '',
  name: '',
  description: '',
  private: false,
})
const editProjectId = ref('')
const editProjectForm = ref({
  name: '',
  description: '',
})

const selectedSession = computed(() => sessions.value.find((s) => s.id === selectedSessionId.value) || null)

const filteredProjects = computed(() => {
  const keyword = projectSearch.value.trim().toLowerCase()
  if (!keyword) {
    return projects.value
  }
  return projects.value.filter((item) => {
    const text = `${item.code} ${item.name} ${item.description} ${item.repository_name} ${item.repository_url}`.toLowerCase()
    return text.includes(keyword)
  })
})

const taskBoardStatusOptions = [
  { value: 'draft', label: '草稿' },
  { value: 'in_progress', label: '进行中' },
  { value: 'blocked', label: '阻塞' },
  { value: 'completed', label: '已完成' },
  { value: 'cancelled', label: '取消' },
]

const taskBoardStatusLabelMap = {
  draft: '草稿',
  in_progress: '进行中',
  blocked: '阻塞',
  completed: '已完成',
  cancelled: '取消',
}

const taskBoardProjectOptions = computed(() => [
  { value: '', label: '全部项目' },
  ...projects.value.map((item) => ({ value: item.id, label: `${item.name}（${item.code}）` })),
])

const taskBoardDependencyOptions = computed(() => taskBoardItems.value.map((item) => ({ value: item.id, label: item.name })))

const taskBoardStatusFilterOptions = computed(() => [
  { value: '', label: '全部状态' },
  ...taskBoardStatusOptions,
])

const filteredTaskBoardItems = computed(() => {
  const keyword = taskBoardKeyword.value.trim().toLowerCase()
  const projectId = taskBoardProjectFilter.value.trim()
  const statusFilter = taskBoardStatusFilter.value.trim()
  return taskBoardItems.value.filter((item) => {
    const projectMatched = !projectId || item.project_id === projectId
    if (!projectMatched) {
      return false
    }
    const statusMatched = !statusFilter || item.status === statusFilter
    if (!statusMatched) {
      return false
    }
    if (!keyword) {
      return true
    }
    const text = `${item.name} ${item.description} ${item.ai_platform} ${item.project_name || ''}`.toLowerCase()
    return text.includes(keyword)
  })
})

const selectedCreateRepo = computed(() => {
  if (!createProjectForm.value.repository_url) {
    return null
  }
  return githubRepos.value.find((repo) => repo.url === createProjectForm.value.repository_url) || null
})

const laneTitleMap = {
  todo: '待处理',
  doing: '进行中',
  done: '已完成',
}

const roleLabelMap = {
  user: '用户',
  assistant: '助手',
  system: '系统',
  tool: '工具',
}

const taskLanes = computed(() => {
  const laneMap = { todo: [], doing: [], done: [] }
  if (!cockpit.value) {
    return laneMap
  }
  for (const task of cockpit.value.tasks || []) {
    laneMap[task.lane]?.push(task)
  }
  return laneMap
})

const runtimeSummary = computed(() => {
  const runtime = cockpit.value?.runtime
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
    selectedModelText: selectedModel.value || '-',
    selectedSkillsText: selectedSkills.value.length > 0 ? selectedSkills.value.join(' · ') : '-',
    selectedMcpText: selectedMcpServers.value.length > 0 ? selectedMcpServers.value.join(' · ') : '-',
  }
})

function getCatalog() {
  return runtimeSummary.value
}

const modelRuntimeCatalog = computed(() => getCatalog())
const skillRuntimeCatalog = computed(() => getCatalog())
const mcpRuntimeCatalog = computed(() => getCatalog())

const selectedSkillsCountText = computed(() => {
  const count = selectedSkills.value.length
  return count > 0 ? `已选择 ${count} 项` : '未选择'
})

const selectedMcpCountText = computed(() => {
  const count = selectedMcpServers.value.length
  return count > 0 ? `已选择 ${count} 项` : '未选择'
})

const platformOptions = computed(() => {
  const values = new Set(['hermes'])
  for (const item of sessions.value) {
    if (item?.platform) {
      values.add(item.platform)
    }
  }
  return Array.from(values)
})

const modelProviderOptions = computed(() => {
  const values = new Set(modelRuntimeCatalog.value.availableModelItems.map((item) => item.provider || '-'))
  return ['全部', ...Array.from(values).filter((value) => value && value !== '-').sort()]
})

const filteredModelItems = computed(() => {
  const providerFilter = modelProviderDraft.value
  const keyword = modelSearchDraft.value.trim().toLowerCase()
  return modelRuntimeCatalog.value.availableModelItems.filter((item) => {
    const provider = item.provider || '-'
    const providerMatched = providerFilter === '全部' || !providerFilter ? true : provider === providerFilter
    if (!providerMatched) {
      return false
    }
    if (!keyword) {
      return true
    }
    const text = `${item.name} ${provider}`.toLowerCase()
    return text.includes(keyword)
  })
})

const filteredSkillItems = computed(() => {
  const keyword = skillSearchDraft.value.trim().toLowerCase()
  if (!keyword) {
    return skillRuntimeCatalog.value.availableSkillItems
  }
  return skillRuntimeCatalog.value.availableSkillItems.filter((item) => {
    const name = item.name?.toLowerCase() ?? ''
    const description = item.description?.toLowerCase() ?? ''
    return name.includes(keyword) || description.includes(keyword)
  })
})

const filteredMcpItems = computed(() => {
  const keyword = mcpSearchDraft.value.trim().toLowerCase()
  if (!keyword) {
    return mcpRuntimeCatalog.value.availableMcpServers
  }
  return mcpRuntimeCatalog.value.availableMcpServers.filter((item) => item.toLowerCase().includes(keyword))
})

function syncRuntimeSelectionsFromCockpit() {
  const runtime = cockpit.value?.runtime
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

function openModelModal() {
  tempSelectedModel.value = selectedModel.value
  const currentProvider = runtimeSummary.value.availableModelItems.find((item) => item.name === selectedModel.value)?.provider || ''
  modelProviderDraft.value = currentProvider || '全部'
  modelSearchDraft.value = ''
  isModelModalOpen.value = true
}

function closeModelModal() {
  isModelModalOpen.value = false
}

async function applyModelModalSelection() {
  if (tempSelectedModel.value) {
    selectedModel.value = tempSelectedModel.value
  }
  await persistRuntimePreferences()
  isModelModalOpen.value = false
}

function selectTempModel(name) {
  tempSelectedModel.value = name
}

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
  if (next.has(name)) {
    next.delete(name)
  } else {
    next.add(name)
  }
  tempSelectedSkills.value = [...next]
}

function isTempSkillChecked(name) {
  return tempSelectedSkills.value.includes(name)
}

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
  if (next.has(name)) {
    next.delete(name)
  } else {
    next.add(name)
  }
  tempSelectedMcpServers.value = [...next]
}

function isTempMcpChecked(name) {
  return tempSelectedMcpServers.value.includes(name)
}

function laneClass(lane) {
  return `lane-${lane}`
}

function taskBoardStatusClass(status) {
  return `task-status-${status || 'draft'}`
}

function resetCreateConversationForm() {
  createConversationPlatform.value = selectedSession.value?.platform || 'hermes'
  createConversationInitialMessage.value = ''
}

function openCreateConversationModal() {
  resetCreateConversationForm()
  isCreateConversationModalOpen.value = true
}

function closeCreateConversationModal() {
  if (creatingConversation.value) {
    return
  }
  isCreateConversationModalOpen.value = false
}

async function submitCreateConversation() {
  const trimmed = createConversationInitialMessage.value.trim()
  if (!trimmed || creatingConversation.value) {
    return
  }

  creatingConversation.value = true
  errorMessage.value = ''
  try {
    const externalSessionId = `web_${Date.now()}`
    const payload = {
      external_session_id: externalSessionId,
      title: 'Web Chat Session',
      platform: createConversationPlatform.value || 'hermes',
      user_message: trimmed,
    }
    await postJson(`${apiBase}/api/v1/connectors/hermes/chat`, payload)
    isCreateConversationModalOpen.value = false
    composerText.value = ''
    await loadSessions()
    const matched = sessions.value.find((item) => item.external_session_id === externalSessionId)
    if (matched) {
      selectedSessionId.value = matched.id
      selectedExternalSessionId.value = matched.external_session_id
    }
    await loadSessionData()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    creatingConversation.value = false
  }
}

function createNewConversation() {
  openCreateConversationModal()
}

function selectConversation(sessionId, externalSessionId) {
  selectedSessionId.value = sessionId
  selectedExternalSessionId.value = externalSessionId
}

function roleClass(role) {
  return `role-${role || 'assistant'}`
}

function messageSideClass(role) {
  return role === 'user' ? 'msg-user' : 'msg-assistant'
}

function formatSessionTime(value) {
  if (!value) {
    return '-'
  }
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return '-'
  }
  return parsed.toLocaleString()
}

async function fetchJson(url) {
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }
  return response.json()
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }
  return response.json()
}

async function putJson(url, payload) {
  const response = await fetch(url, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }
  return response.json()
}

async function patchJson(url, payload) {
  const response = await fetch(url, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }
  return response.json()
}

async function deleteJson(url) {
  const response = await fetch(url, { method: 'DELETE' })
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }
  return response.json()
}

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

async function loadSessions() {
  const data = await fetchJson(`${apiBase}/api/v1/sessions`)
  sessions.value = data
  if (!selectedSessionId.value && data.length > 0) {
    selectedSessionId.value = data[0].id
    selectedExternalSessionId.value = data[0].external_session_id
    return
  }

  if (selectedSessionId.value) {
    const matchedById = data.find((item) => item.id === selectedSessionId.value)
    if (matchedById) {
      selectedExternalSessionId.value = matchedById.external_session_id
      return
    }
  }

  if (selectedExternalSessionId.value) {
    const matchedByExternal = data.find((item) => item.external_session_id === selectedExternalSessionId.value)
    if (matchedByExternal) {
      selectedSessionId.value = matchedByExternal.id
      return
    }
  }

  if (data.length > 0) {
    selectedSessionId.value = data[0].id
    selectedExternalSessionId.value = data[0].external_session_id
  } else {
    selectedSessionId.value = ''
    selectedExternalSessionId.value = ''
  }
}

async function loadSessionData() {
  if (!selectedSessionId.value) {
    return
  }
  const [timelineData, cockpitData] = await Promise.all([
    fetchJson(`${apiBase}/api/v1/sessions/${selectedSessionId.value}/timeline`),
    fetchJson(`${apiBase}/api/v1/board/cockpit?session_id=${selectedSessionId.value}`),
  ])
  timeline.value = timelineData
  cockpit.value = cockpitData
  syncRuntimeSelectionsFromCockpit()
}

async function refreshData() {
  loading.value = true
  errorMessage.value = ''
  try {
    await Promise.all([loadSessions(), loadProjects(), loadTaskBoardItems(), loadGithubRepos(), loadSystemConfig()])
    await loadSessionData()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    loading.value = false
  }
}

function resetCreateProjectForm() {
  createRepoEnabled.value = false
  createProjectForm.value = {
    repository_url: githubRepos.value[0]?.url || '',
    name: '',
    description: '',
    private: false,
  }
}

function openProjectCreateModal() {
  resetCreateProjectForm()
  isProjectCreateModalOpen.value = true
}

function closeProjectCreateModal() {
  if (creatingProject.value) {
    return
  }
  isProjectCreateModalOpen.value = false
}

function closeProjectEditModal() {
  if (updatingProject.value) {
    return
  }
  isProjectEditModalOpen.value = false
  editProjectId.value = ''
}

function openProjectEditModal(item) {
  editProjectId.value = item.id
  editProjectForm.value = {
    name: item.name,
    description: item.description || '',
  }
  isProjectEditModalOpen.value = true
}

function getRepoChoices() {
  return githubRepos.value
}

function handleRepositoryChange() {
  const repo = selectedCreateRepo.value
  if (!repo) {
    return
  }

  if (!createProjectForm.value.name.trim()) {
    createProjectForm.value.name = repo.name
  }

  if (!createProjectForm.value.description.trim() && repo.description?.trim()) {
    createProjectForm.value.description = repo.description.trim()
  }
}

async function loadProjects() {
  const data = await fetchJson(`${apiBase}/api/v1/projects`)
  projects.value = data.items || []
}

async function loadTaskBoardItems() {
  const params = new URLSearchParams()
  if (taskBoardProjectFilter.value.trim()) {
    params.set('project_id', taskBoardProjectFilter.value.trim())
  }
  if (taskBoardKeyword.value.trim()) {
    params.set('keyword', taskBoardKeyword.value.trim())
  }
  const query = params.toString()
  const endpoint = query ? `${apiBase}/api/v1/task-board?${query}` : `${apiBase}/api/v1/task-board`
  const data = await fetchJson(endpoint)
  taskBoardItems.value = data.items || []
}

function resetTaskBoardCreateForm() {
  taskBoardCreateForm.value = {
    name: '',
    description: '',
    ai_platform: 'hermes',
    project_id: '',
    upstream_task_id: '',
    parent_task_id: '',
    status: 'draft',
  }
}

function openTaskBoardByProject(project) {
  taskBoardProjectFilter.value = project.id
  taskBoardKeyword.value = ''
  taskBoardStatusFilter.value = ''
  activePage.value = 'task-board'
}

function openTaskBoardCreateModal() {
  resetTaskBoardCreateForm()
  isTaskBoardCreateModalOpen.value = true
}

function closeTaskBoardCreateModal() {
  if (creatingTaskBoardItem.value) {
    return
  }
  isTaskBoardCreateModalOpen.value = false
}

function openTaskBoardEditModal(item) {
  editingTaskBoardItemId.value = item.id
  taskBoardEditForm.value = {
    name: item.name,
    description: item.description || '',
    ai_platform: item.ai_platform || 'hermes',
    project_id: item.project_id || '',
    upstream_task_id: item.upstream_task_id || '',
    parent_task_id: item.parent_task_id || '',
    status: item.status || 'draft',
  }
  isTaskBoardEditModalOpen.value = true
}

function closeTaskBoardEditModal() {
  if (updatingTaskBoardItem.value) {
    return
  }
  isTaskBoardEditModalOpen.value = false
  editingTaskBoardItemId.value = ''
}

function buildTaskBoardPayload(formState) {
  return {
    name: formState.name.trim(),
    description: formState.description.trim(),
    ai_platform: formState.ai_platform.trim() || 'hermes',
    status: formState.status,
    project_id: formState.project_id || null,
    upstream_task_id: formState.upstream_task_id || null,
    parent_task_id: formState.parent_task_id || null,
  }
}

async function submitCreateTaskBoardItem() {
  if (creatingTaskBoardItem.value || !taskBoardCreateForm.value.name.trim()) {
    return
  }
  creatingTaskBoardItem.value = true
  errorMessage.value = ''
  try {
    await postJson(`${apiBase}/api/v1/task-board`, buildTaskBoardPayload(taskBoardCreateForm.value))
    isTaskBoardCreateModalOpen.value = false
    await loadTaskBoardItems()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    creatingTaskBoardItem.value = false
  }
}

async function submitEditTaskBoardItem() {
  if (updatingTaskBoardItem.value || !editingTaskBoardItemId.value || !taskBoardEditForm.value.name.trim()) {
    return
  }
  updatingTaskBoardItem.value = true
  errorMessage.value = ''
  try {
    await patchJson(`${apiBase}/api/v1/task-board/${editingTaskBoardItemId.value}`, buildTaskBoardPayload(taskBoardEditForm.value))
    isTaskBoardEditModalOpen.value = false
    editingTaskBoardItemId.value = ''
    await loadTaskBoardItems()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    updatingTaskBoardItem.value = false
  }
}

async function deleteTaskBoardItem(item) {
  if (!item?.id || deletingTaskBoardItemId.value) {
    return
  }
  const confirmed = window.confirm(`确认删除任务「${item.name}」？`)
  if (!confirmed) {
    return
  }
  deletingTaskBoardItemId.value = item.id
  errorMessage.value = ''
  try {
    await deleteJson(`${apiBase}/api/v1/task-board/${item.id}`)
    await loadTaskBoardItems()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    deletingTaskBoardItemId.value = ''
  }
}

async function loadGithubRepos() {
  try {
    const data = await fetchJson(`${apiBase}/api/v1/projects/github/repos`)
    githubRepos.value = data || []
    if (!createProjectForm.value.repository_url && githubRepos.value.length > 0) {
      createProjectForm.value.repository_url = githubRepos.value[0].url
    }
  } catch {
    githubRepos.value = []
  }
}

async function loadSystemConfig() {
  try {
    const data = await fetchJson(`${apiBase}/api/v1/system/config`)
    githubTokenConfigured.value = Boolean(data?.github_token_configured)
  } catch {
    githubTokenConfigured.value = false
  }
}

async function saveGithubToken() {
  if (githubTokenSaving.value) {
    return
  }
  githubTokenSaving.value = true
  errorMessage.value = ''
  try {
    const payload = { github_token: githubTokenDraft.value.trim() }
    const data = await putJson(`${apiBase}/api/v1/system/config/github-token`, payload)
    githubTokenConfigured.value = Boolean(data?.github_token_configured)
    githubTokenDraft.value = ''
    await loadGithubRepos()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    githubTokenSaving.value = false
  }
}

async function createGithubRepo() {
  if (creatingGithubRepo.value || !createProjectForm.value.name.trim()) {
    return
  }
  creatingGithubRepo.value = true
  errorMessage.value = ''
  try {
    const payload = {
      name: createProjectForm.value.name.trim(),
      description: createProjectForm.value.description.trim(),
      private: Boolean(createProjectForm.value.private),
    }
    const created = await postJson(`${apiBase}/api/v1/projects/github/repos`, payload)
    createProjectForm.value.repository_url = created.url
    await loadGithubRepos()
    await submitCreateProject()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    creatingGithubRepo.value = false
  }
}

async function submitCreateProject() {
  const projectName = createProjectForm.value.name.trim()
  if (creatingProject.value || !projectName) {
    return
  }
  if (!createRepoEnabled.value && !createProjectForm.value.repository_url.trim()) {
    return
  }
  creatingProject.value = true
  errorMessage.value = ''
  try {
    const payload = {
      repository_url: createProjectForm.value.repository_url.trim(),
      name: projectName,
      description: createProjectForm.value.description.trim(),
    }
    await postJson(`${apiBase}/api/v1/projects`, payload)
    isProjectCreateModalOpen.value = false
    await loadProjects()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    creatingProject.value = false
  }
}

async function submitEditProject() {
  if (updatingProject.value || !editProjectId.value || !editProjectForm.value.name.trim()) {
    return
  }
  updatingProject.value = true
  errorMessage.value = ''
  try {
    const payload = {
      name: editProjectForm.value.name.trim(),
      description: editProjectForm.value.description.trim(),
    }
    await patchJson(`${apiBase}/api/v1/projects/${editProjectId.value}`, payload)
    isProjectEditModalOpen.value = false
    editProjectId.value = ''
    await loadProjects()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    updatingProject.value = false
  }
}

async function deleteProject(item) {
  if (!item?.id || deletingProjectId.value) {
    return
  }
  const confirmed = window.confirm(`确认删除项目「${item.name}」？`)
  if (!confirmed) {
    return
  }
  deletingProjectId.value = item.id
  errorMessage.value = ''
  try {
    await deleteJson(`${apiBase}/api/v1/projects/${item.id}`)
    await loadProjects()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    deletingProjectId.value = ''
  }
}

async function deleteSession(sessionId) {
  if (!sessionId || deletingSessionId.value || clearingSessions.value) {
    return
  }

  const target = sessions.value.find((item) => item.id === sessionId)
  const title = target?.title || target?.external_session_id || sessionId
  const confirmed = window.confirm(`确认删除对话「${title}」？`)
  if (!confirmed) {
    return
  }

  deletingSessionId.value = sessionId
  errorMessage.value = ''
  try {
    const response = await fetch(`${apiBase}/api/v1/sessions/${sessionId}`, { method: 'DELETE' })
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status}`)
    }
    if (selectedSessionId.value === sessionId) {
      selectedSessionId.value = ''
      selectedExternalSessionId.value = ''
      timeline.value = { messages: [], events: [] }
      cockpit.value = null
    }
    await loadSessions()
    if (selectedSessionId.value) {
      await loadSessionData()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    deletingSessionId.value = ''
  }
}

async function clearAllSessions() {
  if (clearingSessions.value || deletingSessionId.value || sessions.value.length === 0) {
    return
  }

  const confirmed = window.confirm('确认清空全部对话？此操作不可恢复。')
  if (!confirmed) {
    return
  }

  clearingSessions.value = true
  errorMessage.value = ''
  try {
    const response = await fetch(`${apiBase}/api/v1/sessions`, { method: 'DELETE' })
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status}`)
    }
    selectedSessionId.value = ''
    selectedExternalSessionId.value = ''
    timeline.value = { messages: [], events: [] }
    cockpit.value = null
    await loadSessions()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    clearingSessions.value = false
  }
}

function handleComposerKeydown(event) {
  if (
    event.key !== 'Enter'
    || event.shiftKey
    || event.ctrlKey
    || event.altKey
    || event.metaKey
    || event.isComposing
  ) {
    return
  }
  event.preventDefault()
  sendMessageToHermes()
}

function handleCreateInitialMessageKeydown(event) {
  if (
    event.key !== 'Enter'
    || event.shiftKey
    || event.ctrlKey
    || event.altKey
    || event.metaKey
    || event.isComposing
  ) {
    return
  }
  event.preventDefault()
  submitCreateConversation()
}

async function sendMessageToHermes() {
  const trimmed = composerText.value.trim()
  if (!trimmed || sending.value) {
    return
  }

  sending.value = true
  errorMessage.value = ''
  try {
    const externalSessionId = selectedExternalSessionId.value || selectedSession.value?.external_session_id || `web_${Date.now()}`
    const payload = {
      external_session_id: externalSessionId,
      title: selectedSession.value?.title || 'Web Chat Session',
      user_message: trimmed,
    }
    await postJson(`${apiBase}/api/v1/connectors/hermes/chat`, payload)
    composerText.value = ''
    await loadSessions()
    const matched = sessions.value.find((item) => item.external_session_id === externalSessionId)
    if (matched) {
      selectedSessionId.value = matched.id
      selectedExternalSessionId.value = matched.external_session_id
    }
    await loadSessionData()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    sending.value = false
  }
}

watch(selectedSessionId, async () => {
  if (!selectedSessionId.value) {
    timeline.value = { messages: [], events: [] }
    cockpit.value = null
    return
  }
  try {
    errorMessage.value = ''
    await loadSessionData()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  }
})

watch([taskBoardProjectFilter, taskBoardKeyword], async () => {
  if (activePage.value !== 'task-board') {
    return
  }
  try {
    errorMessage.value = ''
    await loadTaskBoardItems()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  }
})

watch(activePage, async (page) => {
  if (page !== 'task-board') {
    return
  }
  try {
    errorMessage.value = ''
    await Promise.all([loadProjects(), loadTaskBoardItems()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  }
})

onMounted(refreshData)
</script>

<template>
  <main class="app-shell">
    <div class="bg-layer"></div>

    <section class="cockpit-wrap">
      <header class="topbar panel">
        <div class="brand-block">
          <div class="brand-title-row">
            <img class="brand-logo" src="/src/assets/logo-sjt-a3-icon.svg" alt="枢界台 Logo" />
            <h1 class="title">枢界台 · 会话驾驶舱</h1>
          </div>
          <p class="subtitle">全屏自适应 · 多平台对话任务看板</p>
        </div>

        <nav class="top-nav" aria-label="页面切换">
          <button type="button" class="top-nav-btn" :class="{ 'top-nav-btn-active': activePage === 'chat' }" @click="activePage = 'chat'">
            <span class="top-nav-btn-icon" aria-hidden="true">💬</span>
            <span class="top-nav-btn-label">对话页</span>
          </button>
          <button type="button" class="top-nav-btn" :class="{ 'top-nav-btn-active': activePage === 'projects' }" @click="activePage = 'projects'">
            <span class="top-nav-btn-icon" aria-hidden="true">📁</span>
            <span class="top-nav-btn-label">项目管理</span>
          </button>
          <button type="button" class="top-nav-btn" :class="{ 'top-nav-btn-active': activePage === 'task-board' }" @click="activePage = 'task-board'">
            <span class="top-nav-btn-icon" aria-hidden="true">🗂️</span>
            <span class="top-nav-btn-label">任务看板</span>
          </button>
          <button type="button" class="top-nav-btn" :class="{ 'top-nav-btn-active': activePage === 'model-config' }" @click="activePage = 'model-config'">
            <span class="top-nav-btn-icon" aria-hidden="true">🤖</span>
            <span class="top-nav-btn-label">模型配置</span>
          </button>
          <button type="button" class="top-nav-btn" :class="{ 'top-nav-btn-active': activePage === 'system-config' }" @click="activePage = 'system-config'">
            <span class="top-nav-btn-icon" aria-hidden="true">⚙️</span>
            <span class="top-nav-btn-label">系统配置</span>
          </button>
        </nav>
      </header>

      <div v-if="errorMessage" class="error panel">{{ errorMessage }}</div>

      <section v-if="activePage === 'chat'" class="main-grid chat-grid">
        <article class="panel tasks-panel">
          <div class="tasks-panel-header">
            <h2>对话列表</h2>
            <div class="tasks-panel-actions">
              <button type="button" class="session-new-btn" @click="createNewConversation">新建对话</button>
              <button
                type="button"
                class="session-clear-btn"
                :disabled="clearingSessions || deletingSessionId || sessions.length === 0"
                @click="clearAllSessions"
              >
                {{ clearingSessions ? '清空中...' : '清空对话' }}
              </button>
            </div>
          </div>

          <div class="conversation-only-list">
            <div
              v-for="item in sessions"
              :key="item.id"
              class="task conversation-task"
              :class="{ 'conversation-task-active': item.id === selectedSessionId }"
            >
              <button
                type="button"
                class="conversation-task-main"
                @click="selectConversation(item.id, item.external_session_id)"
              >
                <div class="conversation-task-header">
                  <div class="task-title conversation-task-title">{{ item.title }}</div>
                  <span class="conversation-platform-pill">{{ item.platform }}</span>
                </div>
                <div class="conversation-task-subtitle">{{ item.external_session_id }}</div>
                <div class="conversation-task-meta-row">
                  <span class="conversation-meta-label">开始时间</span>
                  <span class="conversation-meta-value">{{ formatSessionTime(item.started_at) }}</span>
                </div>
              </button>
              <button
                type="button"
                class="conversation-delete-btn"
                :aria-label="`删除对话 ${item.title}`"
                :disabled="clearingSessions || deletingSessionId === item.id"
                @click="deleteSession(item.id)"
              >
                <span aria-hidden="true">🗑</span>
              </button>
            </div>
            <div v-if="sessions.length === 0" class="muted">暂无会话</div>
          </div>
        </article>

        <article class="panel timeline-panel">
          <h2>对话时间线</h2>

          <div class="timeline-scroll">
            <div v-if="timeline.messages?.length === 0" class="muted">暂无消息</div>
            <div
              v-for="message in timeline.messages"
              :key="message.id"
              class="timeline-item"
              :class="messageSideClass(message.role)"
            >
              <div class="role-chip" :class="roleClass(message.role)">{{ roleLabelMap[message.role] || message.role }}</div>
              <div class="timeline-meta">{{ new Date(message.created_at).toLocaleString() }}</div>
              <div class="timeline-content">{{ message.content }}</div>
            </div>
          </div>

          <form class="chat-composer" @submit.prevent="sendMessageToHermes">
            <textarea
              v-model="composerText"
              class="composer-input"
              :disabled="sending"
              placeholder="输入消息，直接与 Hermes 对话"
              @keydown="handleComposerKeydown"
            ></textarea>
            <button class="composer-send" type="submit" :disabled="sending || !composerText.trim()">
              {{ sending ? '发送中...' : '发送' }}
            </button>
          </form>
        </article>

        <article class="panel state-panel placeholder-state-panel">
          <h2>会话状态</h2>
          <div class="muted">暂时为空</div>
        </article>
      </section>

      <section v-else-if="activePage === 'projects'" class="main-grid project-grid">
        <article class="panel project-panel">
          <div class="project-panel-header">
            <h2>项目管理</h2>
            <div class="project-actions">
              <input v-model="projectSearch" class="project-search" placeholder="搜索项目名称/编号/仓库" />
              <button type="button" class="session-new-btn" @click="openProjectCreateModal">新建项目</button>
            </div>
          </div>

          <div class="project-list" v-if="filteredProjects.length > 0">
            <div v-for="item in filteredProjects" :key="item.id" class="project-card project-card-clickable" @click="openTaskBoardByProject(item)">
              <div class="project-card-top">
                <div class="project-title-wrap">
                  <div class="project-name">{{ item.name }}</div>
                  <div class="project-code">{{ item.code }}</div>
                </div>
                <div class="project-card-actions">
                  <button type="button" class="project-btn" @click="openProjectEditModal(item)">编辑</button>
                  <button type="button" class="project-btn project-btn-danger" :disabled="deletingProjectId === item.id" @click="deleteProject(item)">
                    {{ deletingProjectId === item.id ? '删除中...' : '删除' }}
                  </button>
                </div>
              </div>
              <div class="project-desc">{{ item.description || '暂无简介' }}</div>
              <div class="project-meta">
                <span class="project-meta-label">仓库</span>
                <span class="project-meta-value">{{ item.repository_name }}</span>
              </div>
              <div class="project-meta">
                <span class="project-meta-label">更新时间</span>
                <span class="project-meta-value">{{ formatSessionTime(item.updated_at) }}</span>
              </div>
            </div>
          </div>
          <div v-else class="project-empty">暂无项目，点击“新建项目”开始。</div>
        </article>
      </section>

<section v-else-if="activePage === 'task-board'" class="main-grid task-board-grid">
        <article class="panel task-board-panel">
          <div class="task-board-panel-header">
            <h2>任务看板</h2>
            <div class="task-board-actions">
              <select v-model="taskBoardProjectFilter" class="task-board-filter-select">
                <option v-for="opt in taskBoardProjectOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
              </select>
              <select v-model="taskBoardStatusFilter" class="task-board-filter-select">
                <option v-for="opt in taskBoardStatusFilterOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
              </select>
              <input v-model="taskBoardKeyword" class="project-search task-board-search" placeholder="搜索任务名称/描述" />
              <button type="button" class="session-new-btn" @click="openTaskBoardCreateModal">新建任务</button>
            </div>
          </div>

          <div class="task-board-list" v-if="filteredTaskBoardItems.length > 0">
            <div v-for="item in filteredTaskBoardItems" :key="item.id" class="task-board-card">
              <div class="task-board-card-top">
                <div class="task-board-title-wrap">
                  <div class="task-board-name">{{ item.name }}</div>
                  <span class="task-board-status-pill" :class="taskBoardStatusClass(item.status)">{{ taskBoardStatusLabelMap[item.status] || item.status }}</span>
                </div>
                <div class="task-board-card-actions">
                  <button type="button" class="project-btn" @click="openTaskBoardEditModal(item)">编辑</button>
                  <button type="button" class="project-btn project-btn-danger" :disabled="deletingTaskBoardItemId === item.id" @click="deleteTaskBoardItem(item)">
                    {{ deletingTaskBoardItemId === item.id ? '删除中...' : '删除' }}
                  </button>
                </div>
              </div>
              <div class="task-board-desc">{{ item.description || '暂无描述' }}</div>
              <div class="task-board-meta-grid">
                <div class="task-board-meta">
                  <span class="task-board-meta-label">AI 平台</span>
                  <span class="task-board-meta-value">{{ item.ai_platform }}</span>
                </div>
                <div class="task-board-meta">
                  <span class="task-board-meta-label">所属项目</span>
                  <span class="task-board-meta-value">{{ item.project_name || '未关联' }}</span>
                </div>
                <div class="task-board-meta" v-if="item.upstream_task_name">
                  <span class="task-board-meta-label">上游依赖</span>
                  <span class="task-board-meta-value">{{ item.upstream_task_name }}</span>
                </div>
                <div class="task-board-meta" v-if="item.parent_task_name">
                  <span class="task-board-meta-label">父任务</span>
                  <span class="task-board-meta-value">{{ item.parent_task_name }}</span>
                </div>
                <div class="task-board-meta">
                  <span class="task-board-meta-label">更新时间</span>
                  <span class="task-board-meta-value">{{ formatSessionTime(item.updated_at) }}</span>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="project-empty">暂无任务，点击"新建任务"开始。</div>
        </article>
      </section>

      <section v-else-if="activePage === 'model-config'" class="main-grid config-grid">
        <article class="panel state-panel config-panel">
          <h2>模型与 AI 配置</h2>

          <div class="state-group">
            <div class="state-group-title">模型</div>
            <div class="kv">
              <span class="muted">selected_model</span>
              <button type="button" class="state-picker-btn" @click="openModelModal">
                {{ selectedModel || '-' }}
              </button>
            </div>
            <div class="kv">
              <span class="muted">provider</span>
              <span class="state-value">{{ runtimeSummary.selectedModelProvider }}</span>
            </div>
          </div>

          <div class="state-group">
            <div class="state-group-title">技能</div>
            <div class="kv">
              <span class="muted">selected_skills</span>
              <button type="button" class="state-picker-btn" @click="openSkillModal">{{ selectedSkillsCountText }}</button>
            </div>
          </div>

          <div class="state-group">
            <div class="state-group-title">MCP</div>
            <div class="kv">
              <span class="muted">selected_mcp_servers</span>
              <button type="button" class="state-picker-btn" @click="openMcpModal">{{ selectedMcpCountText }}</button>
            </div>
          </div>
        </article>
      </section>

      <section v-else class="main-grid config-grid">
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
                  <input
                    v-model="githubTokenDraft"
                    type="password"
                    class="picker-search-input system-token-input"
                    :disabled="githubTokenSaving"
                    placeholder="输入 GITHUB_TOKEN"
                  />
                </label>

                <p class="system-config-hint">建议使用具备 repo 权限的 Personal Access Token，用于仓库读取与创建。</p>
              </div>

              <aside class="system-config-side">
                <div class="system-status-card" :class="{ 'system-status-card-ready': githubTokenConfigured }">
                  <span class="system-status-label">当前状态</span>
                  <span class="system-status-value">{{ githubTokenConfigured ? '已配置' : '未配置' }}</span>
                </div>

                <div class="picker-actions system-config-actions">
                  <button
                    type="button"
                    class="picker-btn system-save-btn"
                    :disabled="githubTokenSaving || !githubTokenDraft.trim()"
                    @click="saveGithubToken"
                  >
                    {{ githubTokenSaving ? '保存中...' : '保存 Token' }}
                  </button>
                </div>
              </aside>
            </div>
          </div>
        </article>
      </section>
    </section>

    <div v-if="isCreateConversationModalOpen" class="picker-modal-overlay" @click.self="closeCreateConversationModal">
      <div class="picker-modal panel create-conversation-modal">
        <div class="picker-modal-header">
          <h3>新建对话</h3>
          <button type="button" class="picker-close-btn" :disabled="creatingConversation" @click="closeCreateConversationModal" aria-label="关闭"><span class="close-icon" aria-hidden="true">✕</span></button>
        </div>

        <div class="create-conversation-form">
          <label class="create-field">
            <span class="create-field-label">平台</span>
            <select
              v-model="createConversationPlatform"
              class="picker-provider-select"
              :disabled="creatingConversation"
            >
              <option v-for="name in platformOptions" :key="name" :value="name">{{ name }}</option>
            </select>
          </label>

          <label class="create-field">
            <span class="create-field-label">初始消息</span>
            <textarea
              v-model="createConversationInitialMessage"
              class="create-initial-message"
              :disabled="creatingConversation"
              placeholder="请输入你想发送的第一条消息"
              @keydown="handleCreateInitialMessageKeydown"
            ></textarea>
          </label>
        </div>

        <div class="picker-actions">
          <button type="button" class="picker-btn ghost" :disabled="creatingConversation" @click="closeCreateConversationModal">取消</button>
          <button
            type="button"
            class="picker-btn"
            :disabled="creatingConversation || !createConversationInitialMessage.trim()"
            @click="submitCreateConversation"
          >
            {{ creatingConversation ? '创建中...' : '创建并发送' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="isProjectCreateModalOpen" class="picker-modal-overlay" @click.self="closeProjectCreateModal">
      <div class="picker-modal panel create-conversation-modal">
        <div class="picker-modal-header">
          <h3>新建项目</h3>
          <button type="button" class="picker-close-btn" :disabled="creatingProject" @click="closeProjectCreateModal" aria-label="关闭"><span class="close-icon" aria-hidden="true">✕</span></button>
        </div>

        <div class="create-conversation-form">
          <label class="create-field">
            <span class="create-field-label">项目名称</span>
            <input v-model="createProjectForm.name" class="picker-search-input" :disabled="creatingProject || creatingGithubRepo" placeholder="请输入项目名称，如 shujietai-demo" />
          </label>

          <label class="create-field">
            <span class="create-field-label">项目简介</span>
            <textarea
              v-model="createProjectForm.description"
              class="create-initial-message"
              :disabled="creatingProject || creatingGithubRepo"
              placeholder="请输入项目简介"
            ></textarea>
          </label>

          <div class="project-repo-mode-card">
            <label class="create-field-checkbox">
              <input type="checkbox" v-model="createRepoEnabled" :disabled="creatingProject || creatingGithubRepo" />
              <span>同时新建 GitHub 仓库（可选）</span>
            </label>

            <template v-if="!createRepoEnabled">
              <label class="create-field">
                <span class="create-field-label">已有仓库（必选）</span>
                <select
                  v-model="createProjectForm.repository_url"
                  class="picker-provider-select"
                  :disabled="creatingProject || creatingGithubRepo"
                  @change="handleRepositoryChange"
                >
                  <option value="" disabled>请选择仓库</option>
                  <option v-for="repo in getRepoChoices()" :key="repo.url" :value="repo.url">{{ repo.full_name }} · {{ repo.description || '无描述' }}</option>
                </select>
              </label>
            </template>

            <template v-else>
              <label class="create-field-checkbox">
                <input type="checkbox" v-model="createProjectForm.private" :disabled="creatingProject || creatingGithubRepo" />
                <span>创建为私有仓库</span>
              </label>
              <div class="project-repo-mode-hint">将使用“项目名称”作为仓库名，“项目简介”作为仓库描述。</div>
            </template>
          </div>
        </div>

        <div class="picker-actions">
          <button type="button" class="picker-btn ghost" :disabled="creatingProject || creatingGithubRepo" @click="closeProjectCreateModal">取消</button>
          <button
            v-if="!createRepoEnabled"
            type="button"
            class="picker-btn"
            :disabled="creatingProject || creatingGithubRepo || !createProjectForm.name.trim() || !createProjectForm.repository_url.trim()"
            @click="submitCreateProject"
          >
            {{ creatingProject ? '创建中...' : '创建项目' }}
          </button>
          <button
            v-else
            type="button"
            class="picker-btn"
            :disabled="creatingProject || creatingGithubRepo || !createProjectForm.name.trim()"
            @click="createGithubRepo"
          >
            {{ creatingGithubRepo ? '创建仓库并建项目中...' : '新建仓库并创建项目' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="isProjectEditModalOpen" class="picker-modal-overlay" @click.self="closeProjectEditModal">
      <div class="picker-modal panel create-conversation-modal">
        <div class="picker-modal-header">
          <h3>编辑项目</h3>
          <button type="button" class="picker-close-btn" :disabled="updatingProject" @click="closeProjectEditModal" aria-label="关闭"><span class="close-icon" aria-hidden="true">✕</span></button>
        </div>

        <div class="create-conversation-form">
          <label class="create-field">
            <span class="create-field-label">项目名称</span>
            <input v-model="editProjectForm.name" class="picker-search-input" :disabled="updatingProject" placeholder="请输入项目名称" />
          </label>

          <label class="create-field">
            <span class="create-field-label">项目简介</span>
            <textarea
              v-model="editProjectForm.description"
              class="create-initial-message"
              :disabled="updatingProject"
              placeholder="请输入项目简介"
            ></textarea>
          </label>
        </div>

        <div class="picker-actions">
          <button type="button" class="picker-btn ghost" :disabled="updatingProject" @click="closeProjectEditModal">取消</button>
          <button type="button" class="picker-btn" :disabled="updatingProject || !editProjectForm.name.trim()" @click="submitEditProject">
            {{ updatingProject ? '保存中...' : '保存修改' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="isModelModalOpen" class="picker-modal-overlay" @click.self="closeModelModal">
      <div class="picker-modal panel">
        <div class="picker-modal-header">
          <h3>选择模型</h3>
          <button type="button" class="picker-close-btn" @click="closeModelModal" aria-label="关闭"><span class="close-icon" aria-hidden="true">✕</span></button>
        </div>
        <div class="picker-search-row picker-provider-row">
          <select v-model="modelProviderDraft" class="picker-provider-select">
            <option v-for="provider in modelProviderOptions" :key="provider" :value="provider">{{ provider }}</option>
          </select>
          <input v-model="modelSearchDraft" class="picker-search-input" placeholder="搜索 model 名称" />
        </div>
        <div class="picker-list">
          <label
            v-for="item in filteredModelItems"
            :key="item.name"
            class="picker-item"
          >
            <input
              type="radio"
              name="model-selection"
              :checked="tempSelectedModel === item.name"
              @change="selectTempModel(item.name)"
            />
            <div class="picker-item-text">
              <div class="picker-item-title">{{ item.name }}</div>
              <div class="picker-item-desc">provider: {{ item.provider || '-' }}</div>
            </div>
          </label>
          <div v-if="filteredModelItems.length === 0" class="muted">无匹配项</div>
        </div>
        <div class="picker-actions">
          <button type="button" class="picker-btn ghost" @click="closeModelModal">取消</button>
          <button type="button" class="picker-btn" @click="applyModelModalSelection">确认</button>
        </div>
      </div>
    </div>

    <div v-if="isSkillModalOpen" class="picker-modal-overlay" @click.self="closeSkillModal">
      <div class="picker-modal panel">
        <div class="picker-modal-header">
          <h3>选择 Skills</h3>
          <button type="button" class="picker-close-btn" @click="closeSkillModal" aria-label="关闭"><span class="close-icon" aria-hidden="true">✕</span></button>
        </div>
        <div class="picker-search-row">
          <input v-model="skillSearchDraft" class="picker-search-input" placeholder="搜索 skill 名称或描述" />
        </div>
        <div class="picker-list">
          <label
            v-for="item in filteredSkillItems"
            :key="item.name"
            class="picker-item"
          >
            <input
              type="checkbox"
              :checked="isTempSkillChecked(item.name)"
              @change="toggleTempSkill(item.name)"
            />
            <div class="picker-item-text">
              <div class="picker-item-title">{{ item.name }}</div>
              <div class="picker-item-desc">{{ item.description || '-' }}</div>
            </div>
          </label>
          <div v-if="filteredSkillItems.length === 0" class="muted">无匹配项</div>
        </div>
        <div class="picker-actions">
          <button type="button" class="picker-btn ghost" @click="closeSkillModal">取消</button>
          <button type="button" class="picker-btn" @click="applySkillModalSelection">确认</button>
        </div>
      </div>
    </div>

    <div v-if="isMcpModalOpen" class="picker-modal-overlay" @click.self="closeMcpModal">
      <div class="picker-modal panel">
        <div class="picker-modal-header">
          <h3>选择 MCP Servers</h3>
          <button type="button" class="picker-close-btn" @click="closeMcpModal" aria-label="关闭"><span class="close-icon" aria-hidden="true">✕</span></button>
        </div>
        <div class="picker-search-row">
          <input v-model="mcpSearchDraft" class="picker-search-input" placeholder="搜索 MCP 名称" />
        </div>
        <div class="picker-list">
          <label
            v-for="name in filteredMcpItems"
            :key="name"
            class="picker-item"
          >
            <input
              type="checkbox"
              :checked="isTempMcpChecked(name)"
              @change="toggleTempMcp(name)"
            />
            <div class="picker-item-text">
              <div class="picker-item-title">{{ name }}</div>
            </div>
          </label>
          <div v-if="filteredMcpItems.length === 0" class="muted">无匹配项</div>
        </div>
        <div class="picker-actions">
          <button type="button" class="picker-btn ghost" @click="closeMcpModal">取消</button>
          <button type="button" class="picker-btn" @click="applyMcpModalSelection">确认</button>
        </div>
      </div>
    </div>

    <div v-if="isTaskBoardCreateModalOpen" class="picker-modal-overlay" @click.self="closeTaskBoardCreateModal">
      <div class="picker-modal panel create-conversation-modal">
        <div class="picker-modal-header">
          <h3>新建任务</h3>
          <button type="button" class="picker-close-btn" :disabled="creatingTaskBoardItem" @click="closeTaskBoardCreateModal" aria-label="关闭"><span class="close-icon" aria-hidden="true">✕</span></button>
        </div>

        <div class="create-conversation-form">
          <label class="create-field">
            <span class="create-field-label">任务名称</span>
            <input v-model="taskBoardCreateForm.name" class="picker-search-input" :disabled="creatingTaskBoardItem" placeholder="请输入任务名称" />
          </label>

          <label class="create-field">
            <span class="create-field-label">任务描述</span>
            <textarea v-model="taskBoardCreateForm.description" class="create-initial-message" :disabled="creatingTaskBoardItem" placeholder="请输入任务描述"></textarea>
          </label>

          <label class="create-field">
            <span class="create-field-label">AI 平台</span>
            <input v-model="taskBoardCreateForm.ai_platform" class="picker-search-input" :disabled="creatingTaskBoardItem" placeholder="hermes" />
          </label>

          <label class="create-field">
            <span class="create-field-label">所属项目</span>
            <select v-model="taskBoardCreateForm.project_id" class="picker-provider-select" :disabled="creatingTaskBoardItem">
              <option value="">不关联项目</option>
              <option v-for="proj in projects" :key="proj.id" :value="proj.id">{{ proj.name }}（{{ proj.code }}）</option>
            </select>
          </label>

          <label class="create-field">
            <span class="create-field-label">上游依赖</span>
            <select v-model="taskBoardCreateForm.upstream_task_id" class="picker-provider-select" :disabled="creatingTaskBoardItem">
              <option value="">无上游依赖</option>
              <option v-for="dep in taskBoardDependencyOptions" :key="dep.value" :value="dep.value">{{ dep.label }}</option>
            </select>
          </label>

          <label class="create-field">
            <span class="create-field-label">父任务</span>
            <select v-model="taskBoardCreateForm.parent_task_id" class="picker-provider-select" :disabled="creatingTaskBoardItem">
              <option value="">无父任务</option>
              <option v-for="dep in taskBoardDependencyOptions" :key="dep.value" :value="dep.value">{{ dep.label }}</option>
            </select>
          </label>

          <label class="create-field">
            <span class="create-field-label">状态</span>
            <select v-model="taskBoardCreateForm.status" class="picker-provider-select" :disabled="creatingTaskBoardItem">
              <option v-for="opt in taskBoardStatusOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>
          </label>
        </div>

        <div class="picker-actions">
          <button type="button" class="picker-btn ghost" :disabled="creatingTaskBoardItem" @click="closeTaskBoardCreateModal">取消</button>
          <button type="button" class="picker-btn" :disabled="creatingTaskBoardItem || !taskBoardCreateForm.name.trim()" @click="submitCreateTaskBoardItem">
            {{ creatingTaskBoardItem ? '创建中...' : '创建任务' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="isTaskBoardEditModalOpen" class="picker-modal-overlay" @click.self="closeTaskBoardEditModal">
      <div class="picker-modal panel create-conversation-modal">
        <div class="picker-modal-header">
          <h3>编辑任务</h3>
          <button type="button" class="picker-close-btn" :disabled="updatingTaskBoardItem" @click="closeTaskBoardEditModal" aria-label="关闭"><span class="close-icon" aria-hidden="true">✕</span></button>
        </div>

        <div class="create-conversation-form">
          <label class="create-field">
            <span class="create-field-label">任务名称</span>
            <input v-model="taskBoardEditForm.name" class="picker-search-input" :disabled="updatingTaskBoardItem" placeholder="请输入任务名称" />
          </label>

          <label class="create-field">
            <span class="create-field-label">任务描述</span>
            <textarea v-model="taskBoardEditForm.description" class="create-initial-message" :disabled="updatingTaskBoardItem" placeholder="请输入任务描述"></textarea>
          </label>

          <label class="create-field">
            <span class="create-field-label">AI 平台</span>
            <input v-model="taskBoardEditForm.ai_platform" class="picker-search-input" :disabled="updatingTaskBoardItem" placeholder="hermes" />
          </label>

          <label class="create-field">
            <span class="create-field-label">所属项目</span>
            <select v-model="taskBoardEditForm.project_id" class="picker-provider-select" :disabled="updatingTaskBoardItem">
              <option value="">不关联项目</option>
              <option v-for="proj in projects" :key="proj.id" :value="proj.id">{{ proj.name }}（{{ proj.code }}）</option>
            </select>
          </label>

          <label class="create-field">
            <span class="create-field-label">上游依赖</span>
            <select v-model="taskBoardEditForm.upstream_task_id" class="picker-provider-select" :disabled="updatingTaskBoardItem">
              <option value="">无上游依赖</option>
              <option v-for="dep in taskBoardDependencyOptions" :key="dep.value" :value="dep.value">{{ dep.label }}</option>
            </select>
          </label>

          <label class="create-field">
            <span class="create-field-label">父任务</span>
            <select v-model="taskBoardEditForm.parent_task_id" class="picker-provider-select" :disabled="updatingTaskBoardItem">
              <option value="">无父任务</option>
              <option v-for="dep in taskBoardDependencyOptions" :key="dep.value" :value="dep.value">{{ dep.label }}</option>
            </select>
          </label>

          <label class="create-field">
            <span class="create-field-label">状态</span>
            <select v-model="taskBoardEditForm.status" class="picker-provider-select" :disabled="updatingTaskBoardItem">
              <option v-for="opt in taskBoardStatusOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>
          </label>
        </div>

        <div class="picker-actions">
          <button type="button" class="picker-btn ghost" :disabled="updatingTaskBoardItem" @click="closeTaskBoardEditModal">取消</button>
          <button type="button" class="picker-btn" :disabled="updatingTaskBoardItem || !taskBoardEditForm.name.trim()" @click="submitEditTaskBoardItem">
            {{ updatingTaskBoardItem ? '保存中...' : '保存修改' }}
          </button>
        </div>
      </div>
    </div>

  </main>
</template>
