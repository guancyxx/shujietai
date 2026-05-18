import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { fetchJson, postJson, patchJson, deleteJson } from '../services/apiClient.js'

const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:18000'

export const useProjectStore = defineStore('project', () => {
  const projects = ref([])
  const githubRepos = ref([])
  const projectSearch = ref('')
  const deletingProjectId = ref('')
  const creatingProject = ref(false)
  const updatingProject = ref(false)
  const creatingGithubRepo = ref(false)

  const isProjectCreateModalOpen = ref(false)
  const isProjectEditModalOpen = ref(false)
  const createRepoEnabled = ref(false)
  const createProjectForm = ref({ repository_url: '', name: '', description: '', private: false })
  const editProjectId = ref('')
  const editProjectForm = ref({ name: '', description: '' })

  const filteredProjects = computed(() => {
    const kw = projectSearch.value.trim().toLowerCase()
    if (!kw) return projects.value
    return projects.value.filter(p => {
      const text = `${p.code} ${p.name} ${p.description} ${p.repository_name} ${p.repository_url}`.toLowerCase()
      return text.includes(kw)
    })
  })

  const selectedCreateRepo = computed(() => {
    if (!createProjectForm.value.repository_url) return null
    return githubRepos.value.find(r => r.url === createProjectForm.value.repository_url) || null
  })

  function getRepoChoices() { return githubRepos.value }

  function handleRepositoryChange() {
    const repo = selectedCreateRepo.value
    if (!repo) return
    if (!createProjectForm.value.name.trim()) createProjectForm.value.name = repo.name
    if (!createProjectForm.value.description.trim() && repo.description?.trim()) createProjectForm.value.description = repo.description.trim()
  }

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
    } catch { githubRepos.value = [] }
  }

  function resetCreateProjectForm() {
    createRepoEnabled.value = false
    createProjectForm.value = {
      repository_url: githubRepos.value[0]?.url || '', name: '', description: '', private: false,
    }
  }

  function openProjectCreateModal() { resetCreateProjectForm(); isProjectCreateModalOpen.value = true }
  function closeProjectCreateModal() { if (!creatingProject.value) isProjectCreateModalOpen.value = false }

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

  async function submitCreateProject() {
    const name = createProjectForm.value.name.trim()
    if (creatingProject.value || !name) return
    if (!createRepoEnabled.value && !createProjectForm.value.repository_url.trim()) return
    creatingProject.value = true
    try {
      await postJson(`${apiBase}/api/v1/projects`, {
        repository_url: createProjectForm.value.repository_url.trim(),
        name, description: createProjectForm.value.description.trim(),
      })
      isProjectCreateModalOpen.value = false
      await loadProjects()
    } finally { creatingProject.value = false }
  }

  async function submitEditProject() {
    if (updatingProject.value || !editProjectId.value || !editProjectForm.value.name.trim()) return
    updatingProject.value = true
    try {
      await patchJson(`${apiBase}/api/v1/projects/${editProjectId.value}`, {
        name: editProjectForm.value.name.trim(),
        description: editProjectForm.value.description.trim(),
      })
      isProjectEditModalOpen.value = false
      editProjectId.value = ''
      await loadProjects()
    } finally { updatingProject.value = false }
  }

  async function createGithubRepo() {
    if (creatingGithubRepo.value || !createProjectForm.value.name.trim()) return
    creatingGithubRepo.value = true
    try {
      const created = await postJson(`${apiBase}/api/v1/projects/github/repos`, {
        name: createProjectForm.value.name.trim(),
        description: createProjectForm.value.description.trim(),
        private: Boolean(createProjectForm.value.private),
      })
      createProjectForm.value.repository_url = created.url
      await loadGithubRepos()
      await submitCreateProject()
    } finally { creatingGithubRepo.value = false }
  }

  async function deleteProject(item) {
    if (!item?.id || deletingProjectId.value) return
    if (!window.confirm(`确认删除项目「${item.name}」？`)) return
    deletingProjectId.value = item.id
    try {
      await deleteJson(`${apiBase}/api/v1/projects/${item.id}`)
      await loadProjects()
    } finally { deletingProjectId.value = '' }
  }

  return {
    projects, githubRepos, projectSearch, deletingProjectId,
    creatingProject, updatingProject, creatingGithubRepo,
    isProjectCreateModalOpen, isProjectEditModalOpen,
    createRepoEnabled, createProjectForm,
    editProjectId, editProjectForm,
    filteredProjects, selectedCreateRepo,
    getRepoChoices, handleRepositoryChange,
    loadProjects, loadGithubRepos,
    resetCreateProjectForm,
    openProjectCreateModal, closeProjectCreateModal,
    openProjectEditModal, closeProjectEditModal,
    submitCreateProject, submitEditProject,
    createGithubRepo, deleteProject,
  }
})
