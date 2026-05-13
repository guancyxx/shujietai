export const PAGE_WHITELIST = [
  'chat',
  'projects',
  'task-board',
  'task-archive',
  'model-config',
  'system-config',
  'dispatch-history',
  'skills-catalog',
]

export const TASK_BOARD_STATUS_OPTIONS = [
  { value: 'draft', label: '草稿' },
  { value: 'pending_execution', label: '待执行' },
  { value: 'in_progress', label: '进行中' },
  { value: 'blocked', label: '阻塞' },
  { value: 'cancelled', label: '取消' },
  { value: 'completed', label: '已完成' },
]

export const TASK_BOARD_STATUS_LABEL_MAP = {
  draft: '草稿',
  pending_execution: '待执行',
  in_progress: '进行中',
  blocked: '阻塞',
  completed: '已完成',
  cancelled: '取消',
}

export const TASK_BOARD_PRIORITY_OPTIONS = [
  { value: 1, label: 'P0' },
  { value: 2, label: 'P1' },
  { value: 3, label: 'P2' },
  { value: 4, label: 'P3' },
]

export const TASK_BOARD_PRIORITY_LABEL_MAP = {
  1: 'P0',
  2: 'P1',
  3: 'P2',
  4: 'P3',
}

export const KANBAN_STATUSES = ['draft', 'pending_execution', 'in_progress', 'blocked', 'cancelled', 'completed']
export const COLLAPSIBLE_KANBAN_STATUSES = ['completed']
export const KANBAN_PRIORITY_LABELS = { 1: 'P0', 2: 'P1', 3: 'P2', 4: 'P3' }
export const KANBAN_PRIORITY_ORDER = [1, 2, 3, 4]

export const LANE_TITLE_MAP = {
  todo: '待处理',
  doing: '进行中',
  done: '已完成',
}

export const ROLE_LABEL_MAP = {
  user: '用户',
  assistant: '助手',
  system: '系统',
  tool: '工具',
}

export const DISPATCH_EVENT_LABEL_MAP = {
  content_delta: 'AI 正在返回内容',
  tool_call: 'AI 正在调用工具',
  tool_start: 'AI 正在调用工具',
  tool_complete: '工具调用完成',
  agent_thinking: 'AI 思考中…',
  await_input: 'AI 等待你补充信息',
  completed: '任务已完成',
  error: '任务执行异常',
  cancelled: '任务已取消',
}
