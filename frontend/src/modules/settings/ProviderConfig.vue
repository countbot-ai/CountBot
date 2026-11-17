<template>
  <div class="provider-config" :class="{ 'is-rail-expanded': railExpanded }">
    <div class="provider-workspace">
      <ProviderNavList
        :items="navigationProviders"
        :selected-id="selectedProvider"
        :title="$t('settings.providers.sidebar.title')"
        :add-label="$t('settings.providers.sidebar.add')"
        :remove-label="$t('settings.providers.removeProvider')"
        :current-label="$t('settings.providers.currentBadge')"
        :expanded="railExpanded"
        @select="selectProvider"
        @add="showAddProvider = true"
        @remove="handleRemoveProvider"
        @toggle-expanded="railExpanded = !railExpanded"
      />

      <section v-if="selectedProvider" class="provider-detail">
        <header class="provider-detail-header">
            <div class="provider-detail-identity">
              <span class="provider-detail-logo">
                <ProviderIcon :provider-id="selectedProvider" :size="22" />
              </span>
              <div class="provider-detail-copy">
                <div class="provider-detail-title-row">
                  <h4>{{ selectedProviderDisplayName }}</h4>
                  <span class="status-pill" :class="selectedProviderSelectable ? 'ready' : 'warning'">
                    {{ selectedProviderStatusText }}
                  </span>
                  <span v-if="isCustomProvider" class="provider-type-chip">
                    {{ $t('settings.providers.detail.customTag') }}
                  </span>
                </div>
                <p class="provider-detail-sub">
                  <span>{{ selectedProvider }}</span>
                  <span v-if="endpointLabel" class="provider-detail-sub-sep">·</span>
                  <span v-if="endpointLabel">{{ endpointLabel }}</span>
                </p>
              </div>
            </div>

            <div class="provider-detail-actions">
              <button
                type="button"
                class="provider-test-btn"
                :disabled="providerTesting"
                @click="testProvider"
              >
                <Loader2Icon v-if="providerTesting" :size="14" class="provider-test-spin" />
                <PlugZapIcon v-else :size="14" />
                <span>{{ providerTesting
                  ? $t('settings.providers.detail.testing')
                  : $t('settings.providers.detail.test') }}</span>
              </button>

              <label class="provider-enabled">
                <span>{{ $t('settings.providers.enabled') }}</span>
                <SwitchToggle
                  v-model="providerConfig.enabled"
                  :width="38"
                  :height="22"
                  :aria-label="$t('settings.providers.enabled')"
                />
              </label>
            </div>
          </header>

        <div class="provider-detail-scroll">
          <Transition name="provider-result">
            <div
              v-if="providerTestResult"
              class="provider-test-result"
              :class="providerTestResult.success ? 'is-success' : 'is-error'"
            >
              <component
                :is="providerTestResult.success ? CheckCircleIcon : XCircleIcon"
                :size="15"
              />
              <span class="provider-test-result-text">
                {{ providerTestResult.success
                  ? $t('settings.providers.detail.testSuccess', {
                      latency: providerTestResult.latencyMs ?? 0,
                      count: providerTestResult.modelCount ?? 0,
                    })
                  : $t('settings.providers.detail.testFailed', {
                      error: providerTestResult.error,
                    }) }}
              </span>
              <button
                type="button"
                class="provider-test-result-close"
                :aria-label="$t('common.close')"
                @click="clearProviderTestResult"
              >
                <XIcon :size="12" />
              </button>
            </div>
          </Transition>

          <section class="provider-card">
            <header class="provider-card-head">
              <div>
                <h5 class="provider-card-title">{{ $t('settings.providers.connection.title') }}</h5>
                <p class="provider-card-desc">{{ $t('settings.providers.connection.desc') }}</p>
              </div>
            </header>

            <div class="provider-card-body">
              <ProviderConnectionPanel
                v-model:name="providerConfig.name"
                v-model:base-url="providerConfig.baseUrl"
                v-model:api-type="providerConfig.apiType"
                v-model:api-keys="providerConfig.apiKeys"
                :api-type-options="apiTypeOptions"
                :is-api-key-optional="isApiKeyOptional"
                :is-custom-provider="isCustomProvider"
                :default-base-url="currentDefaultBaseUrl"
                :provider-name="selectedProviderDisplayName"
                :thinking-note="selectedProviderThinkingNote"
              />
            </div>
          </section>

          <section class="provider-card provider-card--models">
            <ProviderModelList
              :key="selectedProvider"
              :models="providerModels"
              :testing-model-id="testingModelId"
              :catalog-loading="catalogLoading"
              :source-label="sourceLabel"
              :context-label="contextLabel"
              @request-add="showAddModelDialog = true"
              @fetch-models="openFetchDialog"
              @test-model="testModel"
              @edit-model="openModelEditor"
              @delete-model="deleteModel"
              @toggle-model="toggleModel"
              @reorder-model="reorderModel"
            />
          </section>
        </div>

        <footer class="provider-savebar">
          <span class="provider-savebar-state" :class="{ 'is-dirty': isProviderDirty }">
            <span class="provider-savebar-dot" />
            {{ isProviderDirty
              ? $t('settings.providers.saveBar.unsaved')
              : $t('settings.providers.saveBar.saved') }}
          </span>

          <div class="provider-savebar-actions">
            <button
              type="button"
              class="co-btn co-btn--ghost"
              :disabled="!isProviderDirty || savingProvider"
              @click="handleDiscardProvider"
            >
              {{ $t('settings.providers.saveBar.discard') }}
            </button>
            <button
              type="button"
              class="co-btn co-btn--primary"
              :disabled="!isProviderDirty || savingProvider"
              @click="handleSaveProvider"
            >
              <Loader2Icon v-if="savingProvider" :size="14" class="provider-test-spin" />
              <span>{{ savingProvider
                ? $t('common.saving')
                : $t('settings.providers.saveBar.save') }}</span>
            </button>
          </div>
        </footer>
      </section>

      <section v-else class="provider-detail is-empty">
        <span class="provider-empty-icon">
          <ServerIcon :size="20" />
        </span>
        <p class="provider-empty-title">{{ $t('settings.providers.noProvider') }}</p>
        <p class="provider-empty-desc">{{ $t('settings.providers.sidebar.emptyHint') }}</p>
        <Button variant="primary" size="sm" :icon="PlusIcon" @click="showAddProvider = true">
          {{ $t('settings.providers.sidebar.add') }}
        </Button>
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
      :provider-id="selectedProvider"
      :api-base="draft.providerConfig.value.baseUrl"
      :can-share="canShare"
      :fetch-reasoning-levels="fetchLevels"
      @close="closeModelEditor"
      @save="saveModelEditor"
    />

    <AddModelDialog
      v-model:show="showAddModelDialog"
      :submitting="addingModel"
      :provider-id="selectedProvider"
      :api-base="draft.providerConfig.value.baseUrl"
      @confirm="handleAddModel"
    />

    <AddProviderDialog
      v-model:show="showAddProvider"
      :providers="addableProviders"
      @select="handleAddProvider"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  CheckCircle as CheckCircleIcon,
  Loader2 as Loader2Icon,
  PlugZap as PlugZapIcon,
  Plus as PlusIcon,
  Server as ServerIcon,
  X as XIcon,
  XCircle as XCircleIcon,
} from 'lucide-vue-next'
import Button from '@/components/ui/Button.vue'
import SwitchToggle from '@/components/ui/SwitchToggle.vue'
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
import { useConfirm } from '@/composables/useConfirm'
import {
  createAdminSource,
  createUserSource,
  type ProviderConfigSource,
} from './provider-config/source'
import type { ReasoningLevelsResponse } from '@/api'
import type { ModelUpdatePayload } from './provider-config/types'
import { resolveProviderLabel } from './provider-config/constants'

const props = withDefaults(
  defineProps<{
    /** admin=全局设置；user=普通用户自有配置（/api/me/providers） */
    scope?: 'admin' | 'user'
  }>(),
  { scope: 'admin' },
)

const { t, te } = useI18n()
const toast = useToast()
const { confirm } = useConfirm()

/** 用户侧配置一律私有：共享区块只在管理员视角出现 */
const canShare = computed(() => props.scope === 'admin')

const source: ProviderConfigSource = props.scope === 'user' ? createUserSource() : createAdminSource()

const fetchLevels = (model: string): Promise<ReasoningLevelsResponse> =>
  source.api.getReasoningLevels(model)

const showAddProvider = ref(false)
const showAddModelDialog = ref(false)
const addingModel = ref(false)

/** 服务商轨道展开偏好：默认展开，并记住用户上次的选择 */
const RAIL_EXPANDED_STORAGE_KEY = 'CountBot-provider-rail-expanded'

function readRailExpandedPreference(): boolean {
  try {
    const stored = window.localStorage.getItem(RAIL_EXPANDED_STORAGE_KEY)
    return stored === null ? true : stored === '1'
  } catch {
    return true
  }
}

const railExpanded = ref(readRailExpandedPreference())

watch(railExpanded, expanded => {
  try {
    window.localStorage.setItem(RAIL_EXPANDED_STORAGE_KEY, expanded ? '1' : '0')
  } catch {
    // 隐私模式等不可写场景：只在本次会话内生效
  }
})

/* ------------------------------------------------------------------ */
/* 三个职责模块：清单导航 / 连接草稿 / 模型清单                          */
/* ------------------------------------------------------------------ */

const catalog = useProviderCatalog(source)

const draft = useProviderDraft({
  selectedProvider: catalog.selectedProvider,
  selectedProviderMeta: catalog.selectedProviderMeta,
  availableProviders: catalog.availableProviders,
  source,
})

const models = useProviderModels({
  selectedProvider: catalog.selectedProvider,
  saveProviderConnection: draft.saveProviderConnection,
  syncProviderDraftToStore: draft.syncProviderDraftToStore,
  getPrimaryApiKey: draft.getPrimaryApiKey,
  apiBase: computed(() => draft.providerConfig.value.baseUrl),
  apiType: computed(() => draft.providerConfig.value.apiType),
  source,
})

const {
  selectedProvider,
  selectedProviderMeta,
  navigationProviders,
  addableProviders,
  loadProviders,
  selectProvider,
  markProviderAdded,
  unmarkProviderAdded,
} = catalog

const {
  providerConfig,
  isProviderDirty,
  savingProvider,
  isApiKeyOptional,
  getPrimaryApiKey,
  isCustomProvider,
  currentDefaultBaseUrl,
  selectedProviderSelectable,
  selectedProviderStatusText,
  selectedProviderThinkingNote,
  isHydrating,
  hydrateDraft,
  initializeProvider,
  syncProviderDraftToStore,
  syncModelDraftToStore,
  saveProviderConnection,
  discardDraft,
  createProvider,
  deleteProvider,
} = draft

const {
  models: providerModels,
  existingModelIds,
  editingModel,
  testingModelId,
  providerTesting,
  providerTestResult,
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
  reorderModel,
  openModelEditor,
  closeModelEditor,
  saveModelEditor,
  testModel,
  testProvider,
  clearProviderTestResult,
} = models

/* ------------------------------------------------------------------ */
/* 下拉选项与头部摘要                                                  */
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

/** 头部副标题只展示接口主机名，避免长 URL 撑破布局 */
const endpointLabel = computed(() => {
  const raw = (providerConfig.value.baseUrl || currentDefaultBaseUrl.value || '').trim()
  if (!raw) {
    return ''
  }
  try {
    return new URL(raw).host
  } catch {
    return raw
  }
})

/** 用户自定义名称优先，否则按当前语言展示供应商本地化名称 */
const selectedProviderDisplayName = computed(() => {
  const customName = providerConfig.value.name.trim()
  if (customName) {
    return customName
  }
  return resolveProviderLabel(
    selectedProvider.value,
    t,
    te,
    selectedProviderMeta.value?.name || selectedProvider.value,
  )
})

/* 测试结果自动淡出：成功提示 3.5s 后自熄，失败保留给用户处理 */
let testResultTimer: number | undefined
watch(providerTestResult, result => {
  if (testResultTimer) {
    window.clearTimeout(testResultTimer)
    testResultTimer = undefined
  }
  if (result?.success) {
    testResultTimer = window.setTimeout(() => {
      clearProviderTestResult()
    }, 3500)
  }
})

onBeforeUnmount(() => {
  if (testResultTimer) {
    window.clearTimeout(testResultTimer)
  }
})

/* ------------------------------------------------------------------ */
/* 动作                                                                */
/* ------------------------------------------------------------------ */

/** 添加模型：成功后关窗，失败留给弹窗让用户改 ID 重试 */
async function handleAddModel(
  modelId: string,
  contextWindow: number | null,
  nativeCapabilities?: ModelUpdatePayload['native_capabilities'],
): Promise<void> {
  if (addingModel.value) {
    return
  }
  addingModel.value = true
  try {
    const saved = await commitNewModel(modelId, contextWindow, nativeCapabilities)
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
    toast.success(
      t('settings.providers.addedHint', {
        provider: resolveProviderLabel(providerId, t, te, providerId),
      }),
    )
  }
}

/** 保存当前供应商的连接配置 */
async function handleSaveProvider(): Promise<void> {
  if (!selectedProvider.value || savingProvider.value) {
    return
  }
  const keyWarning = validateConnectionBeforeSave()
  if (keyWarning) {
    toast.error(keyWarning, t('common.error'))
    return
  }
  syncProviderDraftToStore()
  syncModelDraftToStore()

  const saved = await saveProviderConnection()
  if (saved) {
    clearProviderTestResult()
    toast.success(t('settings.saveSuccess'), t('common.success'))
  }
}

/** 撤销当前供应商的草稿改动；刚添加还没保存的直接取消添加 */
function handleDiscardProvider(): void {
  const providerId = selectedProvider.value
  if (!providerId) {
    return
  }

  const item = navigationProviders.value.find(entry => entry.id === providerId)
  clearProviderTestResult()

  if (!item?.pendingSave) {
    discardDraft()
    return
  }

  // 刚添加还没落库：把草稿从清单里摘掉，并退回到下一个已接入的供应商
  unmarkProviderAdded(providerId)
  const providers = source.settings.value?.providers
  if (providers) {
    delete providers[providerId]
  }
  const next = navigationProviders.value.find(entry => entry.id !== providerId)
  selectedProvider.value = next?.id || ''
  if (!next) {
    providerConfig.value = {
      apiKey: '',
      apiKeys: [''],
      baseUrl: '',
      enabled: true,
      name: '',
      apiType: 'openai-chat-completions',
    }
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
  const confirmed = await confirm({
    title: t('common.confirmDelete'),
    message: t('settings.providers.removeConfirm', { provider: label }),
    type: 'danger',
    confirmText: t('common.delete'),
    confirmVariant: 'danger'
  })
  if (!confirmed) {
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
    provider: selectedProviderDisplayName.value,
  })
}

/** 有模型但未配置密钥时阻断保存，避免保存后到对话页才暴露不可用。 */
function validateConnectionBeforeSave(): string | null {
  if (
    !selectedProvider.value
    || !providerConfig.value.enabled
    || isApiKeyOptional.value
    || getPrimaryApiKey().trim()
    || providerModels.value.length === 0
  ) {
    return null
  }
  return t('settings.providers.apiKeyRequiredWarning', {
    provider: selectedProviderDisplayName.value,
  })
}

defineExpose({ validateBeforeSave, validateConnectionBeforeSave })

/* ------------------------------------------------------------------ */
/* watchers                                                            */
/* ------------------------------------------------------------------ */

watch(selectedProvider, (newProvider, oldProvider) => {
  if (!newProvider) {
    return
  }

  showFetchDialog.value = false
  clearProviderTestResult()

  if (isHydrating.value) {
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
})

watch(providerConfig, () => {
  if (isHydrating.value) {
    return
  }
  syncProviderDraftToStore()
  syncModelDraftToStore()
  // 连接信息改过之后，上一次的测试结果就不再可信
  clearProviderTestResult()
}, { deep: true })

watch(providerModels, list => {
  if (isHydrating.value) {
    return
  }
  // 当前选中的模型被删除或隐藏时，回落到第一个可用模型
  const current = draft.modelName.value
  if (current && list.some(model => model.id === current && model.enabled !== false)) {
    return
  }
  const fallback = list.find(model => model.enabled !== false)
  if (fallback) {
    draft.modelName.value = fallback.id
    syncModelDraftToStore()
  }
}, { deep: true })

watch(() => source.settings.value, newSettings => {
  if (newSettings && !selectedProvider.value) {
    initializeProvider()
  }
}, { immediate: true })

onMounted(async () => {
  try {
    // 用户视图按需拉取：settings 就绪后 initializeProvider 才有数据可用
    if (props.scope === 'user' && source.refresh) {
      await source.refresh()
      // model.provider 可能指向共享供应商（只读、不在自有清单），
      // 清空后让初始化回落到第一个自有供应商，避免草稿落在不可编辑的配置上
      const view = source.settings.value
      if (view?.model?.provider && !view.providers?.[view.model.provider]) {
        view.model.provider = ''
        view.model.model = ''
      }
    }
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
