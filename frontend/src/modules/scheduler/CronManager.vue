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
          {{ $t('cron.createJob') }}
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
            <span>{{ truncateText(job.message, 60) }}</span>
          </div>

          <!-- Channel Info (if applicable) -->
          <div v-if="job.deliver_response && job.channel" class="channel-info-compact">
            <component :is="SendIcon" :size="12" />
            <span>{{ job.channel }}</span>
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
              v-if="job.last_error || job.last_response || job.run_count > 0"
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
      <h3>{{ $t('cron.noJobs') }}</h3>
      <p>{{ $t('cron.noJobsDesc') }}</p>
      <button
        class="create-btn-large"
        @click="handleCreateJob"
      >
        <component
          :is="PlusIcon"
          :size="20"
        />
        {{ $t('cron.createFirstJob') }}
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
  Activity as ActivityIcon,
  BarChart as BarChartIcon,
  XCircle as XCircleIcon,
  TrendingUp as TrendingUpIcon,
  ChevronDown as ChevronDownIcon,
  ChevronUp as ChevronUpIcon,
  FileText as FileTextIcon
} from 'lucide-vue-next'
import { useCronStore, type CronJob } from '@/store/cron'
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

// Computed
const jobs = computed(() => cronStore.jobs.filter(j => !j.id.startsWith('builtin:')))
const loading = computed(() => cronStore.loading)
const error = computed(() => cronStore.error)

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
.cron-manager {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--color-bg-secondary);
}

/* Header */
.cron-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: var(--spacing-xl);
  border-bottom: 1px solid var(--color-border-primary);
  background: var(--color-bg-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.header-content {
  flex: 1;
}

.title {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin: 0 0 var(--spacing-xs) 0;
}

.description {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin: 0;
}

.header-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.refresh-btn,
.create-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all var(--transition-base);
  box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
}

.refresh-btn {
  width: 36px;
  padding: var(--spacing-sm);
}

.refresh-btn:hover:not(:disabled) {
  background: var(--color-bg-secondary);
  border-color: var(--color-primary);
  box-shadow: 0 2px 4px 0 rgba(0, 0, 0, 0.1);
}

.create-btn:hover {
  background: var(--color-bg-secondary);
  border-color: var(--color-primary);
  box-shadow: 0 2px 4px 0 rgba(0, 0, 0, 0.1);
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.create-btn {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: white;
}

.create-btn:hover {
  background: var(--color-primary-hover);
  box-shadow: 0 4px 6px -1px rgba(59, 130, 246, 0.3);
}

/* Compact Stats Bar */
.stats-bar-compact {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-lg);
  border-bottom: 1px solid var(--color-border-primary);
  background: var(--color-bg-primary);
  font-size: var(--font-size-xs);
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--color-text-secondary);
  font-weight: var(--font-weight-medium);
}

.stat-item.success {
  color: var(--color-success);
}

.stat-item.info {
  color: var(--color-primary);
  flex: 1;
}

.stat-divider {
  width: 1px;
  height: 16px;
  background: var(--color-border-secondary);
}

.next-run-text {
  font-size: var(--font-size-xs);
}

/* States */
.loading-state,
.error-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-md);
  flex: 1;
  padding: var(--spacing-3xl);
  color: var(--color-text-secondary);
  text-align: center;
}

.error-state {
  color: var(--color-error);
}

.empty-state h3 {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin: 0;
}

.empty-state p {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin: 0;
}

.retry-btn,
.create-btn-large {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: all var(--transition-base);
}

.retry-btn:hover,
.create-btn-large:hover {
  background: var(--color-bg-secondary);
  border-color: var(--color-primary);
}

.create-btn-large {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: white;
}

.create-btn-large:hover {
  background: var(--color-primary-dark);
}

/* Jobs List - More Compact */
.jobs-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  padding: var(--spacing-md);
  overflow-y: auto;
  flex: 1;
}

.job-card {
  display: flex;
  flex-direction: column;
  padding: var(--spacing-md);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  background: var(--color-bg-primary);
  transition: all var(--transition-base);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.job-card:hover {
  border-color: var(--color-primary);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.1);
  transform: translateY(-2px);
}

.job-card.disabled {
  opacity: 0.6;
  background: var(--color-bg-tertiary);
}

/* Compact Card Header */
.card-header-compact {
  margin-bottom: var(--spacing-sm);
}

.job-main-info {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.job-title-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.job-icon {
  color: var(--color-primary);
  flex-shrink: 0;
}

.job-name {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin: 0;
  flex: 1;
}

.status-badge {
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: 10px;
  font-weight: var(--font-weight-semibold);
  background: var(--color-bg-tertiary);
  color: var(--color-text-tertiary);
  border: 1px solid var(--color-border-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.status-badge.enabled {
  background: var(--color-success-light);
  color: var(--color-success);
  border-color: var(--color-success);
}

.job-meta-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
  margin-left: 26px;
}

.job-schedule {
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--color-primary);
  background: rgba(59, 130, 246, 0.1);
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  font-weight: var(--font-weight-semibold);
  border: 1px solid var(--color-primary);
}

.schedule-desc {
  font-size: 11px;
  color: var(--color-text-tertiary);
  padding: 3px 8px;
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-secondary);
}

/* Compact Card Body */
.card-body-compact {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: var(--spacing-sm);
  font-size: var(--font-size-xs);
}

.job-message-compact {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-primary);
  color: var(--color-text-secondary);
}

.job-message-compact svg {
  flex-shrink: 0;
  opacity: 0.6;
}

.channel-info-compact {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  background: rgba(59, 130, 246, 0.08);
  border: 1px solid var(--color-primary);
  color: var(--color-primary);
  font-size: 11px;
  font-weight: var(--font-weight-medium);
}

.channel-info-compact svg {
  flex-shrink: 0;
}

.chat-id-compact {
  font-family: var(--font-mono);
  font-size: 10px;
  opacity: 0.7;
}

.execution-stats-compact {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.stat-badge-compact {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--color-border-secondary);
  font-size: 11px;
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
}

.stat-badge-compact svg {
  flex-shrink: 0;
}

.stat-badge-compact.success {
  background: rgba(16, 185, 129, 0.1);
  border-color: var(--color-success);
  color: var(--color-success);
}

.stat-badge-compact.error {
  background: rgba(239, 68, 68, 0.1);
  border-color: var(--color-error);
  color: var(--color-error);
}

.time-info-compact {
  display: flex;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
}

.time-item-compact {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--color-text-tertiary);
}

.time-item-compact svg {
  flex-shrink: 0;
  opacity: 0.6;
}

.time-item-compact.next {
  color: var(--color-primary);
  font-weight: var(--font-weight-medium);
}

.card-footer-compact {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: var(--spacing-sm);
  border-top: 1px solid var(--color-border-primary);
  gap: var(--spacing-sm);
}

.primary-actions {
  display: flex;
  gap: var(--spacing-xs);
  flex: 1;
}

.secondary-actions {
  display: flex;
  gap: var(--spacing-xs);
}

.action-btn-compact {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-sm);
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
  font-size: 12px;
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all var(--transition-base);
  white-space: nowrap;
}

.action-btn-compact:hover:not(:disabled) {
  background: var(--color-bg-secondary);
  border-color: var(--color-primary);
  color: var(--color-primary);
  transform: translateY(-1px);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.action-btn-compact:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-btn-compact.primary {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: white;
}

.action-btn-compact.primary:hover:not(:disabled) {
  background: var(--color-primary-hover);
  border-color: var(--color-primary-hover);
  color: white;
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3);
}

.action-btn-compact.details {
  background: var(--color-bg-secondary);
  border-color: var(--color-border-primary);
  color: var(--color-text-secondary);
}

.action-btn-compact.details:hover {
  background: var(--color-bg-tertiary);
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.action-btn-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-sm);
  background: var(--color-bg-primary);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-base);
}

.action-btn-icon:hover {
  background: var(--color-bg-secondary);
  border-color: var(--color-primary);
  color: var(--color-primary);
  transform: translateY(-1px);
}

.action-btn-icon.toggle.enabled {
  background: var(--color-success-light);
  border-color: var(--color-success);
  color: var(--color-success);
}

.action-btn-icon.danger:hover {
  background: var(--color-error-light);
  border-color: var(--color-error);
  color: var(--color-error);
}

/* Details Panel */
.details-panel {
  margin-top: var(--spacing-sm);
  padding: var(--spacing-sm);
  border-top: 1px solid var(--color-border-primary);
  background: var(--color-bg-secondary);
  border-radius: 0 0 var(--radius-md) var(--radius-md);
  animation: slideDown 0.2s ease-out;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.detail-section {
  padding: var(--spacing-sm);
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-secondary);
  background: var(--color-bg-primary);
  margin-bottom: var(--spacing-xs);
}

.detail-section:last-child {
  margin-bottom: 0;
}

.detail-section.error {
  background: rgba(239, 68, 68, 0.05);
  border-color: var(--color-error);
}

.detail-section.success {
  background: rgba(16, 185, 129, 0.05);
  border-color: var(--color-success);
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  font-size: 11px;
  font-weight: var(--font-weight-semibold);
}

.detail-section.error .detail-header {
  color: var(--color-error);
}

.detail-section.success .detail-header {
  color: var(--color-success);
}

.detail-text {
  margin: 0;
  padding: 8px;
  border-radius: var(--radius-sm);
  background: var(--color-bg-tertiary);
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--color-text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow-y: auto;
  border: 1px solid var(--color-border-primary);
  line-height: 1.5;
}

.detail-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: var(--spacing-md);
  color: var(--color-text-tertiary);
  font-size: 12px;
}

.detail-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: var(--spacing-md);
  color: var(--color-text-tertiary);
  font-size: 12px;
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-secondary);
}

/* Animations */
.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

/* 深色模式适配 */
:root[data-theme="dark"] .cron-manager {
  background: var(--color-bg-secondary);
}

:root[data-theme="dark"] .cron-header {
  background: var(--color-bg-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

:root[data-theme="dark"] .stats-bar-compact {
  background: var(--color-bg-primary);
}

:root[data-theme="dark"] .job-card {
  background: var(--color-bg-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

:root[data-theme="dark"] .job-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

:root[data-theme="dark"] .job-card.disabled {
  background: var(--color-bg-tertiary);
}

:root[data-theme="dark"] .empty-state,
:root[data-theme="dark"] .loading-state,
:root[data-theme="dark"] .error-state {
  background: transparent;
}
</style>
