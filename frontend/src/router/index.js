import { createRouter, createWebHashHistory } from 'vue-router'

import ChatPage from '../views/ChatPage.vue'
import ProjectsPage from '../views/ProjectsPage.vue'
import TaskBoardPage from '../views/TaskBoardPage.vue'
import TaskArchivePage from '../views/TaskArchivePage.vue'
import ModelConfigPage from '../views/ModelConfigPage.vue'
import SystemConfigPage from '../views/SystemConfigPage.vue'
import DispatchHistoryPage from '../views/DispatchHistoryPage.vue'
import SkillsCatalogPage from '../views/SkillsCatalogPage.vue'
import LoginPage from '../views/LoginPage.vue'

import { getToken, setUnauthorizedHandler } from '../services/auth.js'

const routes = [
  { path: '/login', name: 'login', component: LoginPage, meta: { public: true } },
  { path: '/', name: 'chat', component: ChatPage },
  { path: '/projects', name: 'projects', component: ProjectsPage },
  { path: '/task-board', name: 'task-board', component: TaskBoardPage },
  { path: '/task-archive', name: 'task-archive', component: TaskArchivePage },
  { path: '/model-config', name: 'model-config', component: ModelConfigPage },
  { path: '/system-config', name: 'system-config', component: SystemConfigPage },
  { path: '/dispatch-history', name: 'dispatch-history', component: DispatchHistoryPage },
  { path: '/skills-catalog', name: 'skills-catalog', component: SkillsCatalogPage },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

// M1 auth: 全局守卫 —— 无 JWT 一律跳 /login（保留目标路径，登录后回跳）
router.beforeEach((to) => {
  if (to.meta.public) return true
  if (!getToken()) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  return true
})

// 401 拦截回调：任何请求返回 401（token 失效/过期）时清 token 跳登录
setUnauthorizedHandler(() => {
  if (router.currentRoute.value.name !== 'login') {
    router.push({ name: 'login' })
  }
})

export default router
