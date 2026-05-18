import { createRouter, createWebHashHistory } from 'vue-router'

import ChatPage from '../views/ChatPage.vue'
import ProjectsPage from '../views/ProjectsPage.vue'
import TaskBoardPage from '../views/TaskBoardPage.vue'
import TaskArchivePage from '../views/TaskArchivePage.vue'
import ModelConfigPage from '../views/ModelConfigPage.vue'
import SystemConfigPage from '../views/SystemConfigPage.vue'
import DispatchHistoryPage from '../views/DispatchHistoryPage.vue'
import SkillsCatalogPage from '../views/SkillsCatalogPage.vue'

const routes = [
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

export default router
