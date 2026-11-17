<template>
  <div class="provider-form">
    <div class="form-group">
      <label class="label">{{ $t('settings.providers.nameLabel') }}</label>
      <Input
        v-model="name"
        type="text"
        :placeholder="namePlaceholder"
      />
    </div>

    <div class="form-group form-group-wide">
      <label class="label">
        {{ $t('settings.providers.baseUrl') }}
        <span v-if="defaultBaseUrl" class="label-hint">({{ $t('common.optional') }})</span>
        <span v-else-if="isCustomProvider" class="label-hint required-hint">*</span>
      </label>
      <Input
        v-model="baseUrl"
        type="text"
        :placeholder="baseUrlPlaceholder"
      />
      <p class="hint">{{ $t('settings.providers.baseUrlHint') }}</p>
    </div>

    <div class="form-group form-group-wide">
      <label class="label">{{ $t('settings.providers.apiType.label') }}</label>
      <Select v-model="apiType" :options="apiTypeOptions" />
      <p class="hint">{{ $t('settings.providers.apiType.hint') }}</p>
    </div>

    <div class="form-group form-group-wide">
      <label class="label">{{ $t('settings.providers.apiKey') }}</label>
      <div class="api-key-list">
        <div v-for="(_, index) in apiKeys" :key="index" class="api-key-row">
          <Input
            v-model="apiKeys[index]"
            type="password"
            :placeholder="apiKeyPlaceholder"
          />
          <button
            v-if="apiKeys.length > 1"
            type="button"
            class="api-key-remove"
            :title="$t('common.remove')"
            :aria-label="$t('common.remove')"
            @click="removeApiKey(index)"
          >
            <XIcon :size="14" />
          </button>
        </div>
      </div>
      <div class="api-key-actions">
        <Button variant="outline" size="sm" :icon="PlusIcon" @click="addApiKey">
          {{ $t('common.add') }}
        </Button>
        <p class="hint api-key-hint">{{ $t('settings.providers.apiKeysHint') }}</p>
      </div>
    </div>
  </div>

  <p v-if="thinkingNote" class="hint provider-capability-note">{{ thinkingNote }}</p>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Plus as PlusIcon, X as XIcon } from 'lucide-vue-next'
import Input from '@/components/ui/Input.vue'
import Select from '@/components/ui/Select.vue'
import Button from '@/components/ui/Button.vue'
import type { ProviderApiType } from '@/api'

interface Props {
  /** API 协议选项（由父级注入 i18n 文案） */
  apiTypeOptions: Array<{ value: string; label: string }>
  /** 本地服务/自定义接口允许空密钥 */
  isApiKeyOptional: boolean
  /** 自定义接口必须手填 Base URL */
  isCustomProvider: boolean
  /** 该供应商的内置默认地址，存在时 Base URL 视为可选 */
  defaultBaseUrl?: string
  /** 供应商名称占位（未设置显示名时用元数据名称） */
  providerName?: string
  /** 思考控制说明 */
  thinkingNote: string
}

const props = withDefaults(defineProps<Props>(), {
  defaultBaseUrl: '',
  providerName: '',
})

const { t } = useI18n()

const name = defineModel<string>('name', { required: true })
const baseUrl = defineModel<string>('baseUrl', { required: true })
const apiType = defineModel<ProviderApiType>('apiType', { required: true })
const apiKeys = defineModel<string[]>('apiKeys', { required: true })

const namePlaceholder = computed(
  () => props.providerName || t('settings.providers.namePlaceholder'),
)

const baseUrlPlaceholder = computed(() => {
  if (props.isCustomProvider) {
    return t('settings.providers.baseUrlRequiredPlaceholder')
  }
  return props.defaultBaseUrl || t('settings.providers.baseUrlPlaceholder')
})

const apiKeyPlaceholder = computed(() =>
  props.isApiKeyOptional
    ? t('settings.providers.apiKeyOptionalPlaceholder')
    : t('settings.providers.apiKeyPlaceholder'),
)

function addApiKey(): void {
  apiKeys.value = [...apiKeys.value, '']
}

function removeApiKey(index: number): void {
  const next = [...apiKeys.value]
  next.splice(index, 1)
  apiKeys.value = next.length ? next : ['']
}
</script>

<style scoped>
@import '../styles/ProviderConnectionPanel.css';
</style>
