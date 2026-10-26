<template>
  <Modal
    :model-value="Boolean(model)"
    :title="$t('settings.providers.models.configure')"
    size="small"
    @update:model-value="(value) => { if (!value) emit('close') }"
  >
    <div v-if="model" class="model-editor">
      <div class="form-group">
        <label class="label">{{ $t('settings.providers.models.displayName') }}</label>
        <Input
          v-model="draft.displayName"
          type="text"
          :placeholder="$t('settings.providers.models.displayNamePlaceholder')"
        />
      </div>

      <div class="form-group">
        <label class="label">{{ $t('settings.providers.models.contextWindow') }}</label>
        <ComboBox
          v-model="draft.contextWindow"
          :options="contextWindowOptions"
          :placeholder="$t('settings.providers.models.contextWindowPlaceholder')"
        />
        <p class="hint">{{ $t('settings.providers.models.contextWindowHint') }}</p>
      </div>

      <div class="form-group">
        <label class="label">{{ $t('settings.providers.models.supportsImage') }}</label>
        <Select v-model="draft.supportsImage" :options="imageOptions" />
      </div>

      <!-- 思考档位：用户可自由增删，未收录内置表的自定义模型同样可填 -->
      <div class="form-group">
        <div class="reasoning-head">
          <label class="label">{{ $t('settings.providers.models.reasoningLevels') }}</label>
          <button type="button" class="reasoning-restore" @click="restoreBuiltinLevels">
            {{ $t('settings.providers.models.reasoningLevelsRestore') }}
          </button>
        </div>

        <p v-if="draft.reasoningLevels.length === 0" class="reasoning-empty">
          {{ $t('settings.providers.models.reasoningLevelsEmpty') }}
        </p>
        <div v-else class="reasoning-chips">
          <button
            v-for="level in draft.reasoningLevels"
            :key="level"
            type="button"
            class="reasoning-chip is-checked"
            :class="{ 'is-default': level === effectiveDefaultLevel }"
            :title="$t('settings.providers.models.reasoningLevelsRemove')"
            @click="removeLevel(level)"
          >
            <span>{{ level }}</span>
            <component :is="XIcon" :size="11" class="reasoning-chip-mark" />
          </button>
        </div>

        <div v-if="addableLevels.length > 0" class="reasoning-chips">
          <button
            v-for="level in addableLevels"
            :key="level"
            type="button"
            class="reasoning-chip"
            @click="addLevel(level)"
          >
            <component :is="PlusIcon" :size="11" class="reasoning-chip-mark" />
            <span>{{ level }}</span>
          </button>
        </div>

        <div class="reasoning-add">
          <input
            v-model="levelInput"
            class="reasoning-add-input"
            type="text"
            list="reasoning-level-suggestions"
            :placeholder="$t('settings.providers.models.reasoningLevelsAddPlaceholder')"
            @keydown.enter.prevent="addCustomLevel"
          />
          <datalist id="reasoning-level-suggestions">
            <option v-for="level in suggestionLevels" :key="level" :value="level" />
          </datalist>
          <Button variant="ghost" size="sm" @click="addCustomLevel">
            {{ $t('settings.providers.models.reasoningLevelsAdd') }}
          </Button>
        </div>
        <p v-if="levelError" class="reasoning-error">{{ levelError }}</p>

        <p class="hint">{{ $t('settings.providers.models.reasoningLevelsHint') }}</p>

        <label class="label">{{ $t('settings.providers.models.reasoningLevelDefault') }}</label>
        <Select
          v-model="draft.reasoningLevel"
          :options="levelOptions"
          :placeholder="$t('settings.providers.models.reasoningLevelDefaultPlaceholder')"
        />
        <p class="hint">{{ $t('settings.providers.models.reasoningLevelDefaultHint') }}</p>
      </div>
    </div>

    <template #footer>
      <Button variant="ghost" @click="emit('close')">{{ $t('common.cancel') }}</Button>
      <Button variant="primary" @click="submit">{{ $t('common.save') }}</Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Plus as PlusIcon, X as XIcon } from 'lucide-vue-next'
import Modal from '@/components/ui/Modal.vue'
import Input from '@/components/ui/Input.vue'
import Select from '@/components/ui/Select.vue'
import ComboBox from '@/components/ui/ComboBox.vue'
import Button from '@/components/ui/Button.vue'
import { settingsAPI } from '@/api'
import { CONTEXT_WINDOW_PRESET_VALUES, formatContextLength } from '@/utils/modelConfig'
import type { ModelEditorDraft, ModelUpdatePayload, ProviderModel } from '../types'

interface Props {
  model: ProviderModel | null
  imageOptions: Array<{ value: string; label: string }>
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'save', payload: ModelUpdatePayload): void
}>()

const { t } = useI18n()

/** 与后端一致的档位语法约束：短、无空白、无特殊符号，但允许内置表之外的值 */
const LEVEL_PATTERN = /^[a-z0-9][a-z0-9._-]{0,23}$/

const draft = ref<ModelEditorDraft>({
  displayName: '',
  contextWindow: '',
  supportsImage: 'auto',
  reasoningLevels: [],
  reasoningLevel: '',
})

/** 内置建议档位与常用档位全集（仅作参考，不构成限制） */
const builtinLevels = ref<string[]>([])
const knownLevels = ref<string[]>([])
/** 用户是否动过档位列表：动过才提交当前勾选，否则维持原样（避免误把空数组写成「改用内置」） */
const levelsEdited = ref(false)
const levelInput = ref('')
const levelError = ref('')

/** 常见上下文档位：可直接选，也能手填任意数值 */
const contextWindowOptions = computed(() =>
  CONTEXT_WINDOW_PRESET_VALUES.map(value => ({
    value: String(value),
    label: `${formatContextLength(value)} · ${value.toLocaleString()}`,
  })),
)

const levelOptions = computed(() =>
  draft.value.reasoningLevels.map(level => ({ value: level, label: level })),
)

/** 内置建议里还没被勾选的，作为「点一下即添加」的候选 */
const addableLevels = computed(() =>
  builtinLevels.value.filter(level => !draft.value.reasoningLevels.includes(level)),
)

/** 自定义输入的候选：内置建议 + 常用档位全集 */
const suggestionLevels = computed(() =>
  Array.from(new Set([...builtinLevels.value, ...knownLevels.value])),
)

/** 当前实际生效的默认档位：用户选的还在列表里就用它，否则退回首项 */
const effectiveDefaultLevel = computed(() => {
  const picked = draft.value.reasoningLevel
  if (picked && draft.value.reasoningLevels.includes(picked)) {
    return picked
  }
  return draft.value.reasoningLevels[0] || ''
})

/** 每次打开都按当前模型重置草稿，避免残留上一次的输入 */
watch(
  () => props.model,
  async model => {
    const customLevels = [...(model?.reasoning_levels || [])]
    draft.value = {
      displayName: model?.display_name || '',
      contextWindow: model?.context_window ? String(model.context_window) : '',
      supportsImage:
        model?.supports_image === true ? 'on' : model?.supports_image === false ? 'off' : 'auto',
      reasoningLevels: customLevels,
      reasoningLevel: (model?.reasoning_level || '').trim().toLowerCase(),
    }
    levelsEdited.value = false
    levelInput.value = ''
    levelError.value = ''
    builtinLevels.value = []
    knownLevels.value = []

    const modelId = model?.id
    if (!modelId) {
      return
    }
    try {
      const response = await settingsAPI.getReasoningLevels(modelId)
      // 请求返回时模型可能已切换，丢弃过期结果
      if (props.model?.id !== modelId) {
        return
      }
      builtinLevels.value = response.levels || []
      knownLevels.value = response.known_levels || []
      // 模型条目没有自定义档位时，按内置建议展示与勾选
      if (customLevels.length === 0) {
        draft.value.reasoningLevels = [...builtinLevels.value]
        draft.value.reasoningLevel = builtinLevels.value[0] || ''
      }
    } catch {
      // 取不到内置建议就按模型自身档位展示，不阻断编辑
    }
  },
  { immediate: true },
)

/** 勾选列表变化后，默认档位若已不在列表里就退回首项 */
watch(
  () => draft.value.reasoningLevels,
  levels => {
    if (draft.value.reasoningLevel && levels.includes(draft.value.reasoningLevel)) {
      return
    }
    draft.value.reasoningLevel = levels[0] || ''
  },
)

function addLevel(level: string): void {
  const normalized = level.trim().toLowerCase()
  if (!normalized || draft.value.reasoningLevels.includes(normalized)) {
    return
  }
  draft.value.reasoningLevels = [...draft.value.reasoningLevels, normalized]
  if (!draft.value.reasoningLevel) {
    draft.value.reasoningLevel = normalized
  }
  levelsEdited.value = true
}

function removeLevel(level: string): void {
  draft.value.reasoningLevels = draft.value.reasoningLevels.filter(item => item !== level)
  levelsEdited.value = true
}

function addCustomLevel(): void {
  const normalized = levelInput.value.trim().toLowerCase()
  if (!normalized) {
    return
  }
  if (!LEVEL_PATTERN.test(normalized)) {
    levelError.value = t('settings.providers.models.reasoningLevelsInvalid')
    return
  }
  levelError.value = ''
  addLevel(normalized)
  levelInput.value = ''
}

function restoreBuiltinLevels(): void {
  draft.value.reasoningLevels = [...builtinLevels.value]
  draft.value.reasoningLevel = builtinLevels.value[0] || ''
  levelError.value = ''
  levelsEdited.value = true
}

function submit(): void {
  const current = draft.value
  const displayName = current.displayName.trim()
  const contextWindow = current.contextWindow.trim()
  const model = props.model
  const originalLevels = [...(model?.reasoning_levels || [])]
  const originalDefault = (model?.reasoning_level || '').trim().toLowerCase()

  // 未动过档位就原样提交，避免把「跟随内置建议」误写成用户自定义
  const levels = levelsEdited.value ? [...current.reasoningLevels] : originalLevels
  const defaultTouched = levelsEdited.value || current.reasoningLevel !== originalDefault

  let reasoningLevel: string | null
  let clearReasoningLevel: boolean
  if (defaultTouched) {
    reasoningLevel = effectiveDefaultLevel.value || null
    clearReasoningLevel = !reasoningLevel
  } else {
    reasoningLevel = originalDefault || null
    clearReasoningLevel = false
  }

  emit('save', {
    display_name: displayName || null,
    clear_display_name: !displayName,
    context_window: contextWindow ? Number(contextWindow) : null,
    clear_context_window: !contextWindow,
    supports_image:
      current.supportsImage === 'on' ? true : current.supportsImage === 'off' ? false : null,
    clear_supports_image: current.supportsImage === 'auto',
    reasoning_levels: levels,
    reasoning_level: reasoningLevel,
    clear_reasoning_level: clearReasoningLevel,
  })
}
</script>

<style scoped>
@import '../styles/ModelSettingsDialog.css';
</style>
