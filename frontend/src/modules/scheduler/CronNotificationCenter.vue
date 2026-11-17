<template>
  <Teleport to="body">
    <TransitionGroup name="cron-notice" tag="div" class="cron-notice-stack">
      <article
        v-for="notice in notices"
        :key="notice.id"
        class="cron-notice"
        :class="notice.status === 'ok' ? 'is-success' : 'is-error'"
        role="status"
        tabindex="0"
        @click="openNotice(notice)"
        @keydown.enter.prevent="openNotice(notice)"
        @keydown.space.prevent="openNotice(notice)"
      >
        <div class="cron-notice-accent" />
        <div class="cron-notice-icon">
          <component :is="notice.status === 'ok' ? CheckCircleIcon : AlertCircleIcon" :size="20" />
        </div>
        <div class="cron-notice-body">
          <div class="cron-notice-head">
            <span class="cron-notice-kicker">{{ $t('cron.webNotify.kicker') }}</span>
            <button
              type="button"
              class="cron-notice-close"
              :aria-label="$t('common.close')"
              @click.stop="removeNotice(notice.id)"
            >
              <XIcon :size="14" />
            </button>
          </div>
          <h4 class="cron-notice-title">
            {{ notice.status === 'ok'
              ? $t('cron.webNotify.successTitle', { name: notice.jobName })
              : $t('cron.webNotify.failedTitle', { name: notice.jobName }) }}
          </h4>
          <p class="cron-notice-preview">{{ noticePreview(notice) }}</p>
          <button type="button" class="cron-notice-action" @click.stop="openNotice(notice)">
            {{ $t('cron.webNotify.viewDetail') }}
            <ArrowUpRightIcon :size="13" />
          </button>
        </div>
      </article>
    </TransitionGroup>

    <CronResultModal
      v-model="modalVisible"
      :job-id="selected?.jobId"
      :payload="selected"
    />
  </Teleport>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import {
  AlertCircle as AlertCircleIcon,
  ArrowUpRight as ArrowUpRightIcon,
  CheckCircle as CheckCircleIcon,
  X as XIcon,
} from 'lucide-vue-next'
import CronResultModal from './CronResultModal.vue'
import {
  onCronResultNotification,
  type CronResultNotification,
} from './cronNotifications'

interface Notice extends CronResultNotification {
  id: number
}

const MAX_NOTICES = 3
const AUTO_DISMISS_MS = 12000

const notices = ref<Notice[]>([])
const selected = ref<Notice | null>(null)
const modalVisible = ref(false)

let nextId = 0
let dispose: (() => void) | null = null
const dismissTimers = new Map<number, number>()

function noticePreview(notice: Notice): string {
  if (notice.status === 'error') {
    return (notice.error || '').replace(/\s+/g, ' ').slice(0, 110) || '—'
  }
  return (notice.response || '')
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/[#>*_`~-]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 110) || '—'
}

function clearDismissTimer(id: number) {
  const timer = dismissTimers.get(id)
  if (timer !== undefined) {
    window.clearTimeout(timer)
    dismissTimers.delete(id)
  }
}

function removeNotice(id: number) {
  clearDismissTimer(id)
  notices.value = notices.value.filter((notice) => notice.id !== id)
}

function scheduleDismiss(id: number) {
  clearDismissTimer(id)
  const timer = window.setTimeout(() => removeNotice(id), AUTO_DISMISS_MS)
  dismissTimers.set(id, timer)
}

/**
 * 简单双音提示音，不依赖音频资源；浏览器自动播放策略拒绝时静默降级。
 */
function playChime() {
  try {
    const AudioCtor = window.AudioContext || (window as any).webkitAudioContext
    if (!AudioCtor) return
    const context = new AudioCtor()
    const gain = context.createGain()
    gain.gain.value = 0.08
    gain.connect(context.destination)
    const playNotes = () => {
      ;[880, 1320].forEach((frequency, index) => {
        const oscillator = context.createOscillator()
        oscillator.type = 'sine'
        oscillator.frequency.value = frequency
        oscillator.connect(gain)
        const startAt = context.currentTime + index * 0.09
        oscillator.start(startAt)
        oscillator.stop(startAt + 0.14)
      })
      window.setTimeout(() => void context.close(), 700)
    }
    if (context.state === 'suspended') {
      void context.resume().then(playNotes).catch(() => void context.close())
    } else {
      playNotes()
    }
  } catch (error) {
    console.debug('[cron] notification sound unavailable:', error)
  }
}

function handleResult(payload: CronResultNotification) {
  const notice: Notice = { ...payload, id: ++nextId }
  const previous = notices.value
  notices.value = [notice, ...previous].slice(0, MAX_NOTICES)
  // 只清理被挤出队列的通知计时器，保留仍在展示的通知各自的 12 秒生命周期
  previous.forEach((item) => {
    if (!notices.value.some((current) => current.id === item.id)) {
      clearDismissTimer(item.id)
    }
  })
  scheduleDismiss(notice.id)
  playChime()
}

function openNotice(notice: Notice) {
  selected.value = notice
  modalVisible.value = true
  removeNotice(notice.id)
}

onMounted(() => {
  dispose = onCronResultNotification(handleResult)
})

onBeforeUnmount(() => {
  dispose?.()
  dismissTimers.forEach((timer) => window.clearTimeout(timer))
  dismissTimers.clear()
})
</script>

<style scoped>
@import './styles/CronNotificationCenter.css';
</style>
