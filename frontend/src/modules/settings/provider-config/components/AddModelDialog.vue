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
          :placeholder="$t('settings.providers.models.contextWindowPlaceholder')"
        />
        <p class="hint">{{ $t('settings.providers.models.contextWindowRequiredHint') }}</p>
      </div>
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
import Modal from '@/components/ui/Modal.vue'
import Input from '@/components/ui/Input.vue'
import Button from '@/components/ui/Button.vue'
import ComboBox from '@/components/ui/ComboBox.vue'
import { CONTEXT_WINDOW_PRESET_VALUES, formatContextLength } from '@/utils/modelConfig'

interface Props {
  show: boolean
  submitting?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  submitting: false,
})

const emit = defineEmits<{
  (e: 'update:show', value: boolean): void
  (e: 'confirm', modelId: string, contextWindow: number | null): void
}>()

const modelId = ref('')
const contextWindow = ref('')
const inputRef = ref<{ focus?: () => void } | null>(null)

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
    nextTick(() => inputRef.value?.focus?.())
  },
)

function submit(): void {
  const value = modelId.value.trim()
  const windowSize = Number(contextWindow.value)
  if (!value || !(windowSize > 0) || props.submitting) {
    return
  }
  emit('confirm', value, windowSize)
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
</style>
