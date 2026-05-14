import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/sessions' },
  { path: '/sessions', name: 'sessions', component: () => import('../views/SessionsView.vue') },
  { path: '/task-board', name: 'task-board', component: () => import('../views/TaskBoardView.vue') },
  { path: '/archive', name: 'archive', component: () => import('../views/ArchiveView.vue') },
  { path: '/projects', name: 'projects', component: () => import('../views/ProjectsView.vue') },
  { path: '/skills', name: 'skills', component: () => import('../views/SkillsView.vue') },
  { path: '/settings', name: 'settings', component: () => import('../views/SettingsView.vue') },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
