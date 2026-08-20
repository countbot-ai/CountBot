<template>
  <Modal
    :model-value="modelValue"
    size="full"
    :title="panelTitle"
    :show-footer="false"
    @update:modelValue="emit('update:modelValue', $event)"
  >
    <div class="preset-workbench">
      <section class="preset-hero">
        <div class="hero-copy">
          <h3>{{ panelTitle }}</h3>
        </div>

        <div class="hero-actions">
          <Button variant="secondary" :icon="PlusIcon" @click="beginCreateFromCurrent">
            {{ $t('settings.providers.presetPanel.saveCurrent') }}
          </Button>
          <Button variant="outline" :icon="UploadIcon" @click="fileInputRef?.click()">
            {{ $t('settings.presets.importPresets') }}
          </Button>
          <Button variant="outline" :icon="DownloadIcon" :disabled="presets.length === 0" @click="handleExport">
            {{ $t('settings.presets.exportPresets') }}
          </Button>
        </div>
      </section>

      <section class="draft-summary">
        <div class="summary-card">
          <span class="summary-label">{{ $t('settings.providers.presetPanel.currentDraft') }}</span>
          <strong>{{ currentDraftTitle }}</strong>
        </div>
        <div class="summary-card">
          <span class="summary-label">{{ $t('settings.providers.presetPanel.savedCount') }}</span>
          <strong>{{ presets.length }}</strong>
        </div>
        <div class="summary-card">
          <span class="summary-label">{{ $t('settings.providers.presetPanel.codingPlanCount') }}</span>
          <strong>{{ codingPlanPresets.length }}</strong>
        </div>
      </section>

      <div class="panel-tabs" role="tablist" :aria-label="$t('settings.providers.presetPanel.tabsLabel')">
        <button
          type="button"
          class="panel-tab"
          :class="{ active: activeTab === 'saved' }"
          @click="activeTab = 'saved'"
        >
          <component :is="LayoutGridIcon" :size="16" />
          <span>{{ $t('settings.providers.presetPanel.savedTab') }}</span>
        </button>
        <button
          type="button"
          class="panel-tab"
          :class="{ active: activeTab === 'codingplan' }"
          @click="activeTab = 'codingplan'"
        >
          <component :is="CpuIcon" :size="16" />
          <span>{{ $t('settings.providers.tabs.codingPlan') }}</span>
        </button>
      </div>

      <input
        ref="fileInputRef"
        type="file"
        accept=".json"
        class="file-input"
        @change="handleFileImport"
      >

      <div v-if="activeTab === 'saved'" class="panel-layout">
        <section class="catalog-panel">
          <div class="catalog-toolbar">
            <Input
              v-model="searchQuery"
              type="search"
              :placeholder="$t('settings.providers.presetPanel.searchPlaceholder')"
            />
            <Button variant="ghost" :icon="SparklesIcon" @click="beginCreateFromCurrent">
              {{ $t('settings.providers.presetPanel.newPreset') }}
            </Button>
          </div>

          <div class="filter-chips">
            <button
              type="button"
              class="filter-chip"
              :class="{ active: providerFilter === 'all' }"
              @click="providerFilter = 'all'"
            >
              {{ $t('settings.providers.presetPanel.allProviders') }}
            </button>
            <button
              v-for="option in presetProviderFilters"
              :key="option.value"
              type="button"
              class="filter-chip"
              :class="{ active: providerFilter === option.value }"
              @click="providerFilter = option.value"
            >
              {{ option.label }}
            </button>
          </div>

          <div class="catalog-list">
            <article
              v-for="preset in filteredPresets"
              :key="preset.id"
              class="preset-card"
              :class="{ active: selectedSavedPresetId === preset.id }"
              @click="startEditPreset(preset.id)"
            >
              <div class="preset-card-head">
                <div class="preset-card-copy">
                  <strong>{{ preset.name }}</strong>
                  <span>{{ formatPresetSubtitle(preset) }}</span>
                </div>
                <div class="preset-card-meta">
                  <span class="preset-card-date">{{ formatDate(preset.updatedAt) }}</span>
                  <div class="preset-card-quick-actions">
                    <Button
                      variant="ghost"
                      size="sm"
                      :icon="PencilIcon"
                      class="preset-card-icon-button"
                      @click.stop="startEditPreset(preset.id)"
                    >
                      {{ $t('common.edit') }}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      :icon="Trash2Icon"
                      class="preset-card-icon-button preset-card-delete-button"
                      @click.stop="deleteSavedPreset(preset.id)"
                    >
                      {{ $t('common.delete') }}
                    </Button>
                  </div>
                </div>
              </div>

              <p v-if="preset.description" class="preset-card-description">{{ preset.description }}</p>

              <div class="preset-card-tags">
                <span class="tag">{{ getProviderLabelById(preset.provider) }}</span>
                <span class="tag model-tag">{{ preset.model }}</span>
                <span v-if="preset.baseUrl" class="tag subtle">{{ $t('settings.providers.presetPanel.customEndpoint') }}</span>
              </div>

              <div class="preset-card-actions">
                <Button variant="primary" size="sm" class="preset-card-apply-button" @click.stop="applySavedPreset(preset.id)">
                  {{ $t('settings.providers.presetPanel.applyToDraft') }}
                </Button>
              </div>
            </article>

            <div v-if="filteredPresets.length === 0" class="empty-card">
              <component :is="BookmarkIcon" :size="18" />
              <strong>{{ $t('settings.providers.presetPanel.emptyTitle') }}</strong>
              <p>{{ $t('settings.providers.presetPanel.emptyDesc') }}</p>
            </div>
          </div>
        </section>

        <section
          ref="editorPanelRef"
          class="editor-panel"
          :class="{ 'editor-panel-spotlight': editorPanelSpotlight }"
        >
          <div class="editor-header">
            <div>
              <span class="editor-kicker">{{ editorMode === 'edit' ? $t('common.edit') : $t('common.add') }}</span>
              <h4>{{ editorTitle }}</h4>
            </div>
            <Button variant="ghost" size="sm" :icon="RefreshCwIcon" @click="fillEditorFromCurrent">
              {{ $t('settings.providers.presetPanel.useCurrentDraft') }}
            </Button>
          </div>

          <div class="editor-grid">
            <label class="editor-field editor-field-wide">
              <span>{{ $t('settings.presets.presetName') }}</span>
              <input ref="presetNameInputRef" v-model="presetEditor.name" type="text" class="editor-input">
            </label>

            <label class="editor-field editor-field-wide">
              <span>{{ $t('settings.presets.presetDescription') }}</span>
              <textarea v-model="presetEditor.description" class="editor-textarea" rows="3" />
            </label>

            <label class="editor-field">
              <span>{{ $t('settings.providers.selectProvider') }}</span>
              <Select
                v-model="presetEditor.provider"
                :options="providerOptions"
                :placeholder="$t('settings.providers.selectProvider')"
                searchable
              />
            </label>

            <label class="editor-field">
              <span>{{ $t('settings.providers.model') }}</span>
              <input v-model="presetEditor.model" type="text" class="editor-input">
            </label>

            <label class="editor-field">
              <span>{{ $t('settings.providers.baseUrl') }}</span>
              <input v-model="presetEditor.baseUrl" type="text" class="editor-input">
            </label>

            <label class="editor-field">
              <span>{{ $t('settings.providers.apiKey') }}</span>
              <input v-model="presetEditor.apiKey" type="password" class="editor-input">
            </label>

            <label class="editor-field">
              <span>{{ $t('settings.model.temperature') }}</span>
              <input v-model="presetEditor.temperature" type="number" step="0.1" min="0" max="2" class="editor-input">
            </label>

            <label class="editor-field">
              <span>{{ $t('settings.model.maxTokens') }}</span>
              <input v-model="presetEditor.maxTokens" type="number" min="0" step="256" class="editor-input">
            </label>

            <label class="editor-field">
              <span>{{ $t('settings.model.maxIterations') }}</span>
              <input v-model="presetEditor.maxIterations" type="number" min="1" step="1" class="editor-input">
            </label>
          </div>

          <div class="editor-preview">
            <span class="preview-label">{{ $t('settings.presets.configPreview') }}</span>
            <strong>{{ previewTitle }}</strong>
            <span>{{ previewMeta }}</span>
          </div>

          <div class="editor-actions">
            <Button variant="secondary" :icon="CheckIcon" @click="applyEditorDraft">
              {{ $t('settings.providers.presetPanel.applyToDraft') }}
            </Button>
            <Button variant="primary" :icon="SaveIcon" @click="saveEditorPreset">
              {{ editorMode === 'edit' ? $t('settings.providers.presetPanel.updatePreset') : $t('settings.presets.savePreset') }}
            </Button>
            <Button
              v-if="editorMode === 'edit' && presetEditor.id"
              variant="ghost"
              :icon="Trash2Icon"
              @click="deleteEditorPreset"
            >
              {{ $t('common.delete') }}
            </Button>
          </div>
        </section>
      </div>

      <div v-else class="panel-layout">
        <section class="catalog-panel">
          <div class="catalog-toolbar">
            <Input
              v-model="vendorSearchQuery"
              type="search"
              :placeholder="$t('settings.providers.presetPanel.vendorSearchPlaceholder')"
            />
          </div>

          <div class="vendor-grid">
            <button
              v-for="vendor in filteredCodingPlans"
              :key="vendor.id"
              type="button"
              class="vendor-card"
              :class="{ active: selectedCodingPlanId === vendor.id }"
              @click="selectCodingPlan(vendor.id)"
            >
              <div class="vendor-card-head">
                <strong>{{ getCodingPlanVendorLabel(vendor.vendor) }}</strong>
                <span v-if="recommendedVendorId === vendor.id" class="vendor-badge">
                  {{ $t('settings.providers.codingPlan.recommendedBadge') }}
                </span>
              </div>
              <span class="vendor-card-model">{{ vendor.defaultModel }}</span>
              <span class="vendor-card-meta">{{ vendor.models.length }} {{ $t('settings.providers.presetPanel.modelsAvailable') }}</span>
            </button>
          </div>
        </section>

        <section class="editor-panel">
          <template v-if="selectedCodingPlan">
            <div class="editor-header">
              <div>
                <span class="editor-kicker">{{ $t('settings.providers.tabs.codingPlan') }}</span>
                <h4>{{ getCodingPlanVendorLabel(selectedCodingPlan.vendor) }}</h4>
              </div>
              <div class="editor-links">
                <a :href="selectedCodingPlan.subscribeUrl" target="_blank" rel="noreferrer" class="editor-link">
                  {{ $t('settings.providers.codingPlan.subscribe') }}
                </a>
                <a :href="selectedCodingPlan.sourceUrl" target="_blank" rel="noreferrer" class="editor-link secondary">
                  {{ $t('settings.providers.codingPlan.viewDocs') }}
                </a>
              </div>
            </div>

            <div class="model-pill-list">
              <button
                v-for="model in selectedCodingPlan.models"
                :key="model"
                type="button"
                class="model-pill"
                :class="{ active: codingPlanForm.model === model }"
                @click="codingPlanForm.model = model"
              >
                {{ model }}
              </button>
            </div>

            <div class="editor-grid">
              <label class="editor-field editor-field-wide">
                <span>{{ $t('settings.providers.codingPlan.modelName') }}</span>
                <input v-model="codingPlanForm.model" type="text" class="editor-input">
              </label>

              <label class="editor-field">
                <span>{{ $t('settings.providers.codingPlan.apiKey') }}</span>
                <input v-model="codingPlanForm.apiKey" type="password" class="editor-input">
              </label>

              <label class="editor-field editor-field-wide">
                <span>{{ $t('settings.providers.codingPlan.baseUrl') }}</span>
                <input v-model="codingPlanForm.baseUrl" type="text" class="editor-input">
              </label>
            </div>

            <div class="editor-preview">
              <span class="preview-label">{{ $t('settings.providers.presetPanel.codingPlanSnapshot') }}</span>
              <strong>{{ codingPlanForm.model || selectedCodingPlan.defaultModel }}</strong>
              <span>{{ codingPlanForm.baseUrl || selectedCodingPlan.openaiBaseUrl }}</span>
            </div>

            <div class="editor-actions">
              <Button variant="primary" :icon="CheckIcon" @click="applyCodingPlan">
                {{ $t('settings.providers.presetPanel.applyCodingPlan') }}
              </Button>
              <Button variant="secondary" :icon="SparklesIcon" @click="resetCodingPlanForm">
                {{ $t('settings.providers.presetPanel.resetVendorDraft') }}
              </Button>
            </div>
          </template>

          <div v-else class="empty-card">
            <component :is="CpuIcon" :size="18" />
            <strong>{{ $t('settings.providers.codingPlan.noVendorSelected') }}</strong>
          </div>
        </section>
      </div>
    </div>
  </Modal>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Bookmark as BookmarkIcon,
  Check as CheckIcon,
  Cpu as CpuIcon,
  Download as DownloadIcon,
  LayoutGrid as LayoutGridIcon,
  Pencil as PencilIcon,
  Plus as PlusIcon,
  RefreshCw as RefreshCwIcon,
  Save as SaveIcon,
  Sparkles as SparklesIcon,
  Trash2 as Trash2Icon,
  Upload as UploadIcon,
} from 'lucide-vue-next'
import Modal from '@/components/ui/Modal.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Select from '@/components/ui/Select.vue'
import { usePresets } from '@/composables/usePresets'
import { useToast } from '@/composables/useToast'
import type { ProviderMetadata } from '@/types/settings'
import { CODING_PLAN_PRESETS, type CodingPlanPreset } from '@/data/codingPlanPresets'
import { sortProvidersForDisplay } from '@/utils/providerRuntime'

interface ProviderDraftConfig {
  provider: string
  model: string
  apiKey: string
  baseUrl?: string
  enabled: boolean
  temperature?: number
  maxTokens?: number
  maxIterations?: number
}

interface ApplyDraftPayload extends ProviderDraftConfig {
  source: 'preset' | 'codingplan'
  label: string
}

interface Props {
  modelValue: boolean
  currentConfig: ProviderDraftConfig
  availableProviders: ProviderMetadata[]
}

interface Emits {
  (e: 'update:modelValue', value: boolean): void
  (e: 'apply-config', value: ApplyDraftPayload): void
}

interface PresetEditorState {
  id: string
  name: string
  description: string
  provider: string
  model: string
  apiKey: string
  baseUrl: string
  temperature: string
  maxTokens: string
  maxIterations: string
}

const CODING_PLAN_STORAGE_KEY = 'codingPlanConfigs'

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const { t } = useI18n()
const toast = useToast()
const { presets, createPreset, updatePreset, deletePreset, exportPresets, importPresets } = usePresets()

const activeTab = ref<'saved' | 'codingplan'>('saved')
const searchQuery = ref('')
const vendorSearchQuery = ref('')
const providerFilter = ref('all')
const selectedSavedPresetId = ref('')
const editorMode = ref<'create' | 'edit'>('create')
const fileInputRef = ref<HTMLInputElement>()
const editorPanelRef = ref<HTMLElement | null>(null)
const presetNameInputRef = ref<HTMLInputElement | null>(null)
const editorPanelSpotlight = ref(false)
const codingPlanPresets = CODING_PLAN_PRESETS
const recommendedVendorId = 'deepseek'
const selectedCodingPlanId = ref<string>(recommendedVendorId)
let editorPanelSpotlightTimer: number | null = null

const presetEditor = reactive<PresetEditorState>({
  id: '',
  name: '',
  description: '',
  provider: '',
  model: '',
  apiKey: '',
  baseUrl: '',
  temperature: '',
  maxTokens: '',
  maxIterations: '',
})

const codingPlanForm = reactive({
  model: '',
  apiKey: '',
  baseUrl: '',
  enabled: true,
})

const codingPlanConfigs = ref<Record<string, {
  apiKey: string
  baseUrl: string
  model: string
  enabled: boolean
}>>({})

const panelTitle = computed(() => t('settings.providers.presetPanel.title'))

const providerOptions = computed(() =>
  sortProvidersForDisplay(props.availableProviders).map(provider => ({
    value: provider.id,
    label: getProviderLabelById(provider.id),
  }))
)

const presetProviderFilters = computed(() => {
  const providerIds = Array.from(new Set(presets.value.map(preset => preset.provider)))
  return providerIds.map(providerId => ({
    value: providerId,
    label: getProviderLabelById(providerId),
  }))
})

const filteredPresets = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  return presets.value.filter(preset => {
    const matchesProvider = providerFilter.value === 'all' || preset.provider === providerFilter.value
    const matchesQuery = !query
      || preset.name.toLowerCase().includes(query)
      || preset.model.toLowerCase().includes(query)
      || (preset.description || '').toLowerCase().includes(query)
    return matchesProvider && matchesQuery
  })
})

const filteredCodingPlans = computed(() => {
  const query = vendorSearchQuery.value.trim().toLowerCase()
  if (!query) {
    return codingPlanPresets
  }

  return codingPlanPresets.filter(plan => {
    const vendorLabel = getCodingPlanVendorLabel(plan.vendor).toLowerCase()
    return vendorLabel.includes(query) || plan.models.some(model => model.toLowerCase().includes(query))
  })
})

const selectedCodingPlan = computed(() =>
  codingPlanPresets.find(plan => plan.id === selectedCodingPlanId.value) || null
)

const currentDraftTitle = computed(() =>
  `${getProviderLabelById(props.currentConfig.provider)} / ${props.currentConfig.model || t('common.default')}`
)

const editorTitle = computed(() =>
  editorMode.value === 'edit'
    ? (presetEditor.name || t('settings.providers.presetPanel.editPreset'))
    : t('settings.providers.presetPanel.createPreset')
)

const previewTitle = computed(() =>
  `${getProviderLabelById(presetEditor.provider || props.currentConfig.provider)} / ${presetEditor.model || t('common.default')}`
)

const previewMeta = computed(() =>
  presetEditor.baseUrl || t('settings.providers.presetPanel.usingDefaultBaseUrl')
)

function getProviderLabelById(providerId: string): string {
  const provider = props.availableProviders.find(item => item.id === providerId)
  return provider?.name || providerId || t('common.unknown')
}

function getCodingPlanVendorLabel(vendor: string): string {
  const key = `settings.providers.codingPlan.vendors.${vendor}`
  const translated = t(key)
  return translated === key ? vendor : translated
}

function formatPresetSubtitle(preset: { provider: string; model: string }): string {
  return `${getProviderLabelById(preset.provider)} / ${preset.model}`
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString()
}

function createEditorFromCurrentConfig(): PresetEditorState {
  return {
    id: '',
    name: '',
    description: '',
    provider: props.currentConfig.provider,
    model: props.currentConfig.model,
    apiKey: props.currentConfig.apiKey,
    baseUrl: props.currentConfig.baseUrl || '',
    temperature: props.currentConfig.temperature === undefined ? '' : String(props.currentConfig.temperature),
    maxTokens: props.currentConfig.maxTokens === undefined ? '' : String(props.currentConfig.maxTokens),
    maxIterations: props.currentConfig.maxIterations === undefined ? '' : String(props.currentConfig.maxIterations),
  }
}

function syncEditor(state: PresetEditorState) {
  presetEditor.id = state.id
  presetEditor.name = state.name
  presetEditor.description = state.description
  presetEditor.provider = state.provider
  presetEditor.model = state.model
  presetEditor.apiKey = state.apiKey
  presetEditor.baseUrl = state.baseUrl
  presetEditor.temperature = state.temperature
  presetEditor.maxTokens = state.maxTokens
  presetEditor.maxIterations = state.maxIterations
}

async function revealEditorPanel(focusNameField = false) {
  await nextTick()

  editorPanelRef.value?.scrollIntoView({
    behavior: 'smooth',
    block: 'nearest',
    inline: 'nearest',
  })

  if (focusNameField) {
    presetNameInputRef.value?.focus({ preventScroll: true })
    presetNameInputRef.value?.select()
  }

  editorPanelSpotlight.value = false
  if (editorPanelSpotlightTimer !== null) {
    window.clearTimeout(editorPanelSpotlightTimer)
  }

  requestAnimationFrame(() => {
    editorPanelSpotlight.value = true
    editorPanelSpotlightTimer = window.setTimeout(() => {
      editorPanelSpotlight.value = false
      editorPanelSpotlightTimer = null
    }, 850)
  })
}

function beginCreateFromCurrent() {
  activeTab.value = 'saved'
  editorMode.value = 'create'
  selectedSavedPresetId.value = ''
  syncEditor(createEditorFromCurrentConfig())
  void revealEditorPanel(false)
}

function fillEditorFromCurrent() {
  const next = createEditorFromCurrentConfig()
  next.name = presetEditor.name
  next.description = presetEditor.description
  syncEditor(next)
}

function startEditPreset(presetId: string) {
  const preset = presets.value.find(item => item.id === presetId)
  if (!preset) {
    return
  }

  activeTab.value = 'saved'
  editorMode.value = 'edit'
  selectedSavedPresetId.value = presetId
  syncEditor({
    id: preset.id,
    name: preset.name,
    description: preset.description || '',
    provider: preset.provider,
    model: preset.model,
    apiKey: preset.apiKey,
    baseUrl: preset.baseUrl || '',
    temperature: preset.temperature === undefined ? '' : String(preset.temperature),
    maxTokens: preset.maxTokens === undefined ? '' : String(preset.maxTokens),
    maxIterations: preset.maxIterations === undefined ? '' : String(preset.maxIterations),
  })
  void revealEditorPanel(true)
}

function toOptionalNumber(value: string): number | undefined {
  const normalized = value.trim()
  if (!normalized) {
    return undefined
  }

  const parsed = Number(normalized)
  return Number.isFinite(parsed) ? parsed : undefined
}

function emitApplyConfig(payload: ApplyDraftPayload) {
  emit('apply-config', payload)
  emit('update:modelValue', false)
}

function applySavedPreset(presetId: string) {
  const preset = presets.value.find(item => item.id === presetId)
  if (!preset) {
    return
  }

  emitApplyConfig({
    source: 'preset',
    label: preset.name,
    provider: preset.provider,
    model: preset.model,
    apiKey: preset.apiKey,
    baseUrl: preset.baseUrl,
    enabled: props.currentConfig.enabled,
    temperature: preset.temperature,
    maxTokens: preset.maxTokens,
    maxIterations: preset.maxIterations,
  })
  toast.success(t('settings.providers.presetPanel.applySuccess'))
}

function applyEditorDraft() {
  if (!presetEditor.provider || !presetEditor.model) {
    toast.error(t('settings.providers.presetPanel.requiredFields'))
    return
  }

  emitApplyConfig({
    source: 'preset',
    label: presetEditor.name || presetEditor.model,
    provider: presetEditor.provider,
    model: presetEditor.model,
    apiKey: presetEditor.apiKey,
    baseUrl: presetEditor.baseUrl,
    enabled: props.currentConfig.enabled,
    temperature: toOptionalNumber(presetEditor.temperature),
    maxTokens: toOptionalNumber(presetEditor.maxTokens),
    maxIterations: toOptionalNumber(presetEditor.maxIterations),
  })
  toast.success(t('settings.providers.presetPanel.applySuccess'))
}

function saveEditorPreset() {
  if (!presetEditor.name.trim() || !presetEditor.provider || !presetEditor.model.trim()) {
    toast.error(t('settings.providers.presetPanel.requiredFields'))
    return
  }

  const payload = {
    name: presetEditor.name.trim(),
    description: presetEditor.description.trim() || undefined,
    provider: presetEditor.provider,
    model: presetEditor.model.trim(),
    apiKey: presetEditor.apiKey,
    baseUrl: presetEditor.baseUrl.trim() || undefined,
    temperature: toOptionalNumber(presetEditor.temperature),
    maxTokens: toOptionalNumber(presetEditor.maxTokens),
    maxIterations: toOptionalNumber(presetEditor.maxIterations),
  }

  if (editorMode.value === 'edit' && presetEditor.id) {
    updatePreset(presetEditor.id, payload)
    toast.success(t('settings.providers.presetPanel.updateSuccess'))
  } else {
    const presetId = createPreset(payload)
    editorMode.value = 'edit'
    presetEditor.id = presetId
    selectedSavedPresetId.value = presetId
    toast.success(t('settings.providers.presetPanel.createSuccess'))
  }
}

function deleteEditorPreset() {
  if (!presetEditor.id) {
    return
  }

  if (!confirmDeletePresetById(presetEditor.id)) {
    return
  }

  beginCreateFromCurrent()
}

function confirmDeletePresetById(presetId: string): boolean {
  const preset = presets.value.find(item => item.id === presetId)
  if (!preset) {
    return false
  }

  const confirmed = window.confirm(t('settings.presets.deletePresetConfirm', { name: preset.name }))
  if (!confirmed) {
    return false
  }

  deletePreset(presetId)
  toast.success(t('settings.providers.presetPanel.deleteSuccess'))
  return true
}

function deleteSavedPreset(presetId: string) {
  if (!confirmDeletePresetById(presetId)) {
    return
  }

  if (presets.value.length === 0) {
    beginCreateFromCurrent()
    return
  }

  if (selectedSavedPresetId.value === presetId) {
    startEditPreset(presets.value[0].id)
  }
}

function handleExport() {
  const blob = new Blob([exportPresets()], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `provider-presets-${new Date().toISOString().split('T')[0]}.json`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
  toast.success(t('settings.providers.presetPanel.exportSuccess'))
}

function handleFileImport(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) {
    return
  }

  const reader = new FileReader()
  reader.onload = (loadEvent) => {
    const content = String(loadEvent.target?.result || '')
    const result = importPresets(content)
    if (result.success) {
      toast.success(result.message)
      activeTab.value = 'saved'
    } else {
      toast.error(result.message)
    }
    target.value = ''
  }
  reader.readAsText(file)
}

function loadCodingPlanConfigs() {
  try {
    const stored = localStorage.getItem(CODING_PLAN_STORAGE_KEY)
    if (stored) {
      codingPlanConfigs.value = JSON.parse(stored)
    }
  } catch (error) {
    console.error('Failed to load coding plan configs:', error)
  }
}

function persistCodingPlanConfigs() {
  try {
    localStorage.setItem(CODING_PLAN_STORAGE_KEY, JSON.stringify(codingPlanConfigs.value))
  } catch (error) {
    console.error('Failed to save coding plan configs:', error)
  }
}

function syncCodingPlanForm(plan: CodingPlanPreset | null) {
  if (!plan) {
    codingPlanForm.model = ''
    codingPlanForm.apiKey = ''
    codingPlanForm.baseUrl = ''
    codingPlanForm.enabled = true
    return
  }

  const saved = codingPlanConfigs.value[plan.id]
  codingPlanForm.model = saved?.model || plan.defaultModel
  codingPlanForm.apiKey = saved?.apiKey || ''
  codingPlanForm.baseUrl = saved?.baseUrl || plan.openaiBaseUrl
  codingPlanForm.enabled = saved?.enabled ?? true
}

function selectCodingPlan(planId: string) {
  selectedCodingPlanId.value = planId
}

function resetCodingPlanForm() {
  syncCodingPlanForm(selectedCodingPlan.value)
}

function applyCodingPlan() {
  if (!selectedCodingPlan.value || !codingPlanForm.model.trim()) {
    toast.error(t('settings.providers.presetPanel.requiredFields'))
    return
  }

  emitApplyConfig({
    source: 'codingplan',
    label: getCodingPlanVendorLabel(selectedCodingPlan.value.vendor),
    provider: 'custom_openai',
    model: codingPlanForm.model.trim(),
    apiKey: codingPlanForm.apiKey,
    baseUrl: codingPlanForm.baseUrl.trim(),
    enabled: true,
    temperature: props.currentConfig.temperature,
    maxTokens: props.currentConfig.maxTokens,
    maxIterations: props.currentConfig.maxIterations,
  })
  toast.success(t('settings.providers.presetPanel.applySuccess'))
}

watch(() => props.modelValue, (show) => {
  if (!show) {
    return
  }

  if (presets.value.length > 0 && !selectedSavedPresetId.value) {
    startEditPreset(presets.value[0].id)
  } else if (presets.value.length === 0) {
    beginCreateFromCurrent()
  }

  if (!selectedCodingPlanId.value) {
    selectedCodingPlanId.value = recommendedVendorId
  }
  syncCodingPlanForm(selectedCodingPlan.value)
})

watch(presets, (nextPresets) => {
  if (selectedSavedPresetId.value && !nextPresets.some(preset => preset.id === selectedSavedPresetId.value)) {
    beginCreateFromCurrent()
  }
}, { deep: true })

watch(selectedCodingPlan, (plan) => {
  syncCodingPlanForm(plan)
}, { immediate: true })

watch(
  () => [selectedCodingPlanId.value, codingPlanForm.model, codingPlanForm.apiKey, codingPlanForm.baseUrl, codingPlanForm.enabled],
  () => {
    if (!selectedCodingPlanId.value) {
      return
    }
    codingPlanConfigs.value[selectedCodingPlanId.value] = {
      model: codingPlanForm.model,
      apiKey: codingPlanForm.apiKey,
      baseUrl: codingPlanForm.baseUrl,
      enabled: codingPlanForm.enabled,
    }
    persistCodingPlanConfigs()
  },
  { deep: true }
)

loadCodingPlanConfigs()

onBeforeUnmount(() => {
  if (editorPanelSpotlightTimer !== null) {
    window.clearTimeout(editorPanelSpotlightTimer)
  }
})
</script>
<style scoped>
@import './styles/ProviderPresetPanel.css';
</style>
