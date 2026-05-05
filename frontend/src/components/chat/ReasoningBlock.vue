<template>
  <section class="reasoning-block" :class="{ 'is-expanded': isExpanded, 'is-thinking': isThinking, 'is-embedded': embedded }">
    <div
      role="button"
      tabindex="0"
      class="reasoning-header"
      :aria-expanded="isExpanded"
      @click="toggleExpand"
      @keydown.enter.prevent="toggleExpand"
      @keydown.space.prevent="toggleExpand"
    >
      <div class="reasoning-leading" :class="{ 'is-embedded': embedded }">
        <div class="reasoning-emblem" aria-hidden="true">
          <div class="reasoning-orbit">
            <span class="reasoning-node reasoning-node-top" />
            <span class="reasoning-node reasoning-node-bottom" />
            <component
              :is="BrainCircuitIcon"
              class="reasoning-glyph"
              :class="{ 'is-thinking': isThinking }"
              :size="18"
              :stroke-width="1.9"
            />
            <span class="reasoning-signal" :class="{ 'is-thinking': isThinking }" />
          </div>
        </div>

        <div class="reasoning-main">
          <div class="reasoning-row">
            <span class="reasoning-kicker">{{ $t('chat.reasoning.title') }}</span>
            <span class="reasoning-divider" />
            <span class="reasoning-caption">{{ bodyMeta }}</span>
          </div>

          <div class="reasoning-summary">
            <span class="reasoning-preview-inline">{{ summaryText }}</span>
          </div>
        </div>
      </div>

      <div class="reasoning-meta" :class="{ 'is-embedded': embedded }">
        <span v-if="isThinking" class="reasoning-state-pill">
          <span class="reasoning-state-dot" />
          {{ $t('chat.workflowPanel.thinking') }}
        </span>

        <span class="reasoning-meta-pill">{{ lineCountDisplay }}</span>
        <span class="reasoning-meta-pill">{{ contentMeta }}</span>

        <span class="reasoning-toggle" :class="{ 'is-rotated': isExpanded }" aria-hidden="true">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </span>
      </div>
    </div>

    <transition name="reasoning-expand">
      <div v-if="isExpanded" class="reasoning-content">
        <div class="reasoning-body">
          <div class="reasoning-body-header">
            <div class="reasoning-body-copy">
              <span class="reasoning-body-label">
                {{ embedded ? $t('chat.reasoning.aiTitle') : $t('chat.reasoning.title') }}
              </span>
              <span class="reasoning-body-detail">{{ bodyMeta }}</span>
            </div>

            <div v-if="!embedded" class="reasoning-toolbar" role="toolbar" :aria-label="$t('chat.reasoning.title')">
              <div
                role="button"
                tabindex="0"
                class="reasoning-icon-button reasoning-icon-button-copy"
                :class="{ 'is-success': copied }"
                @click.stop="copyContent"
                @keydown.enter.prevent.stop="copyContent"
                @keydown.space.prevent.stop="copyContent"
                :title="copied ? $t('common.copied') : $t('common.copy')"
                :aria-label="copied ? $t('common.copied') : $t('common.copy')"
              >
                <component
                  :is="copied ? CheckIcon : CopyIcon"
                  class="action-icon"
                  :size="14"
                  :stroke-width="1.9"
                  aria-hidden="true"
                />
              </div>

              <div
                role="button"
                tabindex="0"
                class="reasoning-icon-button reasoning-icon-button-collapse"
                @click.stop="toggleExpand"
                @keydown.enter.prevent.stop="toggleExpand"
                @keydown.space.prevent.stop="toggleExpand"
                :title="$t('common.collapse')"
                :aria-label="$t('common.collapse')"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true">
                  <polyline points="18 15 12 9 6 15" />
                </svg>
              </div>
            </div>
          </div>

          <pre class="reasoning-text">{{ content }}</pre>
        </div>
      </div>
    </transition>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { BrainCircuit as BrainCircuitIcon, Copy as CopyIcon, Check as CheckIcon } from 'lucide-vue-next'
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

const isExpanded = ref(props.isThinking || props.defaultExpanded)
const copied = ref(false)

const normalizedContent = computed(() => props.content.replace(/\r\n/g, '\n'))

const contentLength = computed(() => props.content.length)

const lineCount = computed(() => {
  const trimmed = normalizedContent.value.trim()
  if (!trimmed) {
    return 0
  }

  return trimmed.split('\n').length
})

const lineCountDisplay = computed(() => `${lineCount.value}L`)

const contentMeta = computed(() => `${contentLength.value} ${t('chat.reasoning.chars')}`)

const bodyMeta = computed(() => `${lineCountDisplay.value} · ${contentMeta.value}`)

const embedded = computed(() => props.embedded)

const previewText = computed(() => {
  const normalized = props.content.replace(/\s+/g, ' ').trim()
  if (!normalized) {
    return ''
  }

  const maxLength = 140
  if (normalized.length <= maxLength) {
    return normalized
  }

  return `${normalized.slice(0, maxLength)}...`
})

const summaryText = computed(() => {
  if (previewText.value) {
    return previewText.value
  }

  return props.isThinking ? t('chat.workflowPanel.thinking') : t('chat.reasoning.title')
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
      isExpanded.value = true
      return
    }

    if (!isThinking && wasThinking) {
      isExpanded.value = false
    }
  }
)
</script>
<style scoped>
@import './styles/ReasoningBlock.css';
</style>
