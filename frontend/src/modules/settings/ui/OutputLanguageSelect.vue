<template>
  <div ref="rootRef" class="output-language-select">
    <button
      ref="triggerRef"
      type="button"
      class="language-trigger"
      :class="{ 'is-open': isOpen }"
      :aria-expanded="isOpen"
      aria-haspopup="listbox"
      :aria-controls="listboxId"
      :aria-label="ariaLabel || $t('settings.general.outputLanguage')"
      @click="toggle"
      @keydown.down.prevent="open"
      @keydown.enter.prevent="toggle"
      @keydown.space.prevent="toggle"
      @keydown.esc.prevent="close()"
    >
      <span class="language-value">{{ selectedLabel }}</span>
      <ChevronDownIcon :size="16" class="language-chevron" />
    </button>

    <Transition name="language-dropdown">
      <div
        v-if="isOpen"
        :id="listboxId"
        class="language-popover"
        :class="{ 'is-up': dropUp }"
        role="listbox"
        :aria-label="ariaLabel || $t('settings.general.outputLanguage')"
        @keydown.esc.stop.prevent="close()"
      >
        <div
          v-for="group in groups"
          :key="group.key"
          class="language-group"
        >
          <div v-if="group.options.length > 1" class="language-group-label">{{ group.label }}</div>
          <button
            v-for="option in group.options"
            :key="option.value"
            type="button"
            class="language-option"
            :class="{ 'is-selected': option.value === modelValue }"
            role="option"
            :aria-selected="option.value === modelValue"
            @click="selectOption(option.value)"
          >
            <span>{{ option.label }}</span>
            <CheckIcon
              v-if="option.value === modelValue"
              :size="14"
              class="language-check"
            />
          </button>
        </div>

        <div class="language-custom">
          <button
            type="button"
            class="language-option"
            :class="{ 'is-selected': isCustom }"
            role="option"
            :aria-selected="isCustom"
            @click="selectCustom"
          >
            <span>{{ $t('settings.general.outputLanguageOptions.custom') }}</span>
            <CheckIcon
              v-if="isCustom"
              :size="14"
              class="language-check"
            />
          </button>
          <input
            v-if="isCustom"
            ref="customInputRef"
            v-model="customValue"
            type="text"
            class="language-custom-input"
            :placeholder="$t('settings.general.outputLanguageOptions.customPlaceholder')"
            maxlength="20"
            @input="emitCustom"
            @keydown.enter.prevent="close()"
            @keydown.esc.prevent="close()"
          >
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Check as CheckIcon, ChevronDown as ChevronDownIcon } from 'lucide-vue-next'
import { onClickOutside } from '@vueuse/core'

interface LanguageOption {
  value: string
  labelKey: string
}

interface Props {
  modelValue?: string
  ariaLabel?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '中文',
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

const { t, locale } = useI18n()
const rootRef = ref<HTMLElement>()
const triggerRef = ref<HTMLButtonElement>()
const customInputRef = ref<HTMLInputElement>()
const isOpen = ref(false)
const dropUp = ref(false)
const isCustom = ref(false)
const customValue = ref('')
const listboxId = `output-language-${Math.random().toString(36).slice(2, 9)}`

const isEnglishUi = computed(() => String(locale.value).toLowerCase().startsWith('en'))

// 选项值保持稳定，显示文案跟随界面语言，避免切换中英文后改写用户配置。
const chineseOptions: LanguageOption[] = [
  { value: '中文', labelKey: 'settings.general.outputLanguageOptions.zhHans' },
  { value: '中文繁体', labelKey: 'settings.general.outputLanguageOptions.zhHant' },
  { value: '粤语', labelKey: 'settings.general.outputLanguageOptions.cantonese' },
  { value: '东北', labelKey: 'settings.general.outputLanguageOptions.northeastern' },
  { value: '四川', labelKey: 'settings.general.outputLanguageOptions.sichuanese' },
  { value: '上海', labelKey: 'settings.general.outputLanguageOptions.shanghainese' },
  { value: '北京', labelKey: 'settings.general.outputLanguageOptions.beijing' },
]

const englishOptions: LanguageOption[] = [
  { value: 'English', labelKey: 'settings.general.outputLanguageOptions.english' },
]

const internationalOptions: LanguageOption[] = [
  { value: 'English', labelKey: 'settings.general.outputLanguageOptions.english' },
  { value: '中文', labelKey: 'settings.general.outputLanguageOptions.mandarin' },
  { value: 'Japanese', labelKey: 'settings.general.outputLanguageOptions.japanese' },
  { value: 'Korean', labelKey: 'settings.general.outputLanguageOptions.korean' },
  { value: 'French', labelKey: 'settings.general.outputLanguageOptions.french' },
  { value: 'German', labelKey: 'settings.general.outputLanguageOptions.german' },
  { value: 'Spanish', labelKey: 'settings.general.outputLanguageOptions.spanish' },
]

const toDisplayOptions = (options: LanguageOption[]) =>
  options.map(option => ({
    value: option.value,
    label: t(option.labelKey),
  }))

const chineseGroups = computed(() => [
  {
    key: 'zh',
    label: t('settings.general.outputLanguageGroups.zh'),
    options: toDisplayOptions(chineseOptions),
  },
  {
    key: 'en',
    label: t('settings.general.outputLanguageGroups.en'),
    options: toDisplayOptions(englishOptions),
  },
])

const englishGroups = computed(() => [
  {
    key: 'intl',
    label: t('settings.general.outputLanguageGroups.languages'),
    options: toDisplayOptions(internationalOptions),
  },
])

const groups = computed(() => (isEnglishUi.value ? englishGroups.value : chineseGroups.value))
const allOptions = computed(() => groups.value.flatMap(group => group.options))

// 英文界面隐藏中文方言；旧值只在显示层归一，不修改用户配置
const legacyChineseValues = new Set(['粤语', '东北', '四川', '上海', '北京', '中文繁体'])
const effectiveValue = computed(() =>
  isEnglishUi.value && legacyChineseValues.has(props.modelValue)
    ? '中文'
    : props.modelValue,
)

const selectedOption = computed(() =>
  allOptions.value.find(option => option.value === effectiveValue.value),
)

const selectedLabel = computed(() => {
  if (selectedOption.value) return selectedOption.value.label
  if (isCustom.value && customValue.value.trim()) return customValue.value.trim()
  if (isCustom.value) return t('settings.general.outputLanguageOptions.custom')
  return props.modelValue
})

watch(
  [() => props.modelValue, isEnglishUi],
  () => {
    const known = allOptions.value.some(option => option.value === effectiveValue.value)
    isCustom.value = !known
    if (!known) {
      customValue.value = props.modelValue || ''
      return
    }
    customValue.value = ''
  },
  { immediate: true },
)

function toggle() {
  if (isOpen.value) {
    close()
  } else {
    open()
  }
}

function open() {
  const rect = triggerRef.value?.getBoundingClientRect()
  // 视口下方空间不足时向上展开，避免最后几项被裁掉。
  dropUp.value = Boolean(rect && window.innerHeight - rect.bottom < 310 && rect.top > 310)
  isOpen.value = true
}

function close(restoreFocus = true) {
  isOpen.value = false
  if (restoreFocus) {
    void nextTick(() => triggerRef.value?.focus())
  }
}

function selectOption(value: string) {
  emit('update:modelValue', value)
  close()
}

async function selectCustom() {
  isCustom.value = true
  if (selectedOption.value) customValue.value = ''
  await nextTick()
  customInputRef.value?.focus()
}

function emitCustom(event: Event) {
  const value = (event.target as HTMLInputElement).value
  customValue.value = value
  // 空值不落库，避免把空语言拼接进提示词。
  if (value.trim()) emit('update:modelValue', value.trim())
}

onClickOutside(rootRef, () => {
  if (isOpen.value) close(false)
})
</script>

<style scoped>
.output-language-select {
  position: relative;
  width: 100%;
  max-width: 280px;
}

.language-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
  height: 32px;
  padding: 0 10px;
  border: 1px solid var(--color-border-secondary);
  border-radius: var(--radius-md);
  background: var(--co-panel);
  color: var(--color-text-primary);
  font-family: inherit;
  font-size: var(--font-size-sm);
  text-align: left;
  cursor: pointer;
  transition:
    border-color var(--transition-fast),
    background var(--transition-fast),
    box-shadow var(--transition-fast);
}

.language-trigger:hover {
  border-color: var(--color-border-strong);
  background: var(--color-bg-secondary);
}

.language-trigger:focus-visible,
.language-trigger.is-open {
  outline: none;
  border-color: var(--color-border-strong);
  box-shadow: 0 0 0 3px var(--color-primary-alpha);
}

.language-value {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.language-chevron {
  flex-shrink: 0;
  color: var(--color-text-tertiary);
  transition: transform var(--transition-fast);
}

.language-trigger.is-open .language-chevron {
  transform: rotate(180deg);
}

.language-popover {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  z-index: 60;
  width: 100%;
  min-width: 240px;
  max-height: 300px;
  padding: 6px;
  overflow-y: auto;
  border: 1px solid var(--color-border-secondary);
  border-radius: var(--radius-lg);
  background: var(--color-bg-elevated);
  box-shadow: var(--shadow-lg);
}

.language-group + .language-group,
.language-custom {
  margin-top: 4px;
  padding-top: 4px;
  border-top: 1px solid var(--color-border-primary);
}

.language-group-label {
  padding: 6px 10px 3px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
}

.language-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
  min-height: 32px;
  padding: 5px 10px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-secondary);
  font-family: inherit;
  font-size: var(--font-size-sm);
  text-align: left;
  cursor: pointer;
  transition:
    background var(--transition-fast),
    color var(--transition-fast);
}

.language-option:hover {
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
}

.language-option.is-selected {
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
  font-weight: var(--font-weight-medium);
}

.language-check {
  flex-shrink: 0;
  color: var(--color-accent);
}

.language-custom-input {
  width: 100%;
  height: 32px;
  margin-top: 4px;
  padding: 0 10px;
  border: 1px solid var(--color-border-secondary);
  border-radius: var(--radius-sm);
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
  font-family: inherit;
  font-size: var(--font-size-sm);
  outline: none;
}

.language-custom-input::placeholder {
  color: var(--color-text-tertiary);
}

.language-custom-input:focus {
  border-color: var(--color-border-strong);
  box-shadow: 0 0 0 3px var(--color-primary-alpha);
}

.language-dropdown-enter-active,
.language-dropdown-leave-active {
  transition:
    opacity var(--transition-fast),
    transform var(--transition-fast);
}

.language-popover.is-up {
  top: auto;
  bottom: calc(100% + 6px);
}

.language-dropdown-enter-from,
.language-dropdown-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

@media (max-width: 640px) {
  .output-language-select {
    max-width: none;
  }

  .language-popover {
    min-width: 0;
  }
}
</style>
