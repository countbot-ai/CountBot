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
                    <div v-if="resolveToolCount(message) > 0" class="timeline-tools">
                      <component :is="WrenchIcon" :size="12" />
                      <span>{{ resolveToolCount(message) }} {{ $t('timeline.tools') || '个工具' }}</span>
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
import { computed, ref } from 'vue'
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
  toolCallCount?: number
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

const resolveToolCount = (message: Message): number => {
  return Math.max(message.toolCallCount || 0, message.toolCalls?.length || 0)
}

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
@import './styles/TimelinePanel.css';
</style>
