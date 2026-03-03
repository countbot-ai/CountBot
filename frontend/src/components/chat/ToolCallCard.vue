<template>
  <div class="tool-call-card" :class="[`status-${status}`, { collapsed: isCollapsed }]">
    <!-- 头部 - 紧凑行，可点击展开 -->
    <div class="tool-header" @click="toggleCollapse">
      <div class="status-dot" :class="`dot-${status}`">
        <component v-if="status === 'running'" :is="LoaderIcon" :size="12" class="spin" />
      </div>
      <component :is="getToolIcon()" :size="14" class="tool-type-icon" />
      <span class="tool-name">{{ toolName }}</span>
      <span v-if="isCollapsed && argumentPreview" class="tool-preview">{{ argumentPreview }}</span>
      <span v-if="duration !== null" class="tool-duration">{{ duration }}ms</span>
      <component :is="ChevronRightIcon" :size="14" class="chevron-icon" :class="{ expanded: !isCollapsed }" />
    </div>

    <!-- 可折叠内容 -->
    <transition name="slide">
      <div v-show="!isCollapsed" class="tool-body">
        <!-- 参数 -->
        <div v-if="hasArguments" class="tool-section">
          <div class="section-label">{{ $t('tools.arguments') }}</div>
          <div class="tool-arguments">
            <div v-for="(value, key) in arguments" :key="key" class="arg-item">
              <span class="arg-key">{{ key }}</span>
              <span class="arg-value">{{ formatValue(value) }}</span>
            </div>
          </div>
        </div>

        <!-- 结果 -->
        <div v-if="result" class="tool-section">
          <div class="section-label">
            <span>{{ $t('tools.result') }}</span>
            <button class="copy-btn" @click.stop="copyResult" :title="copied ? $t('common.copied') : $t('common.copy')">
              <component :is="copied ? CheckIcon : CopyIcon" :size="12" />
            </button>
          </div>
          <pre class="tool-result">{{ result }}</pre>
        </div>

        <!-- 错误 -->
        <div v-if="error" class="tool-section error-section">
          <div class="section-label error-label">{{ $t('tools.error') }}</div>
          <pre class="tool-error">{{ error }}</pre>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  Wrench as WrenchIcon,
  Terminal as TerminalIcon,
  FileText as FileIcon,
  Folder as FolderIcon,
  Globe as GlobeIcon,
  Loader2 as LoaderIcon,
  Copy as CopyIcon,
  Check as CheckIcon,
  ChevronRight as ChevronRightIcon,
  Pencil as PencilIcon
} from 'lucide-vue-next'
import { useToast } from '@/composables/useToast'
import { useI18n } from 'vue-i18n'

interface Props {
  toolName: string
  arguments?: Record<string, any>
  status: 'running' | 'success' | 'error'
  result?: string
  error?: string
  duration?: number | null
  timestamp?: Date
  defaultCollapsed?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  arguments: () => ({}),
  duration: null,
  timestamp: () => new Date(),
  defaultCollapsed: true
})

const { t } = useI18n()
const toast = useToast()
const copied = ref(false)
const isCollapsed = ref(props.defaultCollapsed)

const hasArguments = computed(() => {
  return props.arguments && Object.keys(props.arguments).length > 0
})

const argumentPreview = computed(() => {
  if (!props.arguments) return ''
  const keys = Object.keys(props.arguments)
  if (keys.length === 0) return ''
  // Show first meaningful argument as preview
  const firstKey = keys[0]
  const val = String(props.arguments[firstKey] || '')
  const preview = val.length > 60 ? val.slice(0, 60) + '...' : val
  return preview
})

const toggleCollapse = () => {
  isCollapsed.value = !isCollapsed.value
}

const getToolIcon = () => {
  if (!props.toolName) return WrenchIcon
  const name = props.toolName.toLowerCase()
  if (name.includes('exec') || name.includes('shell') || name.includes('command')) return TerminalIcon
  if (name.includes('write') || name.includes('edit') || name.includes('create')) return PencilIcon
  if (name.includes('read') || name.includes('file')) return FileIcon
  if (name.includes('list') || name.includes('dir')) return FolderIcon
  if (name.includes('web') || name.includes('search') || name.includes('fetch')) return GlobeIcon
  return WrenchIcon
}

const formatValue = (value: any): string => {
  if (typeof value === 'string') return value
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

const copyResult = async () => {
  try {
    await navigator.clipboard.writeText(props.result || '')
    copied.value = true
    toast.success(t('common.copied'))
    setTimeout(() => {
      copied.value = false
    }, 2000)
  } catch (error) {
    toast.error(t('common.copyFailed'))
  }
}
</script>

<style scoped>
/* ===== AI IDE 风格工具调用卡片 ===== */
.tool-call-card {
  border-radius: 6px;
  border: 1px solid var(--border-color, #e2e8f0);
  background: var(--bg-primary, #ffffff);
  overflow: hidden;
  transition: border-color 0.15s ease;
}

.tool-call-card:hover {
  border-color: var(--border-secondary, #cbd5e1);
}

/* 状态左边框指示条 */
.status-running {
  border-left: 2px solid var(--color-info, #0ea5e9);
}
.status-success {
  border-left: 2px solid var(--color-success, #10b981);
}
.status-error {
  border-left: 2px solid var(--color-error, #ef4444);
}

/* === 紧凑头部行 === */
.tool-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  cursor: pointer;
  user-select: none;
  transition: background 0.1s ease;
}
.tool-header:hover {
  background: var(--hover-bg, #f1f5f9);
}

/* 状态圆点 */
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}
.dot-running {
  width: 16px;
  height: 16px;
  color: var(--color-info, #0ea5e9);
}
.dot-success {
  background: var(--color-success, #10b981);
}
.dot-error {
  background: var(--color-error, #ef4444);
}

/* 工具类型图标 */
.tool-type-icon {
  color: var(--text-tertiary, #94a3b8);
  flex-shrink: 0;
}

/* 工具名称 */
.tool-name {
  font-size: 12px;
  font-weight: 500;
  font-family: var(--font-mono, 'SF Mono', 'Fira Code', monospace);
  color: var(--text-primary, #0f172a);
  white-space: nowrap;
  flex-shrink: 0;
}

/* 折叠时的参数预览 */
.tool-preview {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  color: var(--text-tertiary, #94a3b8);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: var(--font-mono, 'SF Mono', 'Fira Code', monospace);
}

/* 执行时长 */
.tool-duration {
  font-size: 11px;
  color: var(--text-tertiary, #94a3b8);
  flex-shrink: 0;
  font-family: var(--font-mono, 'SF Mono', 'Fira Code', monospace);
}

/* 展开/折叠箭头 */
.chevron-icon {
  color: var(--text-tertiary, #94a3b8);
  flex-shrink: 0;
  transition: transform 0.15s ease;
}
.chevron-icon.expanded {
  transform: rotate(90deg);
}

/* 加载动画 */
.spin {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* === 展开/折叠动画 === */
.slide-enter-active,
.slide-leave-active {
  transition: all 0.15s ease;
  overflow: hidden;
}
.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  max-height: 0;
}
.slide-enter-to,
.slide-leave-from {
  opacity: 1;
  max-height: 800px;
}

/* === 展开内容区 === */
.tool-body {
  border-top: 1px solid var(--border-color, #e2e8f0);
  background: var(--bg-secondary, #f8fafc);
}

.tool-section {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-color, #e2e8f0);
}
.tool-section:last-child {
  border-bottom: none;
}

.section-label {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary, #94a3b8);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.error-label {
  color: var(--color-error, #ef4444);
}

.copy-btn {
  margin-left: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--text-tertiary, #94a3b8);
  cursor: pointer;
  transition: all 0.1s ease;
}
.copy-btn:hover {
  background: var(--hover-bg, #f1f5f9);
  color: var(--text-primary, #0f172a);
}

/* 参数列表 */
.tool-arguments {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.arg-item {
  display: flex;
  gap: 6px;
  padding: 3px 6px;
  border-radius: 4px;
  background: var(--bg-primary, #ffffff);
  font-size: 12px;
  font-family: var(--font-mono, 'SF Mono', 'Fira Code', monospace);
  line-height: 1.5;
}
.arg-key {
  color: var(--text-tertiary, #94a3b8);
  flex-shrink: 0;
}
.arg-key::after {
  content: ':';
}
.arg-value {
  color: var(--text-primary, #0f172a);
  word-break: break-all;
}

/* 结果/错误 */
.tool-result,
.tool-error {
  margin: 0;
  padding: 6px 8px;
  border-radius: 4px;
  background: var(--bg-primary, #ffffff);
  font-size: 12px;
  font-family: var(--font-mono, 'SF Mono', 'Fira Code', monospace);
  line-height: 1.5;
  color: var(--text-primary, #0f172a);
  white-space: pre-wrap;
  word-wrap: break-word;
  max-height: 200px;
  overflow-y: auto;
}
.tool-error {
  color: var(--color-error, #ef4444);
}
</style>
