<template>
  <section
    class="reasoning"
    :class="{ 'is-open': isExpanded, 'is-thinking': isThinking, 'is-embedded': embedded }"
  >
    <!-- 一行触发器：大脑图标 + 状态词 + 流式末行摘要，收起态就是唯一的实时视图 -->
    <button
      type="button"
      class="reasoning-trigger"
      :aria-expanded="isExpanded"
      :title="isExpanded ? $t('chat.reasoning.collapse') : $t('chat.reasoning.expand')"
      @click="toggleExpand"
    >
      <BrainIcon class="reasoning-glyph" :size="14" :stroke-width="1.8" />

      <span class="reasoning-state" :class="{ 'is-live': isThinking }">{{ stateLabel }}</span>

      <template v-if="inlinePreview">
        <span class="reasoning-separator" aria-hidden="true">·</span>
        <span class="reasoning-preview">{{ inlinePreview }}</span>
      </template>

      <ChevronRightIcon
        class="reasoning-chevron"
        :class="{ 'is-open': isExpanded }"
        :size="13"
        aria-hidden="true"
      />
    </button>

    <transition name="reasoning-expand">
      <div v-if="isExpanded" class="reasoning-body">
        <!-- eslint-disable-next-line vue/no-v-html -->
        <div class="reasoning-text">{{ content }}</div>
        <button
          type="button"
          class="reasoning-copy"
          :title="copied ? $t('common.copied') : $t('common.copy')"
          @click.stop="copyContent"
        >
          <component :is="copied ? CheckIcon : CopyIcon" :size="12" />
        </button>
      </div>
    </transition>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Brain as BrainIcon,
  ChevronRight as ChevronRightIcon,
  Copy as CopyIcon,
  Check as CheckIcon,
} from 'lucide-vue-next'
import { useToast } from '@/composables/useToast'

interface Props {
  content: string
  isThinking?: boolean
  defaultExpanded?: boolean
  embedded?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isThinking: false,
  defaultExpanded: false,
  embedded: false,
})

const { t } = useI18n()
const toast = useToast()

// 默认收起：流式期间靠触发器上的末行摘要表达进度，展开交给用户，
// 避免思考内容持续挤压下方的工具与正文。
const isExpanded = ref(props.defaultExpanded)
const copied = ref(false)

// 本次思考的起始时间，由 isThinking 的上升沿记录；结束后换算成秒数。
const startedAt = ref<number | null>(props.isThinking ? Date.now() : null)
const durationSeconds = ref<number | null>(null)

const normalizedContent = computed(() => props.content.replace(/\r\n/g, '\n'))

/** 流式末行：最新一行才有信息量，取最后一条非空行 */
const lastLine = computed(() => {
  const lines = normalizedContent.value.split('\n')
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    const text = lines[index]?.trim()
    if (text) return text
  }
  return ''
})

const inlinePreview = computed(() => {
  if (props.isThinking) {
    return lastLine.value
  }
  return ''
})

const stateLabel = computed(() => {
  if (props.isThinking) {
    return t('chat.reasoning.thinkingNow')
  }
  if (durationSeconds.value !== null) {
    return t('chat.reasoning.thoughtFor', { seconds: durationSeconds.value })
  }
  return t('chat.reasoning.thought')
})

const toggleExpand = () => {
  isExpanded.value = !isExpanded.value
}

const copyContent = async () => {
  try {
    await navigator.clipboard.writeText(props.content)
    copied.value = true
    toast.success(t('common.copied'))

    window.setTimeout(() => {
      copied.value = false
    }, 1800)
  } catch (error) {
    console.error('Failed to copy reasoning content:', error)
    toast.error(t('common.copyFailed'))
  }
}

watch(
  () => props.isThinking,
  (isThinking, wasThinking) => {
    if (isThinking && !wasThinking) {
      startedAt.value = Date.now()
      durationSeconds.value = null
      return
    }

    if (!isThinking && wasThinking) {
      if (startedAt.value !== null) {
        durationSeconds.value = Math.max(1, Math.round((Date.now() - startedAt.value) / 1000))
      }
      startedAt.value = null
    }
  }
)

onBeforeUnmount(() => {
  startedAt.value = null
})
</script>
<style scoped>
@import './styles/ReasoningBlock.css';
</style>
