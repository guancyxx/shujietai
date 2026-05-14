import { computed, ref } from 'vue'
import { deleteJson, fetchJson, patchJson, postJson, putJson } from '../services/apiClient.js'

const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:18000'

export function useProjects() {
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

  const filteredProjects = computed(() => {
    const keyword = projectSearch.value.trim().toLowerCase()
    if (!keyword) return projects.value
    return projects.value.filter((item) => {
      const text = `${item.code} ${item.name} ${item.description} ${item.repository_name} ${item.repository_url}`.toLowerCase()
      return text.includes(keyword)
    })
  })

  const selectedCreateRepo = computed(() => {
    if (!createProjectForm.value.repository_url) return null
    return githubRepos.value.find((repo) => repo.url === createProjectForm.value.repository_url) || null
  })

  async function loadProjects() {
    const data = await fetchJson(`${apiBase}/api/v1/projects`)
    projects.value = data.items || []
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

  async function saveGithubToken(onError) {
    if (githubTokenSaving.value) return
    githubTokenSaving.value = true
    try {
      const payload = { github_token: githubTokenDraft.value.trim() }
      const data = await putJson(`${apiBase}/api/v1/system/config/github-token`, payload)
      githubTokenConfigured.value = Boolean(data?.github_token_configured)
      githubTokenDraft.value = ''
      await loadGithubRepos()
    } catch (error) {
      if (onError) onError(error instanceof Error ? error.message : 'Unknown error')
    } finally {
      githubTokenSaving.value = false
    }
  }

  async function createGithubRepo(onError) {
    if (creatingGithubRepo.value || !createProjectForm.value.name.trim()) return
    creatingGithubRepo.value = true
    try {
      const payload = {
        name: createProjectForm.value.name.trim(),
        description: createProjectForm.value.description.trim(),
        private: Boolean(createProjectForm.value.private),
      }
      const created = await postJson(`${apiBase}/api/v1/projects/github/repos`, payload)
      createProjectForm.value.repository_url = created.url
      await loadGithubRepos()
      await submitCreateProject(onError)
    } catch (error) {
      if (onError) onError(error instanceof Error ? error.message : 'Unknown error')
    } finally {
      creatingGithubRepo.value = false
    }
  }

  async function submitCreateProject(onError) {
    const projectName = createProjectForm.value.name.trim()
    if (creatingProject.value || !projectName) return
    if (!createRepoEnabled.value && !createProjectForm.value.repository_url.trim()) return
    creatingProject.value = true
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
      if (onError) onError(error instanceof Error ? error.message : 'Unknown error')
    } finally {
      creatingProject.value = false
    }
  }

  async function submitEditProject(onError) {
    if (updatingProject.value || !editProjectId.value || !editProjectForm.value.name.trim()) return
    updatingProject.value = true
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
      if (onError) onError(error instanceof Error ? error.message : 'Unknown error')
    } finally {
      updatingProject.value = false
    }
  }

  async function deleteProject(item, onError) {
    if (!item?.id || deletingProjectId.value) return
    const confirmed = window.confirm(`确认删除项目「${item.name}」？`)
    if (!confirmed) return
    deletingProjectId.value = item.id
    try {
      await deleteJson(`${apiBase}/api/v1/projects/${item.id}`)
      await loadProjects()
    } catch (error) {
      if (onError) onError(error instanceof Error ? error.message : 'Unknown error')
    } finally {
      deletingProjectId.value = ''
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
    if (creatingProject.value) return
    isProjectCreateModalOpen.value = false
  }

  function openProjectEditModal(item) {
    editProjectId.value = item.id
    editProjectForm.value = { name: item.name, description: item.description || '' }
    isProjectEditModalOpen.value = true
  }

  function closeProjectEditModal() {
    if (updatingProject.value) return
    isProjectEditModalOpen.value = false
    editProjectId.value = ''
  }

  function getRepoChoices() {
    return githubRepos.value
  }

  function handleRepositoryChange() {
    const repo = selectedCreateRepo.value
    if (!repo) return
    if (!createProjectForm.value.name.trim()) createProjectForm.value.name = repo.name
    if (!createProjectForm.value.description.trim() && repo.description?.trim()) {
      createProjectForm.value.description = repo.description.trim()
    }
  }

  function formatSessionTime(value) {
    if (!value) return '-'
    const parsed = new Date(value)
    if (Number.isNaN(parsed.getTime())) return '-'
    return parsed.toLocaleString()
  }

  return {
    projects,
    githubRepos,
    projectSearch,
    creatingProject,
    updatingProject,
    deletingProjectId,
    creatingGithubRepo,
    githubTokenDraft,
    githubTokenSaving,
    githubTokenConfigured,
    isProjectCreateModalOpen,
    isProjectEditModalOpen,
    createRepoEnabled,
    createProjectForm,
    editProjectId,
    editProjectForm,
    filteredProjects,
    selectedCreateRepo,
    loadProjects,
    loadGithubRepos,
    loadSystemConfig,
    saveGithubToken,
    createGithubRepo,
    submitCreateProject,
    submitEditProject,
    deleteProject,
    openProjectCreateModal,
    closeProjectCreateModal,
    openProjectEditModal,
    closeProjectEditModal,
    getRepoChoices,
    handleRepositoryChange,
    formatSessionTime,
  }
}
