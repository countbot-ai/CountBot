<template>
  <div class="dependency-graph">
    <div class="graph-header">
      <h3>依赖关系图</h3>
      <div class="graph-controls">
        <button class="control-btn" @click="resetZoom" title="重置视图">
          <component :is="MaximizeIcon" :size="16" />
        </button>
        <button class="control-btn" @click="autoLayout" title="自动布局">
          <component :is="LayoutIcon" :size="16" />
        </button>
      </div>
    </div>

    <div ref="graphContainer" class="graph-container">
      <svg ref="svgElement" class="graph-svg">
        <defs>
          <marker
            id="arrowhead"
            markerWidth="10"
            markerHeight="10"
            refX="9"
            refY="3"
            orient="auto"
          >
            <polygon points="0 0, 10 3, 0 6" :fill="arrowColor" />
          </marker>
          <marker
            id="arrowhead-highlighted"
            markerWidth="10"
            markerHeight="10"
            refX="9"
            refY="3"
            orient="auto"
          >
            <polygon points="0 0, 10 3, 0 6" fill="#3b82f6" />
          </marker>
        </defs>

        <!-- 连线 -->
        <g class="edges">
          <line
            v-for="edge in edges"
            :key="`${edge.from}-${edge.to}`"
            :x1="edge.x1"
            :y1="edge.y1"
            :x2="edge.x2"
            :y2="edge.y2"
            class="edge"
            :class="{ highlighted: isEdgeHighlighted(edge) }"
            :marker-end="isEdgeHighlighted(edge) ? 'url(#arrowhead-highlighted)' : 'url(#arrowhead)'"
          />
        </g>

        <!-- 节点 -->
        <g class="nodes">
          <g
            v-for="node in nodes"
            :key="node.id"
            :transform="`translate(${node.x}, ${node.y})`"
            class="node"
            :class="{ 
              highlighted: highlightedNode === node.id,
              'has-condition': node.hasCondition
            }"
            @click="selectNode(node.id)"
            @mouseenter="hoverNode = node.id"
            @mouseleave="hoverNode = null"
          >
            <rect
              :width="nodeWidth"
              :height="nodeHeight"
              :x="-nodeWidth / 2"
              :y="-nodeHeight / 2"
              rx="8"
              class="node-rect"
            />
            <text
              class="node-label"
              text-anchor="middle"
              dy="0.3em"
            >
              {{ node.label }}
            </text>
            <text
              v-if="node.hasCondition"
              class="condition-indicator"
              text-anchor="middle"
              :y="nodeHeight / 2 - 8"
              font-size="10"
            >
              ⚡ 条件执行
            </text>
          </g>
        </g>
      </svg>

      <!-- 节点详情提示 -->
      <div
        v-if="hoverNode"
        class="node-tooltip"
        :style="getTooltipStyle(hoverNode)"
      >
        <div class="tooltip-content">
          <strong>{{ getNodeById(hoverNode)?.label }}</strong>
          <p v-if="getNodeById(hoverNode)?.task">{{ getNodeById(hoverNode)?.task }}</p>
          <div v-if="getNodeById(hoverNode)?.depends_on?.length" class="tooltip-deps">
            <span class="tooltip-label">依赖:</span>
            {{ getNodeById(hoverNode)?.depends_on.join(', ') }}
          </div>
        </div>
      </div>
    </div>

    <!-- 循环依赖警告 -->
    <div v-if="cycles.length > 0" class="cycle-warning">
      <component :is="AlertTriangleIcon" :size="16" />
      <div>
        <strong>检测到循环依赖！</strong>
        <p v-for="(cycle, index) in cycles" :key="index">
          {{ cycle.join(' → ') }} → {{ cycle[0] }}
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { Maximize as MaximizeIcon, Layout as LayoutIcon, AlertTriangle as AlertTriangleIcon } from 'lucide-vue-next'

interface Agent {
  id: string
  role?: string
  task?: string
  depends_on?: string[]
  condition?: any
}

interface Props {
  agents: Agent[]
}

const props = defineProps<Props>()

const graphContainer = ref<HTMLElement>()
const svgElement = ref<SVGElement>()
const highlightedNode = ref<string | null>(null)
const hoverNode = ref<string | null>(null)

// 动态计算箭头颜色以适应主题
const arrowColor = computed(() => {
  // 从CSS变量获取颜色，如果无法获取则使用默认值
  if (typeof window !== 'undefined' && graphContainer.value) {
    const style = getComputedStyle(graphContainer.value)
    const textTertiary = style.getPropertyValue('--text-tertiary').trim()
    return textTertiary || '#94a3b8'
  }
  return '#94a3b8'
})

const nodeWidth = 140
const nodeHeight = 60
const horizontalSpacing = 200
const verticalSpacing = 120

interface GraphNode {
  id: string
  label: string
  task?: string
  depends_on: string[]
  hasCondition: boolean
  x: number
  y: number
  level: number
}

interface GraphEdge {
  from: string
  to: string
  x1: number
  y1: number
  x2: number
  y2: number
}

// 计算节点层级（拓扑排序）
const calculateLevels = () => {
  const levels = new Map<string, number>()
  const visited = new Set<string>()
  
  const dfs = (nodeId: string): number => {
    if (visited.has(nodeId)) {
      return levels.get(nodeId) || 0
    }
    
    visited.add(nodeId)
    const agent = props.agents.find(a => a.id === nodeId)
    
    if (!agent || !agent.depends_on || agent.depends_on.length === 0) {
      levels.set(nodeId, 0)
      return 0
    }
    
    const maxDepLevel = Math.max(...agent.depends_on.map(dep => dfs(dep)))
    const level = maxDepLevel + 1
    levels.set(nodeId, level)
    return level
  }
  
  props.agents.forEach(agent => dfs(agent.id))
  return levels
}

// 检测循环依赖
const detectCycles = (): string[][] => {
  const cycles: string[][] = []
  const visited = new Set<string>()
  const recStack = new Set<string>()
  const path: string[] = []
  
  const dfs = (nodeId: string): boolean => {
    visited.add(nodeId)
    recStack.add(nodeId)
    path.push(nodeId)
    
    const agent = props.agents.find(a => a.id === nodeId)
    if (agent?.depends_on) {
      for (const dep of agent.depends_on) {
        if (!visited.has(dep)) {
          if (dfs(dep)) return true
        } else if (recStack.has(dep)) {
          // 找到循环
          const cycleStart = path.indexOf(dep)
          cycles.push(path.slice(cycleStart))
          return true
        }
      }
    }
    
    path.pop()
    recStack.delete(nodeId)
    return false
  }
  
  props.agents.forEach(agent => {
    if (!visited.has(agent.id)) {
      dfs(agent.id)
    }
  })
  
  return cycles
}

const cycles = computed(() => detectCycles())

// 计算节点位置
const nodes = computed<GraphNode[]>(() => {
  const levels = calculateLevels()
  const nodesByLevel = new Map<number, GraphNode[]>()
  
  // 按层级分组
  const graphNodes = props.agents.map(agent => ({
    id: agent.id,
    label: agent.role || agent.id,
    task: agent.task,
    depends_on: agent.depends_on || [],
    hasCondition: !!agent.condition,
    x: 0,
    y: 0,
    level: levels.get(agent.id) || 0,
  }))
  
  graphNodes.forEach(node => {
    const level = node.level
    if (!nodesByLevel.has(level)) {
      nodesByLevel.set(level, [])
    }
    nodesByLevel.get(level)!.push(node)
  })
  
  // 计算每层的位置
  const maxLevel = Math.max(...Array.from(levels.values()))
  const containerWidth = 800
  const containerHeight = 600
  
  nodesByLevel.forEach((nodesInLevel, level) => {
    const levelWidth = nodesInLevel.length * horizontalSpacing
    const startX = (containerWidth - levelWidth) / 2 + horizontalSpacing / 2
    const y = 80 + level * verticalSpacing
    
    nodesInLevel.forEach((node, index) => {
      node.x = startX + index * horizontalSpacing
      node.y = y
    })
  })
  
  return graphNodes
})

// 计算边
const edges = computed<GraphEdge[]>(() => {
  const result: GraphEdge[] = []
  
  nodes.value.forEach(node => {
    node.depends_on.forEach(depId => {
      const depNode = nodes.value.find(n => n.id === depId)
      if (depNode) {
        result.push({
          from: depId,
          to: node.id,
          x1: depNode.x,
          y1: depNode.y + nodeHeight / 2,
          x2: node.x,
          y2: node.y - nodeHeight / 2,
        })
      }
    })
  })
  
  return result
})

const selectNode = (nodeId: string) => {
  highlightedNode.value = highlightedNode.value === nodeId ? null : nodeId
}

const isEdgeHighlighted = (edge: GraphEdge) => {
  if (!highlightedNode.value) return false
  
  // 高亮选中节点的所有上下游
  const node = nodes.value.find(n => n.id === highlightedNode.value)
  if (!node) return false
  
  // 检查是否是直接依赖或被依赖
  return edge.from === highlightedNode.value || 
         edge.to === highlightedNode.value ||
         node.depends_on.includes(edge.from) ||
         nodes.value.some(n => n.depends_on.includes(highlightedNode.value!) && n.id === edge.to)
}

const getNodeById = (nodeId: string) => {
  return nodes.value.find(n => n.id === nodeId)
}

const getTooltipStyle = (nodeId: string) => {
  const node = getNodeById(nodeId)
  if (!node) return {}
  
  return {
    left: `${node.x + nodeWidth / 2 + 10}px`,
    top: `${node.y - nodeHeight / 2}px`,
  }
}

const resetZoom = () => {
  // 重置视图（简化版本）
  highlightedNode.value = null
}

const autoLayout = () => {
  // 触发重新计算布局
  highlightedNode.value = null
}
</script>
<style scoped>
@import './styles/DependencyGraph.css';
</style>
