<template>
  <div class="skill-graph-root">
    <!-- Toolbar -->
    <div class="sg-toolbar">
      <button
        v-for="m in modes"
        :key="m.id"
        class="picker-btn"
        :class="{ active: mode === m.id }"
        @click="setMode(m.id)"
      >{{ m.label }}</button>
      <span class="sg-hint" v-if="mode === 'category'">点击分类节点可展开技能细节</span>
      <span class="sg-hint" v-else>{{ expandedCategory }} 下的技能网络</span>
      <button v-if="mode === 'skill'" class="picker-btn sg-back" @click="setMode('category')">
        ← 返回分类图
      </button>
      <button class="picker-btn sg-refresh" @click="reload">⟳ 刷新</button>
    </div>

    <!-- Graph canvas -->
    <div class="sg-canvas-wrap" ref="canvasWrap">
      <svg ref="svgEl" class="sg-svg"></svg>
      <!-- Tooltip -->
      <div class="sg-tooltip" ref="tooltip" style="display:none"></div>
    </div>

    <!-- Side detail panel -->
    <transition name="sg-panel">
      <div class="sg-detail" v-if="selected">
        <div class="sg-detail-header">
          <span class="sg-detail-label">{{ selected.label || selected.name }}</span>
          <button class="picker-btn" @click="selected = null">✕</button>
        </div>
        <div class="sg-detail-meta" v-if="selected.skill_count !== undefined">
          <span class="sg-badge">{{ selected.skill_count }} 个技能</span>
          <span
            v-for="tag in (selected.tags || []).slice(0, 8)"
            :key="tag"
            class="sg-tag"
          >{{ tag }}</span>
        </div>
        <div class="sg-detail-meta" v-else>
          <span
            v-for="tag in (selected.tags || [])"
            :key="tag"
            class="sg-tag"
          >{{ tag }}</span>
        </div>
        <ul class="sg-skill-list" v-if="selected.skills">
          <li
            v-for="s in selected.skills"
            :key="s.name"
            class="sg-skill-item"
            @click="drillInto(selected.id || selected.label)"
          >
            <span class="sg-skill-name">{{ s.name }}</span>
          </li>
        </ul>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as d3 from 'd3'

const props = defineProps({
  apiBase: { type: String, default: '' },
})

const mode = ref('category')        // 'category' | 'skill'
const expandedCategory = ref('')
const svgEl = ref(null)
const canvasWrap = ref(null)
const tooltip = ref(null)
const selected = ref(null)
const modes = [
  { id: 'category', label: '分类图谱' },
]

let graphData = null       // full response from /api/v1/skills/graph
let simulation = null

// ────────────────────────────────────────────────────────────
// Data
// ────────────────────────────────────────────────────────────
async function reload() {
  const res = await fetch(`${props.apiBase}/api/v1/skills/graph`)
  graphData = await res.json()
  draw()
}

// ────────────────────────────────────────────────────────────
// Mode switching
// ────────────────────────────────────────────────────────────
function setMode(m, category) {
  mode.value = m
  if (category) expandedCategory.value = category
  selected.value = null
  draw()
}

function drillInto(categoryId) {
  expandedCategory.value = categoryId
  mode.value = 'skill'
  selected.value = null
  draw()
}

// ────────────────────────────────────────────────────────────
// Color palette — one per category, consistent hashing
// ────────────────────────────────────────────────────────────
const palette = [
  '#6fbafe', '#7bc67e', '#f0a84e', '#e06c75',
  '#c678dd', '#56b6c2', '#e5c07b', '#abb2bf',
  '#be5046', '#98c379', '#61afef', '#d19a66',
]
function catColor(name) {
  let h = 0
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0
  return palette[h % palette.length]
}

// ────────────────────────────────────────────────────────────
// Draw
// ────────────────────────────────────────────────────────────
function draw() {
  if (!graphData) return
  nextTick(() => {
    if (mode.value === 'category') drawCategory()
    else drawSkill(expandedCategory.value)
  })
}

function getSize() {
  const el = canvasWrap.value
  if (!el) return { w: 800, h: 600 }
  return { w: el.clientWidth || 800, h: el.clientHeight || 600 }
}

function clearSvg() {
  if (simulation) { simulation.stop(); simulation = null }
  d3.select(svgEl.value).selectAll('*').remove()
}

// ── Category graph ──────────────────────────────────────────
function drawCategory() {
  clearSvg()
  const { w, h } = getSize()
  const svg = d3.select(svgEl.value)
    .attr('width', w).attr('height', h)

  const g = svg.append('g')
  svg.call(
    d3.zoom()
      .scaleExtent([0.3, 3])
      .on('zoom', ({ transform }) => g.attr('transform', transform))
  )

  const nodes = graphData.nodes.map(n => ({ ...n }))
  const edges = graphData.edges.map(e => ({ ...e }))

  const radiusScale = d3.scaleSqrt()
    .domain([1, d3.max(nodes, d => d.skill_count)])
    .range([14, 46])

  // Links
  const link = g.append('g').attr('class', 'sg-links')
    .selectAll('line')
    .data(edges)
    .join('line')
    .attr('stroke', 'rgba(111,186,255,0.25)')
    .attr('stroke-width', d => Math.min(d.weight * 0.8, 4))

  // Nodes group
  const node = g.append('g').attr('class', 'sg-nodes')
    .selectAll('g')
    .data(nodes)
    .join('g')
    .attr('class', 'sg-node')
    .style('cursor', 'pointer')
    .call(
      d3.drag()
        .on('start', (event, d) => {
          if (!event.active) simulation.alphaTarget(0.3).restart()
          d.fx = d.x; d.fy = d.y
        })
        .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y })
        .on('end', (event, d) => {
          if (!event.active) simulation.alphaTarget(0)
          d.fx = null; d.fy = null
        })
    )
    .on('click', (_, d) => {
      selected.value = d
    })
    .on('dblclick', (_, d) => {
      drillInto(d.id)
    })
    .on('mouseover', (event, d) => showTip(event, `<b>${d.label}</b> — ${d.skill_count} 技能<br/><small>${d.tags.slice(0,5).join(', ')}</small>`))
    .on('mousemove', moveTip)
    .on('mouseout', hideTip)

  node.append('circle')
    .attr('r', d => radiusScale(d.skill_count))
    .attr('fill', d => catColor(d.id))
    .attr('fill-opacity', 0.85)
    .attr('stroke', d => catColor(d.id))
    .attr('stroke-width', 2)
    .attr('stroke-opacity', 0.4)

  node.append('text')
    .text(d => d.label)
    .attr('text-anchor', 'middle')
    .attr('dy', d => radiusScale(d.skill_count) + 13)
    .attr('font-size', 11)
    .attr('fill', '#abb2bf')

  node.append('text')
    .text(d => d.skill_count)
    .attr('text-anchor', 'middle')
    .attr('dy', '0.35em')
    .attr('font-size', d => Math.max(9, radiusScale(d.skill_count) * 0.55))
    .attr('fill', '#fff')
    .attr('pointer-events', 'none')

  simulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(edges).id(d => d.id).distance(d => 80 + d.weight * 5))
    .force('charge', d3.forceManyBody().strength(-250))
    .force('center', d3.forceCenter(w / 2, h / 2))
    .force('collision', d3.forceCollide(d => radiusScale(d.skill_count) + 12))
    .on('tick', () => {
      link
        .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x).attr('y2', d => d.target.y)
      node.attr('transform', d => `translate(${d.x},${d.y})`)
    })
}

// ── Skill-level graph ───────────────────────────────────────
function drawSkill(categoryId) {
  clearSvg()
  const catNode = graphData.nodes.find(n => n.id === categoryId)
  if (!catNode || !catNode.skills?.length) return

  const { w, h } = getSize()
  const svg = d3.select(svgEl.value)
    .attr('width', w).attr('height', h)

  const g = svg.append('g')
  svg.call(
    d3.zoom()
      .scaleExtent([0.2, 4])
      .on('zoom', ({ transform }) => g.attr('transform', transform))
  )

  const nodes = catNode.skills.map(s => ({ ...s, id: s.name }))

  // Edges: skills sharing >=1 tag
  const edges = []
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const shared = (nodes[i].tags || []).filter(t => (nodes[j].tags || []).includes(t))
      if (shared.length) edges.push({ source: nodes[i].id, target: nodes[j].id, weight: shared.length, shared_tags: shared })
    }
  }

  // If no tag edges, it's a solo cluster — just scatter them with no links
  const link = g.append('g')
    .selectAll('line')
    .data(edges)
    .join('line')
    .attr('stroke', 'rgba(111,186,255,0.2)')
    .attr('stroke-width', d => Math.min(d.weight, 3))

  const shortName = n => {
    const parts = n.id.split('/')
    return parts[parts.length - 1]
  }

  const node = g.append('g')
    .selectAll('g')
    .data(nodes)
    .join('g')
    .style('cursor', 'pointer')
    .call(
      d3.drag()
        .on('start', (event, d) => {
          if (!event.active) simulation.alphaTarget(0.3).restart()
          d.fx = d.x; d.fy = d.y
        })
        .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y })
        .on('end', (event, d) => {
          if (!event.active) simulation.alphaTarget(0)
          d.fx = null; d.fy = null
        })
    )
    .on('click', (_, d) => { selected.value = d })
    .on('mouseover', (event, d) => showTip(event, `<b>${shortName(d)}</b><br/><small>${(d.tags||[]).join(', ')}</small>`))
    .on('mousemove', moveTip)
    .on('mouseout', hideTip)

  node.append('circle')
    .attr('r', 10)
    .attr('fill', catColor(categoryId))
    .attr('fill-opacity', 0.8)
    .attr('stroke', catColor(categoryId))
    .attr('stroke-width', 1.5)
    .attr('stroke-opacity', 0.4)

  node.append('text')
    .text(d => shortName(d))
    .attr('text-anchor', 'middle')
    .attr('dy', 22)
    .attr('font-size', 10)
    .attr('fill', '#abb2bf')

  simulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(edges).id(d => d.id).distance(70))
    .force('charge', d3.forceManyBody().strength(-120))
    .force('center', d3.forceCenter(w / 2, h / 2))
    .force('collision', d3.forceCollide(24))
    .on('tick', () => {
      link
        .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x).attr('y2', d => d.target.y)
      node.attr('transform', d => `translate(${d.x},${d.y})`)
    })
}

// ────────────────────────────────────────────────────────────
// Tooltip helpers
// ────────────────────────────────────────────────────────────
function showTip(event, html) {
  const el = tooltip.value
  if (!el) return
  el.innerHTML = html
  el.style.display = 'block'
  moveTip(event)
}
function moveTip(event) {
  const el = tooltip.value
  if (!el) return
  const wrap = canvasWrap.value.getBoundingClientRect()
  el.style.left = (event.clientX - wrap.left + 12) + 'px'
  el.style.top = (event.clientY - wrap.top + 12) + 'px'
}
function hideTip() {
  if (tooltip.value) tooltip.value.style.display = 'none'
}

// ────────────────────────────────────────────────────────────
// Lifecycle
// ────────────────────────────────────────────────────────────
onMounted(async () => {
  await reload()
  // Redraw on container resize
  const ro = new ResizeObserver(() => draw())
  if (canvasWrap.value) ro.observe(canvasWrap.value)
  onUnmounted(() => ro.disconnect())
})
</script>

<style scoped>
.skill-graph-root {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 0;
  background: var(--bg-primary, #1a1d27);
  overflow: hidden;
}

.sg-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-bottom: 1px solid rgba(111,186,255,0.12);
  flex-shrink: 0;
  flex-wrap: wrap;
}

.sg-hint {
  font-size: 12px;
  color: rgba(171,178,191,0.6);
  margin-left: 4px;
}

.sg-back { margin-left: auto; }
.sg-refresh { color: rgba(111,186,255,0.8); }

.sg-canvas-wrap {
  flex: 1;
  position: relative;
  overflow: hidden;
  min-height: 0;
}

.sg-svg {
  width: 100%;
  height: 100%;
  display: block;
}

/* Tooltip */
.sg-tooltip {
  position: absolute;
  pointer-events: none;
  background: rgba(20,23,36,0.92);
  border: 1px solid rgba(111,186,255,0.25);
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 12px;
  color: #abb2bf;
  max-width: 220px;
  z-index: 10;
  line-height: 1.5;
}

/* Detail panel */
.sg-detail {
  position: absolute;
  right: 12px;
  top: 54px;
  width: 260px;
  background: rgba(20,23,36,0.95);
  border: 1px solid rgba(111,186,255,0.2);
  border-radius: 10px;
  padding: 14px;
  z-index: 20;
  backdrop-filter: blur(8px);
  max-height: calc(100% - 70px);
  overflow-y: auto;
}

.sg-detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.sg-detail-label {
  font-size: 14px;
  font-weight: 600;
  color: #6fbafe;
  word-break: break-all;
}

.sg-detail-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-bottom: 10px;
}

.sg-badge {
  background: rgba(111,186,255,0.15);
  color: #6fbafe;
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 11px;
}

.sg-tag {
  background: rgba(171,178,191,0.1);
  color: #abb2bf;
  border-radius: 4px;
  padding: 2px 7px;
  font-size: 11px;
}

.sg-skill-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
  max-height: 340px;
  overflow-y: auto;
}

.sg-skill-item {
  padding: 5px 8px;
  border-radius: 5px;
  cursor: pointer;
  transition: background 150ms;
}

.sg-skill-item:hover {
  background: rgba(111,186,255,0.1);
}

.sg-skill-name {
  font-size: 12px;
  color: #abb2bf;
  word-break: break-all;
}

/* Panel transition */
.sg-panel-enter-active, .sg-panel-leave-active {
  transition: opacity 200ms, transform 200ms;
}
.sg-panel-enter-from, .sg-panel-leave-to {
  opacity: 0;
  transform: translateX(16px);
}

/* Picker-btn overrides for toolbar */
.sg-toolbar .picker-btn {
  font-size: 12px;
  padding: 4px 10px;
  height: 28px;
}
</style>
