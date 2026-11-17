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

      <div class="form-group">
        <label class="label">{{ $t('settings.providers.models.streamMode') }}</label>
        <Select v-model="draft.streamMode" :options="streamModeOptions" />
        <p class="hint">{{ $t('settings.providers.models.streamModeHint') }}</p>
      </div>

      <div v-if="showNativeGuide" class="native-guide">
        <div class="native-guide-copy">
          <p class="native-guide-title">
            {{ $t('settings.providers.models.native.guideTitle') }}
          </p>
          <p class="native-guide-desc">
            {{ $t('settings.providers.models.native.guideDesc') }}
          </p>
        </div>
        <Button variant="ghost" size="sm" @click="nativePickerExpanded = true">
          {{ $t('settings.providers.models.native.guideAction') }}
        </Button>
      </div>

      <NativeCapabilityPicker
        v-model="draft.nativeCapabilities"
        v-model:expanded="nativePickerExpanded"
        :supported="nativeSupported"
        :custom-endpoint="customEndpoint"
      />

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

      <!-- 多用户共享：仅管理员可见可改；用户配置一律私有，共享动作只由管理员发起 -->
      <div v-if="canShare" class="form-group">
        <div class="share-head">
          <div class="share-title">
            <label class="label">{{ $t('settings.providers.models.share') }}</label>
            <SwitchToggle
              v-model="draft.shared"
              :aria-label="$t('settings.providers.models.share')"
            />
          </div>
          <p class="hint">{{ $t('settings.providers.models.shareHint') }}</p>
        </div>

        <template v-if="draft.shared">
          <label class="label">{{ $t('settings.providers.models.shareAlias') }}</label>
          <Input
            v-model="draft.sharedAlias"
            type="text"
            :placeholder="$t('settings.providers.models.shareAliasPlaceholder')"
          />
          <p class="hint">{{ $t('settings.providers.models.shareAliasHint') }}</p>

          <label class="label">{{ $t('settings.providers.models.shareNote') }}</label>
          <Input
            v-model="draft.sharedNote"
            type="text"
            :placeholder="$t('settings.providers.models.shareNotePlaceholder')"
          />

          <label class="label">{{ $t('settings.providers.models.shareDailyLimit') }}</label>
          <Input
            v-model="draft.userDailyLimit"
            type="number"
            :placeholder="$t('settings.providers.models.shareDailyLimitPlaceholder')"
          />
          <p class="hint">{{ $t('settings.providers.models.shareDailyLimitHint') }}</p>
        </template>
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
import SwitchToggle from '@/components/ui/SwitchToggle.vue'
import NativeCapabilityPicker from './NativeCapabilityPicker.vue'
import { settingsAPI, type ReasoningLevelsResponse } from '@/api'
import { CONTEXT_WINDOW_PRESET_VALUES, formatContextLength, isOfficialDeepSeekApiBase, supportsNativeCapabilities } from '@/utils/modelConfig'
import {
  DEFAULT_NATIVE_CAPABILITIES,
  normalizeNativeCapabilities,
} from '@/types/nativeCaps'
import type { ModelEditorDraft, ModelUpdatePayload, ProviderModel } from '../types'

interface Props {
  model: ProviderModel | null
  imageOptions: Array<{ value: string; label: string }>
  /** 当前供应商 ID，用于判断原生能力是否可用 */
  providerId?: string
  /** 当前供应商 API 地址，仅用于官方地址的能力引导 */
  apiBase?: string
  /** 是否展示共享区块；用户侧配置一律私有 */
  canShare?: boolean
  /** 档位建议的取数入口；缺省为管理员全局端点 */
  fetchReasoningLevels?: (model: string) => Promise<ReasoningLevelsResponse>
}

const props = withDefaults(defineProps<Props>(), {
  providerId: '',
  apiBase: '',
  canShare: true,
  fetchReasoningLevels: undefined,
})

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
  streamMode: 'inherit',
  reasoningLevels: [],
  reasoningLevel: '',
  shared: false,
  sharedAlias: '',
  sharedNote: '',
  userDailyLimit: '',
  nativeCapabilities: { ...DEFAULT_NATIVE_CAPABILITIES },
})

/** 是否生效由勾选决定。 */
const nativeSupported = computed(() =>
  supportsNativeCapabilities(props.providerId || props.model?.provider_id),
)

/** 自定义/中转地址按 DeepSeek 原生语义发送。 */
const customEndpoint = computed(
  () => Boolean(props.apiBase) && !isOfficialDeepSeekApiBase(props.apiBase),
)

const nativePickerExpanded = ref(false)

const nativeCapabilityCount = computed(() => {
  const caps = normalizeNativeCapabilities(draft.value.nativeCapabilities)
  return [
    caps.web_search,
    caps.read_url,
    caps.safety_check,
    caps.asr,
    caps.tts,
    caps.document_parsing !== 'off',
  ].filter(Boolean).length
})

/** 官方地址且未勾选时给出引导。 */
const showNativeGuide = computed(
  () =>
    nativeSupported.value
    && isOfficialDeepSeekApiBase(props.apiBase)
    && nativeCapabilityCount.value === 0,
)

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

/** 输出模式：默认跟随全局，个别模型或中转可单独强制 */
const streamModeOptions = computed(() => [
  { value: 'inherit', label: t('settings.providers.models.streamModeInherit') },
  { value: 'stream', label: t('settings.providers.models.streamModeStreaming') },
  { value: 'non-stream', label: t('settings.providers.models.streamModeNonStreaming') },
])

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
      streamMode:
        model?.stream_enabled === true
          ? 'stream'
          : model?.stream_enabled === false
            ? 'non-stream'
            : 'inherit',
      reasoningLevels: customLevels,
      reasoningLevel: (model?.reasoning_level || '').trim().toLowerCase(),
      shared: Boolean(model?.shared),
      sharedAlias: (model?.shared_alias || '').trim(),
      sharedNote: (model?.shared_note || '').trim(),
      userDailyLimit: model?.user_daily_limit ? String(model.user_daily_limit) : '',
      nativeCapabilities: normalizeNativeCapabilities(model?.native_capabilities),
    }
    levelsEdited.value = false
    levelInput.value = ''
    levelError.value = ''
    nativePickerExpanded.value = false
    builtinLevels.value = []
    knownLevels.value = []

    const modelId = model?.id
    if (!modelId) {
      return
    }
    try {
      const fetchLevels = props.fetchReasoningLevels
        ?? ((target: string) => settingsAPI.getReasoningLevels(target))
      const response = await fetchLevels(modelId)
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

  // 关闭共享时一并清空别名 / 说明 / 限额，避免残留无法清理的共享配置
  const sharedAlias = current.shared ? current.sharedAlias.trim() : ''
  const sharedNote = current.shared ? current.sharedNote.trim() : ''
  const limitRaw = current.shared ? current.userDailyLimit.trim() : ''
  const parsedLimit = limitRaw ? Number(limitRaw) : NaN
  const dailyLimit =
    Number.isFinite(parsedLimit) && parsedLimit > 0 ? Math.floor(parsedLimit) : null

  emit('save', {
    display_name: displayName || null,
    clear_display_name: !displayName,
    context_window: contextWindow ? Number(contextWindow) : null,
    clear_context_window: !contextWindow,
    supports_image:
      current.supportsImage === 'on' ? true : current.supportsImage === 'off' ? false : null,
    clear_supports_image: current.supportsImage === 'auto',
    stream_enabled:
      current.streamMode === 'stream' ? true : current.streamMode === 'non-stream' ? false : null,
    clear_stream_enabled: current.streamMode === 'inherit',
    reasoning_levels: levels,
    reasoning_level: reasoningLevel,
    clear_reasoning_level: clearReasoningLevel,
    shared: current.shared,
    shared_alias: sharedAlias || null,
    clear_shared_alias: !sharedAlias,
    shared_note: sharedNote || null,
    clear_shared_note: !sharedNote,
    user_daily_limit: dailyLimit,
    clear_user_daily_limit: dailyLimit === null,
    native_capabilities: normalizeNativeCapabilities(current.nativeCapabilities),
  })
}
</script>

<style scoped>
@import '../styles/ModelSettingsDialog.css';
</style>
