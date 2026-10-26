<template>
  <div class="provider-config">
    <div class="section-header">
      <h3 class="section-title">{{ $t('settings.providers.title') }}</h3>

      <div class="section-actions">
        <Button
          variant="outline"
          size="sm"
          :icon="LayoutGridIcon"
          @click="showPresetPanel = true"
        >
          {{ $t('settings.providers.presetPanel.open') }}
        </Button>
      </div>
    </div>

    <!-- 已保存 / 当前草稿对照 -->
    <section class="state-grid">
      <div class="state-card">
        <div class="state-head">
          <span class="state-label">{{ $t('settings.providers.presetPanel.savedSnapshot') }}</span>
        </div>
        <div class="state-stack">
          <span class="state-provider">{{ savedSnapshot.provider }}</span>
          <strong class="state-model">{{ savedSnapshot.model }}</strong>
        </div>
      </div>

      <div class="state-card" :class="{ 'is-dirty': hasDraftChanges }">
        <div class="state-head">
          <span class="state-label">{{ $t('settings.providers.presetPanel.currentDraft') }}</span>
          <span v-if="draftStateHint" class="state-flag">{{ draftStateHint }}</span>
        </div>
        <div class="state-stack">
          <span class="state-provider">{{ draftSnapshot.provider }}</span>
          <strong class="state-model">{{ draftSnapshot.model }}</strong>
        </div>
      </div>
    </section>

    <div class="provider-workspace">
      <ProviderNavList
        :items="navigationProviders"
        :selected-id="selectedProvider"
        :title="$t('settings.providers.selectProvider')"
        :add-label="$t('settings.providers.addProvider')"
        :remove-label="$t('settings.providers.removeProvider')"
        :current-label="$t('settings.providers.currentModel')"
        :show-all="showAllProviders"
        :hidden-count="hiddenProviderCount"
        :expand-label="$t('settings.providers.filter.showAll', { count: hiddenProviderCount })"
        :collapse-label="$t('settings.providers.filter.showConfiguredOnly')"
        @select="selectProvider"
        @add="showAddProvider = true"
        @remove="handleRemoveProvider"
        @toggle-show-all="showAllProviders = !showAllProviders"
      />

      <section v-if="selectedProvider" class="provider-detail">
        <header class="provider-detail-header">
          <div class="provider-detail-title">
            <ProviderIcon
              class="provider-detail-icon"
              :provider-id="selectedProvider"
              :size="22"
            />
            <h4>{{ selectedProviderMeta?.name || selectedProvider }}</h4>
            <span class="status-pill" :class="selectedProviderSelectable ? 'ready' : 'warning'">
              {{ selectedProviderStatusText }}
            </span>
            <span v-if="appliedSourceText" class="status-pill neutral">
              {{ appliedSourceText }}
            </span>
          </div>

          <label class="provider-enabled">
            <SwitchToggle
              v-model="providerConfig.enabled"
              :width="44"
              :height="26"
              :aria-label="$t('settings.providers.enabled')"
            />
            <span>{{ $t('settings.providers.enabled') }}</span>
          </label>
        </header>

        <ProviderConnectionPanel
          v-model:name="providerConfig.name"
          v-model:base-url="providerConfig.baseUrl"
          v-model:api-type="providerConfig.apiType"
          v-model:api-keys="providerConfig.apiKeys"
          :api-type-options="apiTypeOptions"
          :is-api-key-optional="isApiKeyOptional"
          :is-custom-provider="isCustomProvider"
          :default-base-url="currentDefaultBaseUrl"
          :provider-name="selectedProviderMeta?.name || ''"
          :thinking-note="selectedProviderThinkingNote"
        />

        <ProviderModelList
          :key="selectedProvider"
          :models="providerModels"
          :testing-model-id="testingModelId"
          :provider-testing="providerTesting"
          :catalog-loading="catalogLoading"
          :source-label="sourceLabel"
          :context-label="contextLabel"
          @request-add="showAddModelDialog = true"
          @fetch-models="openFetchDialog"
          @test-provider="testProvider"
          @test-model="testModel"
          @edit-model="openModelEditor"
          @delete-model="deleteModel"
          @toggle-model="toggleModel"
          @move-model="moveModel"
        />

        <div class="action-row">
          <Button
            variant="secondary"
            :loading="testing"
            :disabled="!canTestConnection"
            @click="testConnection"
          >
            {{ testing ? $t('settings.providers.testing') : $t('settings.providers.testConnection') }}
          </Button>
        </div>

        <div
          v-if="testResult"
          class="test-result"
          :class="testResult.success ? 'success' : 'error'"
        >
          <component :is="testResult.success ? CheckCircleIcon : XCircleIcon" :size="16" />
          <span>{{ testResult.message }}</span>
        </div>
      </section>

      <section v-else class="provider-detail is-empty">
        <p>{{ $t('settings.providers.noProvider') }}</p>
      </section>
    </div>

    <FetchModelsDialog
      v-model:show="showFetchDialog"
      :loading="catalogLoading"
      :error="catalogError"
      :models="fetchedModels"
      :existing-model-ids="existingModelIds"
      @confirm="commitFetchedModels"
      @retry="openFetchDialog"
    />

    <ModelSettingsDialog
      :model="editingModel"
      :image-options="imageCapabilityOptions"
      @close="closeModelEditor"
      @save="saveModelEditor"
    />

    <AddModelDialog
      v-model:show="showAddModelDialog"
      :submitting="addingModel"
      @confirm="handleAddModel"
    />

    <AddProviderDialog
      v-model:show="showAddProvider"
      :providers="addableProviders"
      @select="handleAddProvider"
    />

    <ProviderPresetPanel
      v-model="showPresetPanel"
      :current-config="currentDraftConfig"
      :available-providers="availableProviders"
      @apply-config="applyExternalConfig"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  CheckCircle as CheckCircleIcon,
  LayoutGrid as LayoutGridIcon,
  XCircle as XCircleIcon,
} from 'lucide-vue-next'
import Button from '@/components/ui/Button.vue'
import SwitchToggle from '@/components/ui/SwitchToggle.vue'
import ProviderPresetPanel from './ProviderPresetPanel.vue'
import FetchModelsDialog from './FetchModelsDialog.vue'
import ProviderNavList from './provider-config/components/ProviderNavList.vue'
import ProviderConnectionPanel from './provider-config/components/ProviderConnectionPanel.vue'
import ProviderModelList from './provider-config/components/ProviderModelList.vue'
import ModelSettingsDialog from './provider-config/components/ModelSettingsDialog.vue'
import AddProviderDialog from './provider-config/components/AddProviderDialog.vue'
import AddModelDialog from './provider-config/components/AddModelDialog.vue'
import { useProviderCatalog } from './provider-config/useProviderCatalog'
import { useProviderDraft } from './provider-config/useProviderDraft'
import { useProviderModels } from './provider-config/useProviderModels'
import ProviderIcon from '@/components/ui/ProviderIcon.vue'
import { useToast } from '@/composables/useToast'
import { useSettingsStore } from '@/store/settings'

const { t } = useI18n()
const toast = useToast()
const settingsStore = useSettingsStore()

const showPresetPanel = ref(false)
const showAddProvider = ref(false)
const showAddModelDialog = ref(false)
const addingModel = ref(false)

/* ------------------------------------------------------------------ */
/* 三个职责模块：清单导航 / 连接草稿 / 模型清单                          */
/* ------------------------------------------------------------------ */

const catalog = useProviderCatalog()

const draft = useProviderDraft({
  selectedProvider: catalog.selectedProvider,
  selectedProviderMeta: catalog.selectedProviderMeta,
  availableProviders: catalog.availableProviders,
})

const models = useProviderModels({
  selectedProvider: catalog.selectedProvider,
  saveProviderConnection: draft.saveProviderConnection,
  syncProviderDraftToStore: draft.syncProviderDraftToStore,
  getPrimaryApiKey: draft.getPrimaryApiKey,
  apiBase: computed(() => draft.providerConfig.value.baseUrl),
  apiType: computed(() => draft.providerConfig.value.apiType),
})

const {
  availableProviders,
  selectedProvider,
  showAllProviders,
  selectedProviderMeta,
  navigationProviders,
  hiddenProviderCount,
  addableProviders,
  loadProviders,
  selectProvider,
  markProviderAdded,
  unmarkProviderAdded,
} = catalog

const {
  providerConfig,
  modelName,
  testing,
  testResult,
  isHydrating,
  isApplyingExternalConfig,
  isApiKeyOptional,
  isCustomProvider,
  currentDefaultBaseUrl,
  selectedProviderSelectable,
  selectedProviderStatusText,
  selectedProviderThinkingNote,
  currentDraftConfig,
  savedSnapshot,
  draftSnapshot,
  appliedSourceText,
  draftStateHint,
  hasDraftChanges,
  canTestConnection,
  hydrateDraft,
  initializeProvider,
  syncProviderDraftToStore,
  syncModelDraftToStore,
  testConnection,
  applyExternalConfig,
  createProvider,
  deleteProvider,
} = draft

const {
  models: providerModels,
  existingModelIds,
  editingModel,
  testingModelId,
  providerTesting,
  catalogLoading,
  catalogError,
  fetchedModels,
  showFetchDialog,
  sourceLabel,
  contextLabel,
  commitNewModel,
  commitFetchedModels,
  openFetchDialog,
  deleteModel,
  toggleModel,
  moveModel,
  openModelEditor,
  closeModelEditor,
  saveModelEditor,
  testModel,
  testProvider,
} = models

/* ------------------------------------------------------------------ */
/* 下拉选项                                                            */
/* ------------------------------------------------------------------ */

const apiTypeOptions = computed(() => [
  {
    value: 'openai-chat-completions',
    label: t('settings.providers.apiType.options.openai-chat-completions'),
  },
  {
    value: 'openai-responses',
    label: t('settings.providers.apiType.options.openai-responses'),
  },
  {
    value: 'anthropic-messages',
    label: t('settings.providers.apiType.options.anthropic-messages'),
  },
])

const imageCapabilityOptions = computed(() => [
  { value: 'auto', label: t('settings.providers.models.supportsImageAuto') },
  { value: 'on', label: t('settings.providers.models.supportsImageOn') },
  { value: 'off', label: t('settings.providers.models.supportsImageOff') },
])

/* ------------------------------------------------------------------ */
/* 动作                                                                */
/* ------------------------------------------------------------------ */

/** 添加模型：成功后关窗，失败留给弹窗让用户改 ID 重试 */
async function handleAddModel(modelId: string, contextWindow: number | null): Promise<void> {
  if (addingModel.value) {
    return
  }
  addingModel.value = true
  try {
    const saved = await commitNewModel(modelId, contextWindow)
    if (saved) {
      showAddModelDialog.value = false
    }
  } finally {
    addingModel.value = false
  }
}

function handleAddProvider(providerId: string): void {
  showAddProvider.value = false
  if (createProvider(providerId)) {
    // 立刻在左栏出现（带「未保存」），保存成功后标记自动失效
    markProviderAdded(providerId)
    toast.success(t('settings.providers.addedHint', { provider: providerId }))
  }
}

/**
 * 删除左栏里的供应商。
 *
 * 后端为目录里每个供应商都预建了空配置、也没有单独的删除接口，
 * 所以「删除」= 清空它的密钥与模型清单并立即落库（见 useProviderDraft.deleteProvider）：
 * 清空后它不再出现在左栏，也从对话窗口的模型下拉里消失。
 */
async function handleRemoveProvider(providerId: string): Promise<void> {
  const label =
    navigationProviders.value.find(item => item.id === providerId)?.name || providerId
  if (!window.confirm(t('settings.providers.removeConfirm', { provider: label }))) {
    return
  }

  const removed = await deleteProvider(providerId)
  if (!removed) {
    return
  }

  // 先撤销「本次会话刚添加」的标记，否则它还会以「未保存」的身份留在左栏
  unmarkProviderAdded(providerId)

  if (selectedProvider.value === providerId) {
    // 删的正是在编辑的这个：切到左栏里剩下的第一个，右栏别停在已清空的配置上
    const next = navigationProviders.value.find(item => item.id !== providerId)
    selectedProvider.value = next?.id || ''
  }

  toast.success(t('settings.providers.removedHint', { provider: label }))
}

/**
 * 保存前校验（由设置面板调用）。
 * 一个模型都没有的供应商在对话窗口里选不到，保存时明确告知用户。
 */
function validateBeforeSave(): string | null {
  if (!selectedProvider.value || providerModels.value.length > 0) {
    return null
  }
  return t('settings.providers.models.emptySaveWarning', {
    provider: selectedProviderMeta.value?.name || selectedProvider.value,
  })
}

defineExpose({ validateBeforeSave })

/* ------------------------------------------------------------------ */
/* watchers                                                            */
/* ------------------------------------------------------------------ */

watch(selectedProvider, (newProvider, oldProvider) => {
  if (!newProvider) {
    return
  }

  showFetchDialog.value = false

  if (isHydrating.value || isApplyingExternalConfig.value) {
    return
  }

  if (oldProvider) {
    // 必须显式传旧 id：此刻 selectedProvider 已经是新的了，
    // 不传会把旧供应商的草稿写进新供应商
    syncProviderDraftToStore(oldProvider)
  }

  isHydrating.value = true
  hydrateDraft(newProvider)
  isHydrating.value = false
  syncProviderDraftToStore()
  syncModelDraftToStore()
  testResult.value = null
})

watch(providerConfig, () => {
  if (isHydrating.value) {
    return
  }
  syncProviderDraftToStore()
  syncModelDraftToStore()
  testResult.value = null
}, { deep: true })

watch(providerModels, list => {
  if (isHydrating.value) {
    return
  }
  // 当前选中的模型被删除或隐藏时，回落到第一个可用模型
  const current = modelName.value
  if (current && list.some(model => model.id === current && model.enabled !== false)) {
    return
  }
  const fallback = list.find(model => model.enabled !== false)
  if (fallback) {
    modelName.value = fallback.id
    syncModelDraftToStore()
  }
}, { deep: true })

watch(() => settingsStore.settings, newSettings => {
  if (newSettings && !selectedProvider.value) {
    initializeProvider()
  }
}, { immediate: true })

onMounted(async () => {
  try {
    await loadProviders()
  } catch {
    toast.error(t('common.error'))
  }
  initializeProvider()
})
</script>

<style scoped>
@import './styles/ProviderConfig.css';
</style>
