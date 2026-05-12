import { KANBAN_PRIORITY_ORDER } from '../constants/appConstants.js'

export function getTaskPriority(item) {
  const priority = Number(item?.priority ?? 3)
  return KANBAN_PRIORITY_ORDER.includes(priority) ? priority : 3
}

export function sortTaskBoardSiblings(items) {
  return [...items].sort((a, b) => {
    const priorityDiff = getTaskPriority(a) - getTaskPriority(b)
    if (priorityDiff !== 0) return priorityDiff
    const updatedDiff = String(b.updated_at || '').localeCompare(String(a.updated_at || ''))
    if (updatedDiff !== 0) return updatedDiff
    return String(a.name || '').localeCompare(String(b.name || ''))
  })
}

export function buildTaskTree(items) {
  const nodesById = new Map()
  const roots = []
  for (const item of sortTaskBoardSiblings(items)) {
    nodesById.set(item.id, { ...item, children: [] })
  }
  for (const node of nodesById.values()) {
    const parentId = node.parent_task_id || null
    const parent = parentId ? nodesById.get(parentId) : null
    if (parent) {
      parent.children.push(node)
    } else {
      roots.push(node)
    }
  }
  const sortChildren = (node) => {
    node.children = sortTaskBoardSiblings(node.children)
    node.children.forEach(sortChildren)
    return node
  }
  return sortTaskBoardSiblings(roots).map(sortChildren)
}

export function countTaskTreeNodes(nodes) {
  return nodes.reduce((sum, node) => sum + 1 + countTaskTreeNodes(node.children || []), 0)
}

export function makeTaskNodeKey(item) {
  return item?.id || ''
}
