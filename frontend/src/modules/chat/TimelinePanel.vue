<template>
  <div class="timeline-panel">
    <div class="timeline-header">
      <h3 class="timeline-title">{{ $t('timeline.title') || '时间轴' }}</h3>
      <button class="close-btn" @click="$emit('close')" :title="$t('common.close') || '关闭'">
        <component :is="XIcon" :size="18" />
      </button>
    </div>
    
    <!-- 搜索框 -->
    <div class="timeline-search">
      <component :is="SearchIcon" :size="16" class="search-icon" />
      <input
        v-model="searchQuery"
        type="text"
        :placeholder="$t('timeline.searchPlaceholder') || '搜索消息...'"
        class="search-input"
      />
      <button
        v-if="searchQuery"
        class="clear-search-btn"
        @click="searchQuery = ''"
        :title="$t('common.clear') || '清除'"
      >
        <component :is="XIcon" :size="14" />
      </button>
    </div>
    
    <div class="timeline-content">
      <div v-if="filteredGroupedMessages.length === 0" class="timeline-empty">
        <component :is="searchQuery ? SearchIcon : ClockIcon" :size="48" class="empty-icon" />
        <p>{{ searchQuery ? ($t('timeline.noResults') || '未找到匹配的消息') : ($t('timeline.empty') || '暂无消息') }}</p>
      </div>
      
      <div v-else class="timeline-list">
        <div
          v-for="group in filteredGroupedMessages"
          :key="group.date"
          class="timeline-group"
        >
          <div 
            class="timeline-date"
            :class="{ collapsed: collapsedDates.has(group.date) }"
            @click="toggleDateCollapse(group.date)"
          >
            <component 
              :is="ChevronDownIcon" 
              :size="16" 
              class="collapse-icon"
              :class="{ rotated: collapsedDates.has(group.date) }"
            />
            <span class="date-text">{{ group.dateLabel }}</span>
            <span class="message-count">{{ group.messages.length }}</span>
          </div>
          
          <transition name="collapse">
            <div v-show="!collapsedDates.has(group.date)" class="timeline-items">
              <div
                v-for="message in group.messages"
                :key="message.id"
                class="timeline-item"
                :class="{ 
                  active: activeMessageId === message.id,
                  'is-user': message.role === 'user',
                  'is-assistant': message.role === 'assistant'
                }"
                @click="scrollToMessage(message.id)"
              >
                <div class="timeline-dot" :class="`role-${message.role}`" />
                <div class="timeline-card">
                  <div class="timeline-time">{{ formatTime(message.timestamp) }}</div>
                  <div class="timeline-preview">
                    <div class="timeline-role">
                      <component
                        :is="message.role === 'user' ? UserIcon : BotIcon"
                        :size="14"
                      />
                      <span>{{ message.role === 'user' ? ($t('timeline.user') || '用户') : ($t('timeline.assistant') || '助手') }}</span>
                    </div>
                    <div class="timeline-text" v-html="highlightSearchText(truncateText(message.content, 80))"></div>
                    <div v-if="message.toolCalls && message.toolCalls.length > 0" class="timeline-tools">
                      <component :is="WrenchIcon" :size="12" />
                      <span>{{ message.toolCalls.length }} {{ $t('timeline.tools') || '个工具' }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </transition>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  X as XIcon,
  Clock as ClockIcon,
  User as UserIcon,
  Bot as BotIcon,
  Wrench as WrenchIcon,
  Search as SearchIcon,
  ChevronDown as ChevronDownIcon
} from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  toolCalls?: any[]
}

interface Props {
  messages: Message[]
  activeMessageId?: string | null
}

interface Emits {
  (e: 'close'): void
  (e: 'scroll-to', messageId: string): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const { t } = useI18n()

const searchQuery = ref('')
const collapsedDates = ref(new Set<string>())

interface MessageGroup {
  date: string
  dateLabel: string
  messages: Message[]
}

const toggleDateCollapse = (date: string) => {
  if (collapsedDates.value.has(date)) {
    collapsedDates.value.delete(date)
  } else {
    collapsedDates.value.add(date)
  }
  // 触发响应式更新
  collapsedDates.value = new Set(collapsedDates.value)
}

const groupedMessages = computed<MessageGroup[]>(() => {
  const groups = new Map<string, Message[]>()
  
  props.messages.forEach(msg => {
    const date = new Date(msg.timestamp)
    const dateKey = date.toISOString().split('T')[0]
    
    if (!groups.has(dateKey)) {
      groups.set(dateKey, [])
    }
    groups.get(dateKey)!.push(msg)
  })
  
  const result: MessageGroup[] = []
  const today = new Date()
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)
  
  groups.forEach((messages, dateKey) => {
    const date = new Date(dateKey)
    let dateLabel = ''
    
    if (dateKey === today.toISOString().split('T')[0]) {
      dateLabel = t('timeline.today') || '今天'
    } else if (dateKey === yesterday.toISOString().split('T')[0]) {
      dateLabel = t('timeline.yesterday') || '昨天'
    } else {
      dateLabel = date.toLocaleDateString('zh-CN', {
        month: 'long',
        day: 'numeric'
      })
    }
    
    result.push({
      date: dateKey,
      dateLabel,
      messages: messages.sort((a, b) => 
        new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
      )
    })
  })
  
  return result.sort((a, b) => b.date.localeCompare(a.date))
})

const formatTime = (timestamp: Date) => {
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit'
  })
}

const truncateText = (text: string, maxLength: number) => {
  if (!text) return ''
  if (text.length <= maxLength) return text
  return text.substring(0, maxLength) + '...'
}

const scrollToMessage = (messageId: string) => {
  emit('scroll-to', messageId)
}

const filteredGroupedMessages = computed<MessageGroup[]>(() => {
  if (!searchQuery.value.trim()) {
    return groupedMessages.value
  }
  
  const query = searchQuery.value.toLowerCase()
  const filtered: MessageGroup[] = []
  
  groupedMessages.value.forEach(group => {
    const matchedMessages = group.messages.filter(msg => 
      msg.content.toLowerCase().includes(query)
    )
    
    if (matchedMessages.length > 0) {
      filtered.push({
        ...group,
        messages: matchedMessages
      })
    }
  })
  
  return filtered
})

const highlightSearchText = (text: string): string => {
  if (!searchQuery.value.trim()) {
    return text
  }
  
  const query = searchQuery.value.trim()
  const regex = new RegExp(`(${query})`, 'gi')
  return text.replace(regex, '<mark>$1</mark>')
}
</script>

<style scoped>
.timeline-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-primary, #ffffff);
}

.timeline-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color, #e5e7eb);
  flex-shrink: 0;
}

.timeline-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary, #111827);
}

.close-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: var(--radius-md, 8px);
  background: transparent;
  color: var(--text-secondary, #6b7280);
  cursor: pointer;
  transition: all 0.15s ease;
}

.close-btn:hover {
  background: var(--hover-bg, #f3f4f6);
  color: var(--text-primary, #111827);
}

/* 搜索框 */
.timeline-search {
  position: relative;
  padding: 12px 20px;
  border-bottom: 1px solid var(--border-color, #e5e7eb);
  flex-shrink: 0;
}

.search-icon {
  position: absolute;
  left: 32px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-tertiary, #9ca3af);
  pointer-events: none;
}

.search-input {
  width: 100%;
  padding: 8px 32px 8px 36px;
  border: 1.5px solid var(--border-color, #e5e7eb);
  border-radius: var(--radius-md, 8px);
  background: var(--bg-secondary, #f9fafb);
  color: var(--text-primary, #111827);
  font-size: 13px;
  outline: none;
  transition: all 0.15s ease;
}

.search-input:focus {
  border-color: var(--color-primary, #3b82f6);
  background: var(--bg-primary, #ffffff);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.search-input::placeholder {
  color: var(--text-disabled, #9ca3af);
}

.clear-search-btn {
  position: absolute;
  right: 28px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border: none;
  border-radius: 50%;
  background: var(--text-tertiary, #9ca3af);
  color: #ffffff;
  cursor: pointer;
  transition: all 0.15s ease;
}

.clear-search-btn:hover {
  background: var(--text-secondary, #6b7280);
}

.timeline-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px 0;
}

.timeline-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 12px;
  color: var(--text-tertiary, #9ca3af);
}

.empty-icon {
  opacity: 0.5;
}

.timeline-list {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.timeline-group {
  display: flex;
  flex-direction: column;
  gap: 0;
}

/* 日期折叠头 */
.timeline-date {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  background: var(--bg-primary, #ffffff);
  border-bottom: 1px solid var(--border-color, #e5e7eb);
  cursor: pointer;
  user-select: none;
  transition: all 0.15s ease;
}

.timeline-date:hover {
  background: var(--hover-bg, #f9fafb);
}

.collapse-icon {
  flex-shrink: 0;
  color: var(--text-tertiary, #9ca3af);
  transition: transform 0.2s ease;
}

.collapse-icon.rotated {
  transform: rotate(-90deg);
}

.date-text {
  flex: 1;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary, #6b7280);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.message-count {
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: 12px;
  background: var(--bg-tertiary, #f3f4f6);
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary, #6b7280);
}

/* 折叠动画 */
.collapse-enter-active,
.collapse-leave-active {
  transition: all 0.3s ease;
  overflow: hidden;
}

.collapse-enter-from,
.collapse-leave-to {
  max-height: 0;
  opacity: 0;
}

.collapse-enter-to,
.collapse-leave-from {
  max-height: 2000px;
  opacity: 1;
}

.timeline-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 20px;
}

.timeline-item {
  position: relative;
  display: flex;
  gap: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.timeline-item:hover .timeline-card {
  background: var(--hover-bg, #f9fafb);
  border-color: var(--text-tertiary, #9ca3af);
  transform: translateX(-2px);
}

.timeline-item.active .timeline-card {
  background: var(--color-primary-alpha, rgba(59, 130, 246, 0.1));
  border-color: var(--color-primary, #3b82f6);
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.15);
}

.timeline-item.active .timeline-dot {
  background: var(--color-primary, #3b82f6);
  box-shadow: 0 0 0 4px var(--color-primary-alpha, rgba(59, 130, 246, 0.2));
  transform: scale(1.2);
}

/* 时间轴点 - 根据角色区分颜色 */
.timeline-dot {
  position: relative;
  flex-shrink: 0;
  width: 10px;
  height: 10px;
  margin-top: 8px;
  border-radius: 50%;
  border: 2px solid var(--bg-primary, #ffffff);
  transition: all 0.2s ease;
}

.timeline-dot.role-user {
  background: #64748b;
}

.timeline-dot.role-assistant {
  background: #3b82f6;
}

.timeline-dot::before {
  content: '';
  position: absolute;
  top: 18px;
  left: 50%;
  width: 2px;
  height: calc(100% + 20px);
  background: var(--border-color, #e5e7eb);
  transform: translateX(-50%);
}

.timeline-item:last-child .timeline-dot::before {
  display: none;
}

.timeline-card {
  flex: 1;
  padding: 12px 14px;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: var(--radius-md, 8px);
  background: var(--bg-primary, #ffffff);
  transition: all 0.2s ease;
}

.timeline-time {
  margin-bottom: 6px;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-tertiary, #9ca3af);
}

.timeline-preview {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.timeline-role {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary, #6b7280);
}

.timeline-text {
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-primary, #374151);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}

/* 搜索高亮 */
.timeline-text :deep(mark) {
  background: #fef08a;
  color: #854d0e;
  padding: 1px 2px;
  border-radius: 2px;
  font-weight: 500;
}

.timeline-tools {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: var(--radius-sm, 6px);
  background: var(--bg-tertiary, #f3f4f6);
  font-size: 11px;
  font-weight: 500;
  color: var(--text-tertiary, #6b7280);
  width: fit-content;
}

/* 滚动条样式 */
.timeline-content::-webkit-scrollbar {
  width: 6px;
}

.timeline-content::-webkit-scrollbar-track {
  background: transparent;
}

.timeline-content::-webkit-scrollbar-thumb {
  background: var(--border-color, #e5e7eb);
  border-radius: 3px;
}

.timeline-content::-webkit-scrollbar-thumb:hover {
  background: var(--text-tertiary, #9ca3af);
}

/* 深色模式 */
:root[data-theme="dark"] .timeline-panel {
  background: var(--bg-primary, #0a0e1a);
}

:root[data-theme="dark"] .timeline-header {
  border-bottom-color: var(--border-color, #1f2937);
}

:root[data-theme="dark"] .timeline-search {
  border-bottom-color: var(--border-color, #1f2937);
}

:root[data-theme="dark"] .search-input {
  background: var(--bg-secondary, #0e1422);
  border-color: var(--border-color, #1f2937);
  color: var(--text-primary, #e5e7eb);
}

:root[data-theme="dark"] .search-input:focus {
  border-color: #00f0ff;
  background: var(--bg-primary, #0a0e1a);
  box-shadow: 0 0 0 3px rgba(0, 240, 255, 0.1);
}

:root[data-theme="dark"] .timeline-date {
  background: var(--bg-primary, #0a0e1a);
  border-bottom-color: var(--border-color, #1f2937);
}

:root[data-theme="dark"] .timeline-date:hover {
  background: var(--bg-secondary, #0e1422);
}

:root[data-theme="dark"] .message-count {
  background: var(--bg-tertiary, #1f2937);
  color: var(--text-tertiary, #9ca3af);
}

:root[data-theme="dark"] .timeline-card {
  background: var(--bg-secondary, #0e1422);
  border-color: var(--border-color, #1f2937);
}

:root[data-theme="dark"] .timeline-item:hover .timeline-card {
  background: var(--bg-tertiary, #131b2c);
  border-color: var(--text-tertiary, #4b5563);
}

:root[data-theme="dark"] .timeline-item.active .timeline-card {
  background: rgba(0, 240, 255, 0.1);
  border-color: #00f0ff;
  box-shadow: 0 2px 8px rgba(0, 240, 255, 0.15);
}

:root[data-theme="dark"] .timeline-item.active .timeline-dot {
  background: #00f0ff;
  box-shadow: 0 0 0 4px rgba(0, 240, 255, 0.2);
}

:root[data-theme="dark"] .timeline-dot {
  border-color: var(--bg-primary, #0a0e1a);
}

:root[data-theme="dark"] .timeline-dot.role-user {
  background: #64748b;
}

:root[data-theme="dark"] .timeline-dot.role-assistant {
  background: #00f0ff;
}

:root[data-theme="dark"] .timeline-dot::before {
  background: var(--border-color, #1f2937);
}

:root[data-theme="dark"] .timeline-tools {
  background: var(--bg-tertiary, #1f2937);
}

:root[data-theme="dark"] .timeline-text :deep(mark) {
  background: #854d0e;
  color: #fef08a;
}
</style>
