<template>
  <Modal
    :model-value="show"
    :title="$t('settings.providers.models.add')"
    size="small"
    @update:model-value="(value) => emit('update:show', value)"
  >
    <div class="add-model">
      <div class="form-group">
        <label class="label">{{ $t('settings.providers.models.modelIdLabel') }}</label>
        <Input
          ref="inputRef"
          v-model="modelId"
          type="text"
          :placeholder="$t('settings.providers.models.addPlaceholder')"
          @keydown.enter.prevent="submit"
        />
        <p class="hint">{{ $t('settings.providers.models.addHint') }}</p>
      </div>

      <!-- 窗口大小决定压缩阈值：未填写会落到兜底值，导致压缩时机与模型实际能力不符 -->
      <div class="form-group">
        <label class="label">{{ $t('settings.providers.models.contextWindow') }}</label>
        <ComboBox
          v-model="contextWindow"
          :options="contextWindowOptions"
          :placeholder="t('settings.providers.models.contextWindowPlaceholder')"
        />
        <p class="hint">{{ $t('settings.providers.models.contextWindowRequiredHint') }}</p>
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
        v-model="nativeCapabilities"
        v-model:expanded="nativePickerExpanded"
        :supported="nativeSupported"
        :custom-endpoint="customEndpoint"
      />
    </div>

    <template #footer>
      <Button variant="ghost" @click="emit('update:show', false)">
        {{ $t('common.cancel') }}
      </Button>
      <Button
        variant="primary"
        :disabled="!canSubmit"
        :loading="submitting"
        @click="submit"
      >
        {{ $t('common.add') }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Modal from '@/components/ui/Modal.vue'
import Input from '@/components/ui/Input.vue'
import Button from '@/components/ui/Button.vue'
import ComboBox from '@/components/ui/ComboBox.vue'
import NativeCapabilityPicker from './NativeCapabilityPicker.vue'
import { CONTEXT_WINDOW_PRESET_VALUES, formatContextLength, isOfficialDeepSeekApiBase, supportsNativeCapabilities } from '@/utils/modelConfig'
import {
  DEFAULT_NATIVE_CAPABILITIES,
  DEEPSEEK_DEFAULT_NATIVE_CAPABILITIES,
  normalizeNativeCapabilities,
  type NativeCapabilities,
} from '@/types/nativeCaps'

interface Props {
  show: boolean
  submitting?: boolean
  /** 当前供应商 ID，用于判断是否支持原生能力 */
  providerId?: string
  /** 当前供应商 API 地址，仅用于官方地址的能力引导 */
  apiBase?: string
}

const props = withDefaults(defineProps<Props>(), {
  submitting: false,
  providerId: '',
  apiBase: '',
})

const emit = defineEmits<{
  (e: 'update:show', value: boolean): void
  (e: 'confirm', modelId: string, contextWindow: number | null, capabilities: NativeCapabilities): void
}>()

const { t } = useI18n()

const modelId = ref('')
const contextWindow = ref('')
/** DeepSeek 官方模型默认开启全部原生能力，其他供应商保持关闭。 */
const defaultNativeCapabilities = computed(() =>
  props.providerId === 'deepseek'
    ? DEEPSEEK_DEFAULT_NATIVE_CAPABILITIES
    : DEFAULT_NATIVE_CAPABILITIES,
)
const nativeCapabilities = ref<NativeCapabilities>({ ...defaultNativeCapabilities.value })
const nativePickerExpanded = ref(false)
const inputRef = ref<{ focus?: () => void } | null>(null)

/** 是否生效由勾选决定。 */
const nativeSupported = computed(() => supportsNativeCapabilities(props.providerId))

/** 自定义/中转地址按 DeepSeek 原生语义发送。 */
const customEndpoint = computed(
  () => Boolean(props.apiBase) && !isOfficialDeepSeekApiBase(props.apiBase),
)

const nativeCapabilityCount = computed(() => {
  const caps = normalizeNativeCapabilities(nativeCapabilities.value)
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

/** 常见上下文档位：可直接选，也能手填任意数值 */
const contextWindowOptions = computed(() =>
  CONTEXT_WINDOW_PRESET_VALUES.map(value => ({
    value: String(value),
    label: `${formatContextLength(value)} · ${value.toLocaleString()}`,
  })),
)

/** 模型 ID 与窗口都必须有值：窗口缺省会让压缩阈值落到兜底值 */
const canSubmit = computed(
  () => Boolean(modelId.value.trim()) && Number(contextWindow.value) > 0,
)

/** 每次打开都清空上次输入并聚焦，避免误提交 */
watch(
  () => props.show,
  show => {
    if (!show) {
      return
    }
    modelId.value = ''
    contextWindow.value = ''
    nativeCapabilities.value = { ...defaultNativeCapabilities.value }
    nativePickerExpanded.value = false
    nextTick(() => inputRef.value?.focus?.())
  },
)

function submit(): void {
  const value = modelId.value.trim()
  const windowSize = Number(contextWindow.value)
  if (!value || !(windowSize > 0) || props.submitting) {
    return
  }
  emit(
    'confirm',
    value,
    windowSize,
    normalizeNativeCapabilities(
      nativeSupported.value ? nativeCapabilities.value : DEFAULT_NATIVE_CAPABILITIES,
    ),
  )
}
</script>

<style scoped>
.add-model {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}

.hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.55;
  color: var(--text-secondary);
}

.native-guide {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid rgba(59, 130, 246, 0.28);
  border-radius: 10px;
  background: rgba(59, 130, 246, 0.08);
}

.native-guide-copy {
  flex: 1;
  min-width: 0;
}

.native-guide-title {
  margin: 0;
  font-size: 12.5px;
  font-weight: 700;
  color: var(--text-primary);
}

.native-guide-desc {
  margin: 3px 0 0;
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--text-secondary);
}
</style>
