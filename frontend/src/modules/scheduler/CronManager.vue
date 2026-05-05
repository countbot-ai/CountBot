<template>
  <div class="cron-manager">
    <!-- Header -->
    <div class="cron-header">
      <div class="header-content">
        <h2 class="title">
          {{ $t('cron.title') }}
        </h2>
        <p class="description">
          {{ $t('cron.description') }}
        </p>
      </div>
      <div class="header-actions">
        <button
          class="refresh-btn"
          :disabled="loading"
          @click="handleRefresh"
        >
          <component
            :is="RefreshIcon"
            :size="16"
            :class="{ 'spin': loading }"
          />
        </button>
        <button
          class="create-btn"
          @click="handleCreateJob"
        >
          <component
            :is="PlusIcon"
            :size="16"
          />
          {{ createButtonLabel }}
        </button>
      </div>
    </div>

    <!-- Compact Stats Bar -->
    <div
      v-if="!loading && jobs.length > 0"
      class="stats-bar-compact"
    >
      <div class="stat-item">
        <component :is="ClockIcon" :size="14" />
        <span>{{ jobs.length }}</span>
      </div>
      <div class="stat-divider"></div>
      <div class="stat-item success">
        <component :is="CheckCircleIcon" :size="14" />
        <span>{{ enabledCount }}</span>
      </div>
      <div class="stat-divider"></div>
      <div class="stat-item info">
        <component :is="PlayCircleIcon" :size="14" />
        <span class="next-run-text">{{ nextRunTime }}</span>
      </div>
    </div>

    <!-- Loading State -->
    <div
      v-if="loading"
      class="loading-state"
    >
      <component
        :is="LoaderIcon"
        :size="32"
        class="spin"
      />
      <p>{{ $t('common.loading') }}</p>
    </div>

    <!-- Error State -->
    <div
      v-else-if="error"
      class="error-state"
    >
      <component
        :is="AlertCircleIcon"
        :size="32"
      />
      <p>{{ error }}</p>
      <button
        class="retry-btn"
        @click="handleRefresh"
      >
        {{ $t('common.retry') }}
      </button>
    </div>

    <!-- Jobs List -->
    <div
      v-else-if="jobs.length > 0"
      class="jobs-list"
    >
      <div
        v-for="job in jobs"
        :key="job.id"
        class="job-card"
        :class="{ 'disabled': !job.enabled }"
      >
        <!-- Compact Card Header -->
        <div class="card-header-compact">
          <div class="job-main-info">
            <div class="job-title-row">
              <component :is="ClockIcon" :size="18" class="job-icon" />
              <h3 class="job-name">{{ job.name }}</h3>
              <span class="status-badge" :class="{ 'enabled': job.enabled }">
                {{ job.enabled ? $t('cron.enabled') : $t('cron.disabled') }}
              </span>
            </div>
            <div class="job-meta-row">
              <span class="job-schedule">{{ job.schedule }}</span>
              <span class="schedule-desc">{{ parseCronExpression(job.schedule) }}</span>
            </div>
          </div>
        </div>

        <!-- Compact Card Body -->
        <div class="card-body-compact">
          <!-- Message Preview -->
          <div class="job-message-compact">
            <component :is="MessageSquareIcon" :size="12" />
            <span>{{ getJobPreview(job) }}</span>
          </div>

          <!-- Channel Info (if applicable) -->
          <div v-if="job.deliver_response && job.channel" class="channel-info-compact">
            <component :is="SendIcon" :size="12" />
            <span>{{ job.channel }}</span>
            <span v-if="job.account_id" class="chat-id-compact">{{ job.account_id }}</span>
            <span v-if="job.chat_id" class="chat-id-compact">{{ truncateText(job.chat_id, 20) }}</span>
          </div>

          <!-- Execution Stats (Compact) -->
          <div v-if="job.run_count > 0" class="execution-stats-compact">
            <div class="stat-badge-compact">
              <component :is="BarChartIcon" :size="12" />
              <span>{{ job.run_count }}</span>
            </div>
            <div v-if="job.last_status === 'ok'" class="stat-badge-compact success">
              <component :is="CheckCircleIcon" :size="12" />
              <span>{{ $t('cron.statusOk') }}</span>
            </div>
            <div v-if="job.last_status === 'error'" class="stat-badge-compact error">
              <component :is="XCircleIcon" :size="12" />
              <span>{{ $t('cron.statusError') }}</span>
            </div>
            <div v-if="job.run_count > 0" class="stat-badge-compact">
              <span>{{ calculateSuccessRate(job) }}%</span>
            </div>
          </div>

          <!-- Time Info (Compact) -->
          <div class="time-info-compact">
            <div v-if="job.last_run" class="time-item-compact">
              <component :is="HistoryIcon" :size="12" />
              <span>{{ formatTime(job.last_run) }}</span>
            </div>
            <div v-if="job.next_run && job.enabled" class="time-item-compact next">
              <component :is="CalendarIcon" :size="12" />
              <span>{{ formatTime(job.next_run) }}</span>
            </div>
          </div>
        </div>

        <!-- Compact Card Footer with Clear Entry Points -->
        <div class="card-footer-compact">
          <!-- Primary Actions -->
          <div class="primary-actions">
            <button
              class="action-btn-compact primary"
              :disabled="!job.enabled || executingJobs.has(job.id)"
              @click="handleExecuteJob(job.id)"
              :title="$t('cron.executeNow')"
            >
              <component :is="executingJobs.has(job.id) ? LoaderIcon : PlayIcon" :size="14" :class="{ 'spin': executingJobs.has(job.id) }" />
              <span>{{ executingJobs.has(job.id) ? $t('cron.executing') : $t('cron.executeNow') }}</span>
            </button>
            
            <!-- 🎯 明显的详情入口 -->
            <button
              v-if="job.last_error || job.run_count > 0"
              class="action-btn-compact details"
              @click="toggleDetails(job.id)"
              :title="expandedJobs.has(job.id) ? $t('cron.hideDetails') : $t('cron.showDetails')"
            >
              <component :is="FileTextIcon" :size="14" />
              <span>{{ expandedJobs.has(job.id) ? $t('cron.hideDetails') : $t('cron.showDetails') }}</span>
            </button>
          </div>

          <!-- Secondary Actions -->
          <div class="secondary-actions">
            <button
              class="action-btn-icon"
              @click="handleEditJob(job)"
              :title="$t('common.edit')"
            >
              <component :is="EditIcon" :size="14" />
            </button>
            <button
              class="action-btn-icon toggle"
              :class="{ 'enabled': job.enabled }"
              @click="handleToggleJob(job.id, !job.enabled)"
              :title="job.enabled ? $t('cron.disableSuccess') : $t('cron.enableSuccess')"
            >
              <component :is="job.enabled ? ToggleRightIcon : ToggleLeftIcon" :size="14" />
            </button>
            <button
              class="action-btn-icon danger"
              @click="handleDeleteJob(job.id, job.name)"
              :title="$t('common.delete')"
            >
              <component :is="TrashIcon" :size="14" />
            </button>
          </div>
        </div>

        <!-- 展开的详情区域 -->
        <div
          v-if="expandedJobs.has(job.id)"
          class="details-panel"
        >
          <!-- Loading State -->
          <div
            v-if="loadingDetails.has(job.id)"
            class="detail-loading"
          >
            <component :is="LoaderIcon" :size="16" class="spin" />
            <span>{{ $t('common.loading') }}...</span>
          </div>
          
          <!-- Detail Content -->
          <template v-else>
            <div
              v-if="getJobDetail(job.id)?.last_error"
              class="detail-section error"
            >
              <div class="detail-header">
                <component :is="AlertCircleIcon" :size="14" />
                <span class="detail-title">{{ $t('cron.lastError') }}</span>
              </div>
              <pre class="detail-text">{{ getJobDetail(job.id)?.last_error }}</pre>
            </div>
            
            <div
              v-if="getJobDetail(job.id)?.last_response"
              class="detail-section success"
            >
              <div class="detail-header">
                <component :is="MessageSquareIcon" :size="14" />
                <span class="detail-title">{{ $t('cron.lastResponse') }}</span>
              </div>
              <pre class="detail-text">{{ getJobDetail(job.id)?.last_response }}</pre>
            </div>
            
            <!-- No Details Available -->
            <div
              v-if="!getJobDetail(job.id)?.last_error && !getJobDetail(job.id)?.last_response"
              class="detail-empty"
            >
              <component :is="AlertCircleIcon" :size="16" />
              <span>{{ $t('cron.noDetailsAvailable') }}</span>
            </div>
          </template>
        </div>
      </div>
    </div>

    <!-- Empty State -->
    <div
      v-else
      class="empty-state"
    >
      <component
        :is="ClockIcon"
        :size="48"
      />
      <h3>{{ emptyTitle }}</h3>
      <p>{{ emptyDescription }}</p>
      <button
        class="create-btn-large"
        @click="handleCreateJob"
      >
        <component
          :is="PlusIcon"
          :size="20"
        />
        {{ createButtonLabel }}
      </button>
    </div>

    <!-- Job Editor Modal -->
    <JobEditor
      v-if="showEditor"
      :job="editingJob"
      @close="handleCloseEditor"
      @save="handleSaveJob"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  RefreshCw as RefreshIcon,
  Loader2 as LoaderIcon,
  AlertCircle as AlertCircleIcon,
  Clock as ClockIcon,
  CheckCircle as CheckCircleIcon,
  PlayCircle as PlayCircleIcon,
  Plus as PlusIcon,
  MessageSquare as MessageSquareIcon,
  History as HistoryIcon,
  Calendar as CalendarIcon,
  Play as PlayIcon,
  Edit as EditIcon,
  ToggleLeft as ToggleLeftIcon,
  ToggleRight as ToggleRightIcon,
  Trash as TrashIcon,
  Send as SendIcon,
  BarChart as BarChartIcon,
  XCircle as XCircleIcon,
  FileText as FileTextIcon
} from 'lucide-vue-next'
import { useCronStore } from '@/store/cron'
import type { CronJob } from '@/api'
import { useToast } from '@/composables/useToast'
import JobEditor from './JobEditor.vue'

const { t } = useI18n()
const cronStore = useCronStore()
const toast = useToast()

// State
const showEditor = ref(false)
const editingJob = ref<CronJob | null>(null)
const expandedJobs = ref<Set<string>>(new Set())
const loadingDetails = ref<Set<string>>(new Set())
const executingJobs = ref<Set<string>>(new Set())

// Methods
const toggleDetails = async (jobId: string) => {
  if (expandedJobs.value.has(jobId)) {
    // 折叠
    expandedJobs.value.delete(jobId)
  } else {
    // 展开 - 加载完整详情
    expandedJobs.value.add(jobId)
    
    // 如果还没有加载详情，则加载
    if (!cronStore.jobDetails.has(jobId) && !loadingDetails.value.has(jobId)) {
      loadingDetails.value.add(jobId)
      try {
        await cronStore.getJobDetail(jobId)
      } catch (err: any) {
        toast.error(t('cron.loadDetailError'))
        expandedJobs.value.delete(jobId) // 加载失败时折叠
      } finally {
        loadingDetails.value.delete(jobId)
      }
    }
  }
}

// Helper to get job detail
const getJobDetail = (jobId: string) => {
  return cronStore.jobDetails.get(jobId)
}

const getJobPreview = (job: CronJob): string => {
  return truncateText(job.message, 80)
}

// Computed
const baseJobs = computed(() => cronStore.jobs.filter(j => !j.id.startsWith('builtin:')))
const jobs = computed(() => baseJobs.value)
const loading = computed(() => cronStore.loading)
const error = computed(() => cronStore.error)
const createButtonLabel = computed(() => t('cron.createJob'))
const emptyTitle = computed(() => t('cron.noJobs'))
const emptyDescription = computed(() => t('cron.noJobsDesc'))

const enabledCount = computed(() => 
  jobs.value.filter(j => j.enabled).length
)

const nextRunTime = computed(() => {
  const enabledJobs = jobs.value.filter(j => j.enabled && j.next_run)
  if (enabledJobs.length === 0) return t('cron.noScheduled')
  
  const nextJob = enabledJobs.reduce((earliest, job) => {
    if (!earliest.next_run || !job.next_run) return earliest
    return new Date(job.next_run) < new Date(earliest.next_run) ? job : earliest
  })
  
  return nextJob.next_run ? formatTime(nextJob.next_run) : t('cron.noScheduled')
})

// Methods
const formatTime = (isoString: string): string => {
  const date = new Date(isoString)
  const now = new Date()
  const diff = date.getTime() - now.getTime()
  const diffMinutes = Math.floor(diff / 60000)
  const diffHours = Math.floor(diff / 3600000)
  const diffDays = Math.floor(diff / 86400000)

  // 如果是过去的时间
  if (diff < 0) {
    const absDiffMinutes = Math.abs(diffMinutes)
    const absDiffHours = Math.abs(diffHours)
    const absDiffDays = Math.abs(diffDays)

    if (absDiffMinutes < 1) return t('sessions.justNow')
    if (absDiffMinutes < 60) return t('sessions.minutesAgo', { count: absDiffMinutes })
    if (absDiffHours < 24) return t('sessions.hoursAgo', { count: absDiffHours })
    return t('sessions.daysAgo', { count: absDiffDays })
  }

  // 如果是未来的时间
  if (diffMinutes < 1) return t('cron.inLessThanMinute')
  if (diffMinutes < 60) return t('cron.inMinutes', { count: diffMinutes })
  if (diffHours < 24) return t('cron.inHours', { count: diffHours })
  return t('cron.inDays', { count: diffDays })
}

const truncateText = (text: string, maxLength: number): string => {
  if (!text) return ''
  if (text.length <= maxLength) return text
  return text.substring(0, maxLength) + '...'
}

const calculateSuccessRate = (job: CronJob): number => {
  if (job.run_count === 0) return 0
  const successCount = job.run_count - job.error_count
  return Math.round((successCount / job.run_count) * 100)
}

const parseCronExpression = (cron: string): string => {
  // 简单的 Cron 表达式解析
  const parts = cron.trim().split(/\s+/)
  if (parts.length !== 5) return cron
  
  const [minute, hour, day, month, weekday] = parts
  
  // 常见模式
  if (cron === '* * * * *') return t('cron.patterns.everyMinute')
  if (cron === '*/5 * * * *') return t('cron.patterns.every5Minutes')
  if (cron === '*/15 * * * *') return t('cron.patterns.every15Minutes')
  if (cron === '*/30 * * * *') return t('cron.patterns.every30Minutes')
  if (cron === '0 * * * *') return t('cron.patterns.everyHour')
  if (cron === '0 0 * * *') return t('cron.patterns.everyDayMidnight')
  if (cron === '0 9 * * *') return t('cron.patterns.everyDay9AM')
  if (cron === '0 0 * * 0') return t('cron.patterns.everyWeekSunday')
  if (cron === '0 0 1 * *') return t('cron.patterns.everyMonth1st')
  
  // 自定义解析
  let result = ''
  
  // 分钟
  if (minute === '*') {
    result += t('cron.patterns.everyMinuteShort')
  } else if (minute.startsWith('*/')) {
    result += t('cron.patterns.everyNMinutes', { n: minute.slice(2) })
  } else {
    result += t('cron.patterns.atMinute', { minute })
  }
  
  // 小时
  if (hour !== '*') {
    if (hour.startsWith('*/')) {
      result += ' ' + t('cron.patterns.everyNHours', { n: hour.slice(2) })
    } else {
      result += ' ' + t('cron.patterns.atHour', { hour })
    }
  }
  
  // 日期
  if (day !== '*') {
    result += ' ' + t('cron.patterns.onDay', { day })
  }
  
  // 月份
  if (month !== '*') {
    result += ' ' + t('cron.patterns.inMonth', { month })
  }
  
  // 星期
  if (weekday !== '*') {
    const weekdays = ['日', '一', '二', '三', '四', '五', '六']
    result += ' ' + t('cron.patterns.onWeekday', { weekday: weekdays[parseInt(weekday)] || weekday })
  }
  
  return result || cron
}

const handleRefresh = async () => {
  try {
    await cronStore.loadJobs()
  } catch (err: any) {
    toast.error(t('cron.loadError'))
  }
}

const handleCreateJob = () => {
  editingJob.value = null
  showEditor.value = true
}

const handleEditJob = (job: CronJob) => {
  editingJob.value = job
  showEditor.value = true
}

const handleCloseEditor = () => {
  showEditor.value = false
  editingJob.value = null
}

const handleSaveJob = async (data: any) => {
  try {
    if (editingJob.value) {
      // 更新现有任务
      await cronStore.updateJob(editingJob.value.id, data)
      toast.success(t('cron.updateSuccess', { name: data.name || editingJob.value.name }))
    } else {
      // 创建新任务
      await cronStore.createJob(data)
      toast.success(t('cron.createSuccess', { name: data.name }))
    }
    handleCloseEditor()
  } catch (err: any) {
    toast.error(editingJob.value ? t('cron.updateError') : t('cron.createError'))
  }
}

const handleExecuteJob = async (id: string) => {
  if (executingJobs.value.has(id)) return // 防抖：正在执行中则忽略
  
  executingJobs.value.add(id)
  toast.success(t('cron.executeSubmitted'))
  
  try {
    await cronStore.executeJob(id)
  } catch (err: any) {
    toast.error(t('cron.executeError'))
  } finally {
    // 延迟移除执行状态，给后台任务一些时间
    setTimeout(() => {
      executingJobs.value.delete(id)
    }, 3000)
  }
}

const handleToggleJob = async (id: string, enabled: boolean) => {
  try {
    await cronStore.toggleJob(id, enabled)
    toast.success(
      enabled 
        ? t('cron.enableSuccess') 
        : t('cron.disableSuccess')
    )
  } catch (err: any) {
    toast.error(t('cron.toggleError'))
  }
}

const handleDeleteJob = async (id: string, name: string) => {
  if (!confirm(t('cron.deleteConfirm', { name }))) {
    return
  }

  try {
    await cronStore.deleteJob(id)
    toast.success(t('cron.deleteSuccess', { name }))
  } catch (err: any) {
    toast.error(t('cron.deleteError'))
  }
}

// Lifecycle
onMounted(() => {
  handleRefresh()
})
</script>
<style scoped>
@import './styles/CronManager.css';
</style>
